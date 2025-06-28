"""Interface to the Train Ticket application"""

import os
import tempfile
import time
from pathlib import Path

from srearena.paths import TARGET_MICROSERVICES, TRAIN_TICKET_METADATA
from srearena.service.apps.base import Application
from srearena.service.helm import Helm
from srearena.service.kubectl import KubeCtl


class TrainTicket(Application):
    def __init__(self):
        super().__init__(str(TRAIN_TICKET_METADATA))
        self.load_app_json()
        self.kubectl = KubeCtl()
        self.workload_manager = None
        self.create_namespace()

    def load_app_json(self):
        super().load_app_json()
        metadata = self.get_app_json()
        self.frontend_service = None
        self.frontend_port = None

    def deploy(self):
        """Deploy the Helm configurations and flagd infrastructure."""
        if self.namespace:
            self.kubectl.create_namespace_if_not_exist(self.namespace)

        Helm.install(**self.helm_configs)
        self.kubectl.wait_for_job_completion(name="train-ticket-deploy", namespace="train-ticket")

        self._deploy_flagd_infrastructure()
        self._deploy_locust()

    def delete(self):
        """Delete the Helm configurations."""
        # Helm.uninstall(**self.helm_configs) # Don't helm uninstall until cleanup job is fixed on train-ticket
        if self.namespace:
            self.kubectl.delete_namespace(self.namespace)
        self.kubectl.wait_for_namespace_deletion(self.namespace)

    def cleanup(self):
        # Helm.uninstall(**self.helm_configs)
        if self.namespace:
            self.kubectl.delete_namespace(self.namespace)

    def start_workload(self):
        """Start TrainTicket workload using Locust."""
        try:
            from srearena.generators.workload.trainticket_locust import TrainTicketLocustWorkloadManager

            if not self.workload_manager:
                self.workload_manager = TrainTicketLocustWorkloadManager(namespace=self.namespace, kubectl=self.kubectl)

            self.workload_manager.start()
            # Trigger F1 scenario with moderate load
            self.workload_manager.trigger_f1_scenario(user_count=5, spawn_rate=1)
            print("[TrainTicket] Workload started - F1 scenario active")

        except Exception as e:
            print(f"[TrainTicket] Warning: Failed to start workload: {e}")

    def stop_workload(self):
        """Stop the current workload."""
        if self.workload_manager:
            try:
                self.workload_manager.stop_workload()
                print("[TrainTicket] Workload stopped")
            except Exception as e:
                print(f"[TrainTicket] Warning: Failed to stop workload: {e}")

    def _deploy_flagd_infrastructure(self):
        """Deploy flagd service and ConfigMap for fault injection."""
        try:
            flagd_templates_path = TARGET_MICROSERVICES / "train-ticket" / "templates"

            if (flagd_templates_path / "flagd-deployment.yaml").exists():
                result = self.kubectl.exec_command(f"kubectl apply -f {flagd_templates_path / 'flagd-deployment.yaml'}")
                print(f"[TrainTicket] Deployed flagd service: {result}")

            if (flagd_templates_path / "flagd-config.yaml").exists():
                result = self.kubectl.exec_command(f"kubectl apply -f {flagd_templates_path / 'flagd-config.yaml'}")
                print(f"[TrainTicket] Deployed flagd ConfigMap: {result}")

            print(f"[TrainTicket] flagd infrastructure deployed successfully")

        except Exception as e:
            print(f"[TrainTicket] Warning: Failed to deploy flagd infrastructure: {e}")

    def _deploy_locust(self):
        """Deploy Locust load generator from srearena/resources"""
        try:
            # Update path to use srearena/resources instead of aiopslab-applications
            locust_resources_path = Path(__file__).parent.parent.parent / "resources" / "trainticket"

            # Apply Locust configurations
            for file in ["locust-configmap.yaml", "locust-deployment.yaml"]:
                yaml_path = locust_resources_path / file
                if yaml_path.exists():
                    # Need to process the template first
                    with open(yaml_path, "r") as f:
                        content = f.read()
                    # Replace {{ .Values.namespace }} with actual namespace
                    content = content.replace("{{ .Values.namespace }}", self.namespace)

                    # Write to temp file and apply
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
                        tmp.write(content)
                        temp_path = tmp.name

                    result = self.kubectl.exec_command(f"kubectl apply -f {temp_path}")
                    os.unlink(temp_path)
                    print(f"[TrainTicket] Applied {file}: {result}")

            print("[TrainTicket] Locust workload generator deployed")
        except Exception as e:
            print(f"[TrainTicket] Warning: Failed to deploy Locust: {e}")

    def get_flagd_status(self):
        """Check if flagd infrastructure is running."""
        try:
            result = self.kubectl.exec_command(f"kubectl get pods -l app=flagd -n {self.namespace}")
            return "Running" in result
        except Exception:
            return False

    def get_workload_stats(self):
        """Get current workload statistics."""
        if self.workload_manager:
            return self.workload_manager.get_stats()
        return {}


# if __name__ == "__main__":
#     app = TrainTicket()
#     app.deploy()
#     app.delete()
