from srearena.conductor.oracles.compound import CompoundedOracle
from srearena.conductor.oracles.localization import LocalizationOracle
from srearena.conductor.oracles.mitigation import MitigationOracle
from srearena.conductor.oracles.workload import WorkloadOracle
from srearena.conductor.problems.base import Problem
from srearena.generators.fault.inject_virtual import VirtualizationFaultInjector
from srearena.service.apps.socialnet import SocialNetwork
from srearena.service.kubectl import KubeCtl
from srearena.utils.decorators import mark_fault_injected
import threading
import time
import requests
import json


class TrafficSpike(Problem):
    def __init__(self):
        self.app = SocialNetwork()
        self.namespace = self.app.namespace
        self.kubectl = KubeCtl()

        self.faulty_service = "user-service"
        
        self.traffic_intensity = 1000  
        self.traffic_duration = 300 
        self.traffic_threads = []
        self.stop_traffic = False
        
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
            
            if service.status.load_balancer.ingress:
                ip = service.status.load_balancer.ingress[0].ip
                port = service.spec.ports[0].port
                return f"http://{ip}:{port}"
            elif service.spec.type == "NodePort":
                nodes = self.kubectl.core_v1_api.list_node().items
                node_ip = nodes[0].status.addresses[0].address
                node_port = service.spec.ports[0].node_port
                return f"http://{node_ip}:{node_port}"
            else:
                cluster_ip = service.spec.cluster_ip
                port = service.spec.ports[0].port
                return f"http://{cluster_ip}:{port}"
        except Exception as e:
            print(f"Could not determine service endpoint: {e}")
            return f"http://{self.faulty_service}.{self.namespace}.svc.cluster.local:8080"

    def _generate_traffic_worker(self, worker_id: int, requests_per_worker: int):
        session = requests.Session()
        successful_requests = 0
        failed_requests = 0
        
        for i in range(requests_per_worker):
            if self.stop_traffic:
                break
                
            try:
                endpoints = ["/", "/api/user/timeline", "/api/user/profile", "/api/post/compose"]
                endpoint = endpoints[i % len(endpoints)]
                
                response = session.get(f"{self.service_endpoint}{endpoint}", timeout=5)
                if response.status_code == 200:
                    successful_requests += 1
                else:
                    failed_requests += 1
            except Exception as e:
                failed_requests += 1
            
            time.sleep(0.001)
        
        print(f"Worker {worker_id}: {successful_requests} successful, {failed_requests} failed requests")

    @mark_fault_injected
    def inject_fault(self):
        print(f"Starting traffic spike attack on {self.faulty_service}")
        print(f"Target: {self.service_endpoint}")
        print(f"Intensity: {self.traffic_intensity} requests/second for {self.traffic_duration} seconds")
        
        self.stop_traffic = False
        
        num_workers = 20 
        requests_per_worker = (self.traffic_intensity * self.traffic_duration) // num_workers
        
        for i in range(num_workers):
            thread = threading.Thread(
                target=self._generate_traffic_worker,
                args=(i + 1, requests_per_worker),
                daemon=True
            )
            thread.start()
            self.traffic_threads.append(thread)
        
        self._reduce_resource_limits()
        
        print("Traffic spike initiated. Service should start experiencing high load...")

    def _reduce_resource_limits(self):
        """Reduce resource limits to make the service more vulnerable to traffic spikes."""
        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{
                            "name": self.faulty_service,
                            "resources": {
                                "limits": {
                                    "cpu": "100m",      
                                    "memory": "128Mi"   
                                },
                                "requests": {
                                    "cpu": "50m",
                                    "memory": "64Mi"
                                }
                            }
                        }]
                    }
                }
            }
        }
        
        try:
            self.kubectl.apps_v1_api.patch_namespaced_deployment(
                name=self.faulty_service,
                namespace=self.namespace,
                body=patch
            )
            print(f"Reduced resource limits for {self.faulty_service}")
            
            self.kubectl.exec_command(
                f"kubectl rollout restart deployment {self.faulty_service} -n {self.namespace}"
            )
            
        except Exception as e:
            print(f"Failed to reduce resource limits: {e}")

    @mark_fault_injected
    def recover_fault(self):
        print("Starting fault recovery for traffic spike...")
        
        self.stop_traffic = True
        
        for thread in self.traffic_threads:
            thread.join(timeout=5)
        self.traffic_threads.clear()
        
        self._scale_up_service()
        
        self._restore_resource_limits()
        
        self.kubectl.wait_for_stable(self.namespace)
        
        print("Traffic spike recovery completed")

    def _scale_up_service(self):
        patch = {
            "spec": {
                "replicas": 5 
            }
        }
        
        try:
            self.kubectl.apps_v1_api.patch_namespaced_deployment(
                name=self.faulty_service,
                namespace=self.namespace,
                body=patch
            )
            print(f"Scaled up {self.faulty_service} to 5 replicas")
            
        except Exception as e:
            print(f"Failed to scale up service: {e}")

    def _restore_resource_limits(self):
        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{
                            "name": self.faulty_service,
                            "resources": {
                                "limits": {
                                    "cpu": "500m",     
                                    "memory": "512Mi"  
                                },
                                "requests": {
                                    "cpu": "200m",
                                    "memory": "256Mi"
                                }
                            }
                        }]
                    }
                }
            }
        }
        
        try:
            self.kubectl.apps_v1_api.patch_namespaced_deployment(
                name=self.faulty_service,
                namespace=self.namespace,
                body=patch
            )
            print(f"Restored resource limits for {self.faulty_service}")
            
            self.kubectl.exec_command(
                f"kubectl rollout restart deployment {self.faulty_service} -n {self.namespace}"
            )
            
        except Exception as e:
            print(f"Failed to restore resource limits: {e}")