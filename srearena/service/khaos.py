import json
import textwrap

from srearena.service.kubectl import KubeCtl

KHAOS_NS = "khaos"
KHAOS_DS_NAME = "khaos"

# DaemonSet that runs one privileged Khaos pod per amd64 node
# If you also deploy arm64 nodes later, create a second DS or use a multi-arch image.
KHAOS_DAEMONSET_YAML = textwrap.dedent(
    f"""
apiVersion: v1
kind: Namespace
metadata:
  name: {KHAOS_NS}
---
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: {KHAOS_DS_NAME}
  namespace: {KHAOS_NS}
spec:
  selector:
    matchLabels:
      app: khaos
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        app: khaos
    spec:
      hostPID: true
      hostNetwork: true
      tolerations:
        - key: "node-role.kubernetes.io/control-plane"
          operator: "Exists"
          effect: "NoSchedule"
        - key: "node-role.kubernetes.io/master"
          operator: "Exists"
          effect: "NoSchedule"
      nodeSelector:
        kubernetes.io/arch: amd64
      containers:
        - name: khaos
          image: dahyeonh0420/khaos-x86:latest
          imagePullPolicy: IfNotPresent
          command: ["sleep", "infinity"]  # keep it running; we'll exec /khaos/khaos
          securityContext:
            privileged: true
          volumeMounts:
            - name: sys-bpf
              mountPath: /sys/fs/bpf
            - name: sys-debug
              mountPath: /sys/kernel/debug
            - name: host-proc
              mountPath: /host/proc
              readOnly: true
            - name: lib-modules
              mountPath: /lib/modules
              readOnly: true
            - name: btf
              mountPath: /sys/kernel/btf
              readOnly: true
      volumes:
        - name: sys-bpf
          hostPath:
            path: /sys/fs/bpf
            type: Directory
        - name: sys-debug
          hostPath:
            path: /sys/kernel/debug
            type: Directory
        - name: host-proc
          hostPath:
            path: /proc
            type: Directory
        - name: lib-modules
          hostPath:
            path: /lib/modules
            type: Directory
        - name: btf
          hostPath:
            path: /sys/kernel/btf
            type: DirectoryOrCreate
"""
).strip()


class KhaosController:
    """
    Minimal controller to deploy Khaos and inject/recover faults.

    Assumptions:
      - Your Problem implementation will provide:
          * the target node name
          * the target *host* PID to inject against
      - Your Khaos image is x86-only (amd64). We select nodes accordingly.
      - KubeCtl.exec_command(cmd) runs a shell command and returns (stdout, stderr, rc) or text.
    """

    def __init__(self, kubectl: KubeCtl):
        self.kubectl = kubectl

    # ---------- Deploy / Teardown ----------

    def ensure_deployed(self):
        # idempotent apply
        self.kubectl.exec_command(f"kubectl apply -f - <<'EOF'\n{KHAOS_DAEMONSET_YAML}\nEOF")
        # wait until DaemonSet pods are ready
        self.kubectl.exec_command(f"kubectl -n {KHAOS_NS} rollout status ds/{KHAOS_DS_NAME} --timeout=3m")

    def teardown(self):
        self.kubectl.exec_command(f"kubectl delete ns {KHAOS_NS} --ignore-not-found")

    # ---------- Helpers ----------

    def _khaos_pod_on_node(self, node_name: str) -> str:
        out = self.kubectl.exec_command(f"kubectl -n {KHAOS_NS} get pods -o json")
        if isinstance(out, tuple):
            out = out[0]
        data = json.loads(out)
        for item in data.get("items", []):
            if item.get("spec", {}).get("nodeName") == node_name and item.get("status", {}).get("phase") == "Running":
                return item["metadata"]["name"]
        raise RuntimeError(f"No running Khaos pod on node {node_name}")

    # ---------- Public API ----------

    def inject(self, node_name: str, fault_name: str, host_pid: int):
        """
        Run:  /khaos/khaos <fault_name> <pid>
        inside the Khaos pod on the specified node.
        """
        pod = self._khaos_pod_on_node(node_name)
        cmd = f"kubectl -n {KHAOS_NS} exec {pod} -- /khaos/khaos {fault_name} {host_pid}"
        out = self.kubectl.exec_command(cmd)
        return out

    def recover(self, node_name: str, fault_name: str):
        pod = self._khaos_pod_on_node(node_name)
        cmd = f"kubectl -n {KHAOS_NS} exec {pod} -- /khaos/khaos --recover {fault_name}"
        out = self.kubectl.exec_command(cmd)
        return out
