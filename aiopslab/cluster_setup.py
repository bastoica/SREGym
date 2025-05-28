import yaml
import subprocess
from remote import RemoteExecutor

def load_config(path="config.yml"):
    with open(path) as f:
        return yaml.safe_load(f)

def nodes_reachable(cloud_cfg):
    for ip in cloud_cfg["nodes"]:
        try:
            r = RemoteExecutor(ip, cloud_cfg["ssh_user"], cloud_cfg["ssh_key"])
            r.close()
        except Exception:
            return False
    return True

def install_k8s_components(runner: RemoteExecutor):
    steps = [
        "sudo swapoff -a",
        "sudo modprobe br_netfilter",
        "echo 'net.bridge.bridge-nf-call-iptables=1' | sudo tee /etc/sysctl.d/k8s.conf",
        "sudo sysctl --system",
        "sudo apt-get update",
        "sudo apt-get install -y containerd kubeadm kubelet kubectl",
    ]
    for cmd in steps:
        code, out, err = runner.exec(cmd)
        if code != 0:
            raise RuntimeError(f"[{runner.host}] `{cmd}` failed: {err}")

def init_master(runner: RemoteExecutor, cidr: str) -> str:
    """Initialize control-plane and return the `kubeadm join` command."""
    cmd = f"sudo kubeadm init --pod-network-cidr={cidr} --upload-certs"
    code, out, err = runner.exec(cmd)
    if code != 0:
        raise RuntimeError(f"[{runner.host}] kubeadm init failed: {err}")

    join_cmd = next(
        (line for line in out.splitlines() if line.strip().startswith("kubeadm join")),
        None,
    )
    if not join_cmd:
        raise RuntimeError("Failed to parse join command from init output")

    runner.exec("mkdir -p $HOME/.kube")
    runner.exec("sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config")
    runner.exec("sudo chown $(id -u):$(id -g) $HOME/.kube/config")

    runner.exec(
        "kubectl apply -f https://projectcalico.docs.tigera.io/manifests/calico.yaml"
    )
    return join_cmd

def join_worker(runner: RemoteExecutor, join_cmd: str):
    code, out, err = runner.exec(f"sudo {join_cmd}")
    if code != 0:
        raise RuntimeError(f"[{runner.host}] kubeadm join failed: {err}")

def setup_cloudlab_cluster(cfg):
    cloud = cfg["cloudlab"]
    cidr = cfg["pod_network_cidr"]

    # Install on all nodes
    executors = []
    for ip in cloud["nodes"]:
        r = RemoteExecutor(ip, cloud["ssh_user"], cloud["ssh_key"])
        install_k8s_components(r)
        executors.append(r)

    # Init on the first node
    master = executors[0]
    join_cmd = init_master(master, cidr)

    for worker in executors[1:]:
        join_worker(worker, join_cmd)

    for r in executors:
        r.close()

    code, out, err = RemoteExecutor(
        cloud["nodes"][0], cloud["ssh_user"], cloud["ssh_key"]
    ).exec("kubectl get nodes --no-headers")
    print("Cluster nodes:\n", out)

def setup_kind_cluster(cfg):
    kind_cfg = cfg["kind"]
    cfg_file = kind_cfg["kind_config_arm"]  # adjust if you need x86
    print("CloudLab unreachable; falling back to Kind.")
    subprocess.run(["kind", "create", "cluster", "--config", cfg_file], check=True)
    print("Kind cluster created.")

def main():
    cfg = load_config()
    if cfg["mode"] == "cloudlab" and nodes_reachable(cfg["cloudlab"]):
        setup_cloudlab_cluster(cfg)
    else:
        setup_kind_cluster(cfg)

if __name__ == "__main__":
    main()
