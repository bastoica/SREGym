import asyncio
import atexit
import os
import shutil
import threading
import time
from contextlib import nullcontext
from json.decoder import JSONDecodeError

from srearena.conductor.oracles.detection import DetectionOracle
from srearena.conductor.problems.registry import ProblemRegistry
from srearena.service.kubectl import KubeCtl
from srearena.service.telemetry.prometheus import Prometheus
from srearena.utils.critical_section import CriticalSection
from srearena.utils.sigint_aware_section import SigintAwareSection


class Conductor:
    def __init__(self):
        # core services
        self.problems = ProblemRegistry()
        self.kubectl = KubeCtl()
        self.prometheus = Prometheus()

        # runtime state
        self.problem_id = None
        self.problem = None
        self.detection_oracle = None
        self.execution_start_time = None

        # drives HTTP flow: noop→detection→localization→mitigation→done
        self.submission_stage = None
        self.results = {}

    def dependency_check(self, binaries: list[str]):
        for b in binaries:
            if shutil.which(b) is None:
                raise RuntimeError(f"[❌] Required dependency '{b}' not found.")

    async def start_problem(self):
        """
        Deploy environment, then set submission_stage='noop'.
        Uses SigintAwareSection only if we're in the main thread.
        """
        self.execution_start_time = time.time()
        self.problem = self.problems.get_problem_instance(self.problem_id)
        self.detection_oracle = DetectionOracle(self.problem)
        self.results = {}

        # Choose context manager based on thread
        if threading.current_thread() is threading.main_thread():
            ctx = SigintAwareSection()
        else:
            ctx = nullcontext()

        # 1) Environment setup
        self.dependency_check(["kubectl", "helm"])
        with ctx:
            print(f"[Session Start] Problem ID: {self.problem_id}")
            print("Setting up metrics-server...")
            self.kubectl.exec_command(
                "kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"
            )
            self.kubectl.exec_command(
                "kubectl -n kube-system patch deployment metrics-server "
                "--type=json -p='["
                '{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"},'
                '{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-preferred-address-types=InternalIP"}'
                "]'"
            )
            self.kubectl.wait_for_ready("kube-system")

            print("Setting up OpenEBS...")
            self.kubectl.exec_command("kubectl apply -f https://openebs.github.io/charts/openebs-operator.yaml")
            self.kubectl.exec_command(
                "kubectl patch storageclass openebs-hostpath "
                '-p \'{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}\''
            )
            self.kubectl.wait_for_ready("openebs")

            print("Deploying Prometheus...")
            self.prometheus.deploy()

            print("Deploying and starting workload...")
            self.problem.app.delete()
            self.problem.app.deploy()
            self.problem.app.start_workload()

        # Hand off to HTTP
        self.submission_stage = "noop"
        print("✅ Environment ready—now POST /submit to grade NO-OP detection.")
        return self.results

    async def ask_env(self, wrapped_cmd: str):
        """
        Grading logic for HTTP /submit:
        parse, run the correct oracle, advance stage, record results.
        """
        from srearena.conductor.parser import ResponseParser

        parser = ResponseParser()

        parsed = parser.parse(wrapped_cmd)
        if parsed["api_name"] != "submit":
            return "[❌] Only `submit(...)` is supported."
        sol = parsed["args"][0] if parsed["args"] else None

        # NO-OP
        if self.submission_stage == "noop":
            r = self.detection_oracle.evaluate(sol)
            self.results["NOOP Detection"] = r
            if r.get("reason") == "Invalid Format":
                return "[⚠️] Invalid NO-OP format."
            with CriticalSection():
                self.problem.inject_fault()
                atexit.register(self.exit_cleanup_and_recover_fault)
            self.submission_stage = "detection"
            return "[✅] NO-OP passed — fault injected. Submit detection."

        # DETECTION
        if self.submission_stage == "detection":
            r = self.detection_oracle.evaluate(sol)
            self.results["Detection"] = r
            self.results["TTD"] = time.time() - self.execution_start_time
            if self.problem.localization_oracle:
                self.submission_stage = "localization"
            elif self.problem.mitigation_oracle:
                self.submission_stage = "mitigation"
            else:
                self.submission_stage = "done"
            return f"[✅] Detection {'successful' if r.get('success') else 'failed'}."

        # LOCALIZATION
        if self.submission_stage == "localization":
            r = self.problem.localization_oracle.evaluate(sol)
            self.results["Localization"] = r
            self.results["TTL"] = time.time() - self.execution_start_time
            self.submission_stage = "mitigation" if self.problem.mitigation_oracle else "done"
            return f"[✅] Localization {'successful' if r.get('success') else 'failed'}."

        # MITIGATION
        if self.submission_stage == "mitigation":
            r = self.problem.mitigation_oracle.evaluate()
            self.results["Mitigation"] = r
            self.results["TTM"] = time.time() - self.execution_start_time
            self.submission_stage = "done"
            return "[✅] Mitigation evaluated."

        return "[✅] All stages completed."

    def exit_cleanup_and_recover_fault(self):
        """Cleanup on exit or SIGINT."""
        try:
            if self.problem:
                self.problem.recover_fault()
                self.problem.app.cleanup()
        except (JSONDecodeError, RuntimeError):
            pass
        self.prometheus.teardown()
        self.kubectl.exec_command("kubectl delete sc openebs-hostpath openebs-device --ignore-not-found")
        self.kubectl.exec_command("kubectl delete -f https://openebs.github.io/charts/openebs-operator.yaml")


def exit_cleanup_fault(conductor):
    conductor.exit_cleanup_and_recover_fault()
