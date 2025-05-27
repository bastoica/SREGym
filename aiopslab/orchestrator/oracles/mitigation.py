from aiopslab.orchestrator.oracles.base import Oracle


class MitigationOracle(Oracle):
    def evaluate(self) -> dict:
        print("== Mitigation Evaluation ==")

        kubectl = self.problem.kubectl
        namespace = self.problem.namespace
        results = {}

        pod_list = kubectl.list_pods(namespace)
        all_normal = True

        for pod in pod_list.items:
            for container_status in pod.status.container_statuses or []:
                if (
                    container_status.state.waiting
                    and container_status.state.waiting.reason == "CrashLoopBackOff"
                ):
                    print(
                        f"❌ Container {container_status.name} is in CrashLoopBackOff"
                    )
                    all_normal = False
                elif (
                    container_status.state.terminated
                    and container_status.state.terminated.reason != "Completed"
                ):
                    print(
                        f"❌ Container {container_status.name} terminated with reason: {container_status.state.terminated.reason}"
                    )
                    all_normal = False
                elif not container_status.ready:
                    print(f"⚠️ Container {container_status.name} is not ready")
                    all_normal = False

            if not all_normal:
                break

        results["Mitigation Success"] = all_normal
        results["success"] = all_normal
        return results
