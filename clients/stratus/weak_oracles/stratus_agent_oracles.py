from clients.stratus.weak_oracles.cluster_state import validate_cluster_status


class StratusAgentOracles:
    def __init__(self, namespace="default"):
        self.namespace = namespace

    def validate(self):
        return validate_cluster_status(self.namespace)
