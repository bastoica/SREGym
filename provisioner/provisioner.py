import datetime
import html
import json
import random
import warnings
import geni.util
from geni.aggregate.cloudlab import Clemson, Utah, Wisconsin
import requests
from bs4 import BeautifulSoup
import geni.portal as portal
from provisioner.utils.logger import logger
from provisioner.utils.parser import parse_sliver_info, collect_and_parse_hardware_info
from provisioner.config.settings import (
    AGGREGATES_MAP,
    PRIORITY_HARDWARE_TYPES,
    DefaultSettings,
)

warnings.filterwarnings("ignore", category=UserWarning)


class CloudlabProvisioner:
    def __init__(self, context_path: str):
        self.context = geni.util.loadContext(path=context_path)
        self.project = self.context.cf.project
        self.framework = self.context.cf.name
        self.cert_path = self.context.cf.cert
        self.key_path = self.context.cf.key
        self.user_name = self.context.uname
        self.user_urn = list(self.context._users)[0].urn
        self.user_pubkeypath = self.context.cf._key

    def get_aggregate(self, aggregate_name: str):
        return AGGREGATES_MAP[aggregate_name.lower()]

    def get_aggregate_version(self, aggregate_name: str):
        aggregate = self.get_aggregate(aggregate_name)
        return aggregate.getversion(context=self.context)

    def get_all_hardware_info(self, hardware_type: str):
        all_hardware_list = collect_and_parse_hardware_info()
        hardware_list = []
        for hardware in all_hardware_list:
            if hardware["hardware_name"] == hardware_type:
                hardware_list.append(hardware)
        return hardware_list

    def print_all_hardware_info(self):
        hardware_list = collect_and_parse_hardware_info()
        print(
            f"{'Hardware Name':<20} | {'Cluster Name':<30} | {'Total':<7} | {'Free':<7}"
        )
        print("-" * 100)
        for hardware in hardware_list:
            print(
                f"{hardware['hardware_name']:<20} | {hardware['cluster_name']:<30} | {hardware['total']:<7} | {hardware['free']:<7}"
            )

    def get_hardware_available_aggregate_name(
        self, hardware_type: str, node_count: int
    ):
        hardware_list = self.get_all_hardware_info(hardware_type)
        aggregate_name = None

        for hardware in hardware_list:
            if (
                hardware["hardware_name"] == hardware_type
                and hardware["free"] >= node_count
            ):
                aggregate_name = hardware["cluster_name"].lower()
                break

        if not aggregate_name:
            logger.error("Error: Requested hardware is not available")
            return None

        return aggregate_name

    def generate_slice_name(self):
        return f"test-{random.randint(100000, 999999)}"

    def create_slice(
        self, slice_name: str, duration: float, description: str = "Cloudlab Experiment"
    ):
        try:
            expiration = datetime.datetime.now() + datetime.timedelta(hours=duration)
            res = self.context.cf.createSlice(
                self.context, slice_name, exp=expiration, desc=description
            )
            return res
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    def create_sliver(self, slice_name: str, rspec_file: str, aggregate_name: str):
        try:
            aggregate = self.get_aggregate(aggregate_name)
            igm = aggregate.createsliver(self.context, slice_name, rspec_file)
            geni.util.printlogininfo(manifest=igm)

            login_info = geni.util._corelogininfo(igm)
            return login_info
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    def create_rspec(
        self,
        hardware_type: str = DefaultSettings.DEFAULT_HARDWARE_TYPE,
        os_type: str = DefaultSettings.DEFAULT_OS_TYPE,
        node_count: int = DefaultSettings.DEFAULT_NODE_COUNT,
    ):
        os_url = f"urn:publicid:IDN+emulab.net+image+emulab-ops//{os_type}"

        rspec = portal.context.makeRequestRSpec()

        nodes = []
        nodes.append(rspec.RawPC("control"))
        for i in range(1, node_count):
            nodes.append(rspec.RawPC(f"compute{i}"))

        for node in nodes:
            node.hardware_type = hardware_type
            node.disk_image = os_url

        link = rspec.Link(members=nodes)

        return rspec

    def create_experiment(
        self,
        duration: float = DefaultSettings.DEFAULT_DURATION,
        description: str = DefaultSettings.DEFAULT_DESCRIPTION,
        hardware_type: str = DefaultSettings.DEFAULT_HARDWARE_TYPE,
        os_type: str = DefaultSettings.DEFAULT_OS_TYPE,
        node_count: int = DefaultSettings.DEFAULT_NODE_COUNT,
    ):
        slice_name = self.generate_slice_name()

        for i in range(100):
            slice_info = self.create_slice(slice_name, duration, description)
            if slice_info:
                break

        if not slice_info:
            logger.error("Error: Failed to create slice")
            return None

        # TODO: Save the slice info in a database for now save it in a file
        with open(f"{slice_name}.slice.info.txt", "w") as f:
            f.write(f"Slice Name: {slice_name}\n")
            f.write(f"Duration: {duration}\n")
            f.write(f"Description: {description}\n")
            f.write(f"Slice Info: {json.dumps(slice_info, indent=4)}\n")

        logger.info(
            f"Slice Successfully created: {slice_name}, duration: {duration}, description: {description}"
        )
        logger.info(f"Slice Info: {slice_info}")

        for i, hardware_type in enumerate(PRIORITY_HARDWARE_TYPES):
            aggregate_name = self.get_hardware_available_aggregate_name(
                hardware_type, node_count
            )

            rspec_file = self.create_rspec(hardware_type, os_type, node_count)
            login_info = self.create_sliver(slice_name, rspec_file, aggregate_name)

            if login_info:
                break

        if not login_info:
            logger.error("Error: Requested hardware is not available")
            return None

        # TODO: Save the sliver and login info in a database for now save it in a file
        with open(f"{slice_name}.sliver.info.txt", "w") as f:
            f.write(f"Slice Name: {slice_name}\n")
            f.write(f"Aggregate: {aggregate_name}\n")
            f.write(f"Duration: {duration}\n")
            f.write(f"Description: {description}\n")
            f.write(f"Hardware Type: {hardware_type}\n")
            f.write(f"OS Type: {os_type}\n")
            f.write(f"Node Count: {node_count}\n")
            f.write(f"Login Info: {json.dumps(login_info, indent=4)}\n")

        logger.info(
            f"Experiment Successfully created: {slice_name}, duration: {duration}, description: {description}, hardware_type: {hardware_type}, os_type: {os_type}, node_count: {node_count}"
        )

        return True

    def delete_experiment(self, slice_name: str, aggregate_name: str):
        try:
            aggregate = self.get_aggregate(aggregate_name)
            aggregate.deletesliver(self.context, slice_name)
            return True
        except Exception as e:
            logger.error(f"Error: {e}")
            return False

    # TODO: check the return of renewSlice
    def renew_slice(self, slice_name: str, duration: float):
        try:
            new_expiration = datetime.datetime.now() + datetime.timedelta(
                hours=duration
            )
            ret = self.context.cf.renewSlice(self.context, slice_name, new_expiration)
            print(ret)
            return True
        except Exception as e:
            logger.error(f"Error: {e}")
            return False

    # TODO: check the return of renewSliver
    def renew_sliver(self, slice_name: str, aggregate_name: str, duration: float):
        try:
            aggregate = self.get_aggregate(aggregate_name)
            new_expiration = datetime.datetime.now() + datetime.timedelta(
                hours=duration
            )
            ret = aggregate.renewsliver(self.context, slice_name, new_expiration)
            print(ret)
            return True
        except Exception as e:
            logger.error(f"Error: {e}")
            return False

    def get_sliver_status(self, slice_name: str, aggregate_name: str):
        try:
            aggregate = self.get_aggregate(aggregate_name)
            sliver_info = aggregate.getsliver(self.context, slice_name)
            return sliver_info
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    def get_sliver_spec(self, slice_name: str, aggregate_name: str):
        try:
            aggregate = self.get_aggregate(aggregate_name)
            sliver_spec = aggregate.getsliver(self.context, slice_name)
            return sliver_spec
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    def print_experiment_spec(self, slice_name: str, aggregate_name: str):
        sliver_spec = self.get_sliver_spec(slice_name, aggregate_name)
        try:
            print("\nExperiment Information:")
            print(f"Description: {sliver_spec['description']}")
            print(f"Expiration: {sliver_spec['expiration']}")

            print("\nNodes:")
            for node in sliver_spec["nodes"]:
                print(f"\nNode: {node['client_id']}")
                print(f"  Hostname: {node['hostname']}")
                print(f"  Public IP: {node['public_ip']}")
                print(f"  Internal IP: {node['internal_ip']}")
                print(f"  Hardware: {node['hardware']}")
                print(f"  OS Image: {node['os_image']}")

            print("\nLocation:")
            print(f"  Country: {sliver_spec['location']['country']}")
            print(f"  Latitude: {sliver_spec['location']['latitude']}")
            print(f"  Longitude: {sliver_spec['location']['longitude']}")
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    def list_slices(self):
        try:
            slices = self.context.cf.listSlices(self.context)
            return slices
        except Exception as e:
            logger.error(f"Error: {e}")
            return None
