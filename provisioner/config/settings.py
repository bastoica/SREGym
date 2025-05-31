import os
from pathlib import Path
from dotenv import load_dotenv
from geni.aggregate.cloudlab import Clemson, Utah, Wisconsin

load_dotenv(override=True)

# Default settings
class DefaultSettings:
    DEFAULT_HARDWARE_TYPE = "c220g5"
    DEFAULT_OS_TYPE = "UBUNTU22-64-STD"
    DEFAULT_NODE_COUNT = 2
    DEFAULT_DURATION = 1  # (hours)
    DEFAULT_DESCRIPTION = "Cloudlab Experiment"


# Aggregates mapping
AGGREGATES_MAP = {
    "clemson": Clemson,
    "utah": Utah,
    "wisconsin": Wisconsin,
    "cloudlab clemson": Clemson,
    "cloudlab utah": Utah,
    "cloudlab wisconsin": Wisconsin,
    "cl-clemson": Clemson,
    "cl-wisconsin": Wisconsin,
    "cl-utah": Utah,
}

# Hardware types
PRIORITY_HARDWARE_TYPES = ["c220g5", "c220g4", "c220g3", "c220g2", "c220g1"]

# OS types
OS_TYPES = [
    "UBUNTU22-64-STD",
    "UBUNTU20-64-STD",
    "UBUNTU18-64-STD",
    "UBUNTU16-64-STD",
    "DEBIAN11-64-STD",
    "DEBIAN10-64-STD",
    "FEDORA36-64-STD",
    "CENTOS7-64-STD",
    "CENTOS8-64-STD",
    "RHEL8-64-STD",
]
