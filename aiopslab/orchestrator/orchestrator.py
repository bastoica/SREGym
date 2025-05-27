"""Orchestrator class that interfaces with the agent and the environment."""

import asyncio
import atexit
import inspect
import os
import time

from aiopslab.orchestrator.parser import ResponseParser
from aiopslab.orchestrator.problems.registry import ProblemRegistry
from aiopslab.service.kubectl import KubeCtl
from aiopslab.service.telemetry.prometheus import Prometheus
from aiopslab.utils.critical_section import CriticalSection
from aiopslab.utils.status import SessionPrint, SubmissionStatus


class Orchestrator:
    def __init__(self):
        self.agent = None
        self.agent_name = None
        self.parser = ResponseParser()
        self.problems = ProblemRegistry()
        self.sprint = SessionPrint()
        self.kubectl = KubeCtl()
        self.prometheus = Prometheus()
        self.execution_start_time = None
        self.execution_end_time = None
        self.use_wandb = os.getenv("USE_WANDB", "false").lower() == "true"

        self.problem = None
        self.problem_id = None
        self.submission_stage = (
            "detection"  # → detection → localization → mitigation → done
        )
        self.results = {}

    def register_agent(self, agent, name="agent"):
        self.agent = agent
        self.agent_name = name

    def init_problem(self, problem_id: str):
        self.execution_start_time = time.time()
        self.problem_id = problem_id
        self.problem = self.problems.get_problem_instance(problem_id)

        print(f"[Session Start] Problem ID: {problem_id}")
        print("Setting up OpenEBS...")
        self.kubectl.exec_command(
            "kubectl apply -f https://openebs.github.io/charts/openebs-operator.yaml"
        )
        self.kubectl.exec_command(
            'kubectl patch storageclass openebs-hostpath -p \'{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}\''
        )
        self.kubectl.wait_for_ready("openebs")
        print("OpenEBS setup completed.")

        self.prometheus.deploy()
        self.problem.app.delete()
        self.problem.app.deploy()

        with CriticalSection():
            self.problem.inject_fault()
            atexit.register(exit_cleanup_fault, prob=self.problem)

        if inspect.iscoroutinefunction(self.problem.start_workload):
            asyncio.create_task(self.problem.start_workload())
        else:
            self.problem.start_workload()

        return (
            "Problem loaded.",
            "Use submit(...) when ready.",
            {"submit(...)": "Submit your solution"},
        )

    async def ask_agent(self, input: str):
        return await self.agent.get_action(input)

    async def ask_env(self, input: str):
        try:
            parsed = self.parser.parse(input)
        except Exception as e:
            return str(e)

        if parsed["api_name"] != "submit":
            return "[❌] Only `submit(...)` is supported."

        solution = parsed["args"][0] if parsed["args"] else None
        duration = time.time() - self.execution_start_time

        if self.submission_stage == "detection":
            results = self.problem.detection_oracle.evaluate(solution)
            self.results["Detection"] = results
            self.submission_stage = (
                "localization" if results.get("success") else "mitigation"
            )
            return SubmissionStatus.VALID_SUBMISSION

        elif self.submission_stage == "localization":
            results = self.problem.localization_oracle.evaluate(solution)
            self.results["Localization"] = results
            self.submission_stage = "mitigation"
            return SubmissionStatus.VALID_SUBMISSION

        elif self.submission_stage == "mitigation":
            results = self.problem.mitigation_oracle.evaluate()
            self.results["Mitigation"] = results
            self.submission_stage = "done"
            return SubmissionStatus.VALID_SUBMISSION

        elif self.submission_stage == "done":
            return "[⚠️] Problem already completed."

    async def start_problem(self, max_steps: int = 50):
        instr = "Please take the next action"
        try:
            while self.submission_stage != "done":
                action = await self.ask_agent(instr)
                self.sprint.agent(action)
                env_response = await self.ask_env(action)
                self.sprint.service(env_response)

        except Exception as e:
            with CriticalSection():
                self.problem.recover_fault()
                atexit.unregister(exit_cleanup_fault)
            raise e

        self.execution_end_time = time.time()

        with CriticalSection():
            self.problem.recover_fault()
            atexit.unregister(exit_cleanup_fault)

        self.problem.app.cleanup()
        self.prometheus.teardown()

        self.kubectl.exec_command(
            "kubectl delete sc openebs-hostpath openebs-device --ignore-not-found"
        )
        self.kubectl.exec_command(
            "kubectl delete -f https://openebs.github.io/charts/openebs-operator.yaml"
        )
        self.kubectl.wait_for_namespace_deletion("openebs")

        elapsed = self.execution_end_time - self.execution_start_time
        time_keys = ["TTD", "TTL", "TTA", "TTM"]
        key = next((k for k in time_keys if k in self.results), None)
        overhead = elapsed - self.results.get(key, 0) if key else elapsed
        print(f"Framework overhead: {overhead:.2f}s")

        return {
            "results": self.results,
            "framework_overhead": overhead,
        }


def exit_cleanup_fault(prob):
    print("Recovering fault before exit...")
    prob.recover_fault()
