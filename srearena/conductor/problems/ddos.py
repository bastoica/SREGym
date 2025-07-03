# Fix for your TrafficSpike problem class
from srearena.conductor.oracles.compound import CompoundedOracle
from srearena.conductor.oracles.localization import LocalizationOracle
from srearena.conductor.oracles.mitigation import MitigationOracle
from srearena.conductor.oracles.workload import WorkloadOracle
from srearena.conductor.problems.base import Problem
from srearena.generators.fault.inject_virtual import VirtualizationFaultInjector
from srearena.service.apps.socialnet import SocialNetwork
from srearena.service.kubectl import KubeCtl
from srearena.utils.decorators import mark_fault_injected


class TrafficSpike(Problem):
    def __init__(self, app_name: str = "social_network", faulty_service: str = "user-service"):
        if app_name == "social_network":
            self.app = SocialNetwork()
        else:
            raise ValueError(f"Unsupported app: {app_name}")
        
        self.namespace = self.app.namespace
        self.kubectl = KubeCtl()
        self.faulty_service = faulty_service
        
        self.service_endpoint = self._get_service_endpoint()
        
        super().__init__(app=self.app, namespace=self.namespace)

        self.localization_oracle = LocalizationOracle(problem=self, expected=[self.faulty_service])

        self.app.create_workload()
        self.mitigation_oracle = CompoundedOracle(
            self,
            MitigationOracle(problem=self),
            WorkloadOracle(problem=self, wrk_manager=self.app.wrk),
        )

        self.injector = VirtualizationFaultInjector(namespace=self.namespace)

    def _get_service_endpoint(self) -> str:
        try:
            service = self.kubectl.core_v1_api.read_namespaced_service(
                name=self.faulty_service, 
                namespace=self.namespace
            )
            
            if service.spec.cluster_ip and service.spec.cluster_ip != "None":
                port = service.spec.ports[0].port
                return f"http://{service.spec.cluster_ip}:{port}"
            else:
                return f"http://{self.faulty_service}.{self.namespace}.svc.cluster.local:8080"
                
        except Exception as e:
            print(f"Could not determine service endpoint: {e}")
            return f"http://{self.faulty_service}.{self.namespace}.svc.cluster.local:8080"

    @mark_fault_injected
    def inject_fault(self):
        print(f"Injecting traffic spike on {self.faulty_service}")
        
        self.injector.inject_traffic_spike(
            target_service=self.faulty_service,
            service_endpoint=self.service_endpoint,  
            traffic_intensity=100, 
            duration=60,         
            reduce_resources=True
        )

    @mark_fault_injected
    def recover_fault(self):
        print("Recovering from traffic spike...")
        
        self.injector.recover_traffic_spike(
            target_service=self.faulty_service,
            target_replicas=5,
            restore_resources=True
        )


def inject_traffic_spike_updated(
    self,
    target_service: str,
    service_endpoint: str = None,
    traffic_intensity: int = 100,
    duration: int = 60,
    reduce_resources: bool = True
):
    
    print(f"Injecting traffic spike: {traffic_intensity} req/s for {duration}s")
    
    if service_endpoint is None:
        service_endpoint = f"http://{target_service}.{self.namespace}.svc.cluster.local:8080"
    
    print(f"Target endpoint: {service_endpoint}")
    
    if reduce_resources:
        self._reduce_service_resources(target_service)
        import time
        time.sleep(30)
    
    self._start_traffic_generation(service_endpoint, traffic_intensity, duration)


def inject_traffic_spike_kubectl(
    self,
    target_service: str,
    traffic_intensity: int = 100,
    duration: int = 60,
    reduce_resources: bool = True
):
    
    print(f"Injecting traffic spike: {traffic_intensity} req/s for {duration}s on {target_service}")
    
    if reduce_resources:
        self._reduce_service_resources(target_service)
        # Wait for deployment to roll out
        import time
        time.sleep(30)
    
    self._create_load_generator(target_service, traffic_intensity, duration)

def recover_traffic_spike_kubectl(
    self,
    target_service: str,
    target_replicas: int = 5,
    restore_resources: bool = True
):
    
    print(f"Recovering from traffic spike for {target_service}")
    
    self.kubectl.exec_command(f"kubectl delete pods -l app=load-generator -n {self.namespace} --ignore-not-found")
    
    self.kubectl.exec_command(
        f"kubectl scale deployment {target_service} --replicas={target_replicas} -n {self.namespace}"
    )
    print(f"Scaled {target_service} to {target_replicas} replicas")
    
    if restore_resources:
        self._restore_service_resources(target_service)
    
    self.kubectl.wait_for_stable(self.namespace)
    print(f"Recovery completed for {target_service}")