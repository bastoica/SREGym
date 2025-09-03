from srearena.conductor.oracles.localization import LocalizationOracle
from srearena.conductor.oracles.rolling_update_misconfiguration_mitigation import RollingUpdateMitigationOracle
from srearena.conductor.problems.base import Problem
from srearena.generators.fault.inject_virtual import VirtualizationFaultInjector
from srearena.service.apps.hotel_reservation import HotelReservation
from srearena.service.apps.social_network import SocialNetwork
from srearena.service.kubectl import KubeCtl
from srearena.utils.decorators import mark_fault_injected


class RollingUpdateMisconfigured(Problem):
    def __init__(self, app_name: str = "social_network"):
        self.faulty_service = "custom-service"
        self.app_name = app_name

        if self.app_name == "social_network":
            self.app = SocialNetwork()
        elif self.app_name == "hotel_reservation":
            self.app = HotelReservation()
        else:
            raise ValueError(f"Unsupported app name: {app_name}")

        super().__init__(app=self.app, namespace=self.app.namespace)

        self.kubectl = KubeCtl()
        self.localization_oracle = LocalizationOracle(problem=self, expected=[self.faulty_service])

        self.app.create_workload()
        self.mitigation_oracle = RollingUpdateMitigationOracle(problem=self, deployment_name=self.faulty_service)

    @mark_fault_injected
    def inject_fault(self):
        print("== Fault Injection ==")
        injector = VirtualizationFaultInjector(namespace=self.namespace)
        injector._inject(fault_type="rolling_update_misconfigured", microservices=[self.faulty_service])

        print(f"Service: {self.faulty_service} | Namespace: {self.namespace}")

    @mark_fault_injected
    def recover_fault(self):
        print("== Fault Recovery ==")
        injector = VirtualizationFaultInjector(namespace=self.namespace)
        injector._recover(fault_type="rolling_update_misconfigured", microservices=[self.faulty_service])
        print(f"Service: {self.faulty_service} | Namespace: {self.namespace}")
