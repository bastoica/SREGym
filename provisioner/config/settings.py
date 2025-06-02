import os
from pathlib import Path
from dotenv import load_dotenv
from geni.aggregate.cloudlab import Clemson, Utah, Wisconsin

load_dotenv(override=True)


# Default settings
class DefaultSettings:
    DEFAULT_HARDWARE_TYPE = "c220g5"
    DEFAULT_OS_TYPE = "UBUNTU22-64-STD"
    DEFAULT_NODE_COUNT = 3
    DEFAULT_DURATION_HOURS = 1
    DEFAULT_DESCRIPTION = "Cloudlab Experiment"

    MIN_AVAILABLE_CLUSTERS = 2
    MAX_TOTAL_CLUSTERS = 8
    MAX_CLUSTERS_PER_USER = 2
    UNCLAIMED_CLUSTER_TIMEOUT_HOURS = 16
    CLAIMED_CLUSTER_DEFAULT_DURATION_HOURS = 7 * 24
    CLAIMED_CLUSTER_INACTIVITY_TIMEOUT_HOURS = 48

    DATABASE_PATH = "database.sqlite3"

    DEFAULT_SSH_TIME_OUT_SECONDS = 300  # (seconds)

    LOG_LEVEL = "INFO"
    LOG_FILE = "provisioner.log"

    #### Provisioner Credentials ####
    PROVISIONER_SSH_PRIVATE_KEY_PATH = "/home/pial/.ssh/id_cl"
    PROVISIONER_DEFAULT_SSH_USERNAME = "Pial"
    CLOUDLAB_CONTEXT_PATH = "~/Academics/UIUC/Projects/SREAreana/provisioner/context.json"


    #### Daemon Settings ####
    SCHEDULER_INTERVAL_MINUTES = 10



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

# The first error means deletion not successful have to retry
# The second error means experiment does not exist maybe already deleted and no need to retry
DELETE_EXPERIMENT_ERRORS = [
    "resource is busy; try again later",  # -> retry
    "No such slice here",  # -> no need to retry
]
