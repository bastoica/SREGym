import logging
from typing import Any, override

from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

from sregym.conductor.oracles.localization_oracle import LocalizationOracle

local_logger = logging.getLogger("all.sregym.localization_oracle")
local_logger.propagate = True
local_logger.setLevel(logging.DEBUG)


class LatentSectorErrorLocalizationOracle(LocalizationOracle):
    """
    Localization oracle for latent sector error problems.
    Identifies the MongoDB deployment affected by the storage fault.
    """

    def __init__(self, problem, namespace: str, expected_deployment_name: str):
        super().__init__(problem, namespace)
        self.expected_deployment_name = expected_deployment_name

    @override
    def expect(self):
        """
        Returns the UID of the expected deployment affected by latent sector errors.
        """
        uid = self.deployment_uid(self.expected_deployment_name, self.namespace)
        return [uid]  # Return as list for consistency with other oracles

