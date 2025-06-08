#!/usr/bin/env python3
"""
GENI / CloudLab experiment management CLI - Fixed Version
"""
# ──────────────────────────────────────────────────────────────────────────────
# 0. make repo root importable
# ──────────────────────────────────────────────────────────────────────────────
import sys
from pathlib import Path
import warnings

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ──────────────────────────────────────────────────────────────────────────────
# 1. stdlib + third-party
# ──────────────────────────────────────────────────────────────────────────────
import argparse
import datetime
import json
import random
import re
import time

import geni.portal as portal
import geni.util
from geni.aggregate.cloudlab import Clemson, Utah, Wisconsin
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding import KeyBindings

from provisioner.utils.parser import parse_sliver_info, collect_and_parse_hardware_info

warnings.filterwarnings("ignore")

# List of available OS types
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


def validate_hours(value):
    float_value = float(value)
    if float_value <= 0:
        raise argparse.ArgumentTypeError("Hours must be greater than 0")
    return float_value


def create_slice(context, args):
    try:
        print(f"Creating slice '{args.slice_name}'...")
        expiration = datetime.datetime.now() + datetime.timedelta(hours=args.hours)
        res = context.cf.createSlice(
            context, args.slice_name, exp=expiration, desc=args.description
        )
        print(f"Slice Info: \n{json.dumps(res, indent=2)}")
        print(f"Slice '{args.slice_name}' created")
    except Exception as e:
        print(f"Error: {e}")


def create_sliver(context, args):
    try:
        print(f"Creating sliver in slice '{args.slice_name}'...")
        aggregate = get_aggregate(args.site)
        igm = aggregate.createsliver(context, args.slice_name, args.rspec_file)
        geni.util.printlogininfo(manifest=igm)

        # Save the login info to a file
        login_info = geni.util._corelogininfo(igm)
        if isinstance(login_info, list):
            login_info = "\n".join(map(str, login_info))
        with open(f"{args.slice_name}.login.info.txt", "w") as f:
            f.write(f"Slice name: {args.slice_name}\n")
            f.write(f"Cluster name: {aggregate.name}\n")
            f.write(login_info)

        print(f"Sliver '{args.slice_name}' created")
    except Exception as e:
        print(f"Error: {e}")


def get_sliver_status(context, args):
    try:
        print("Checking sliver status...")
        aggregate = get_aggregate(args.site)
        status = aggregate.sliverstatus(context, args.slice_name)
        print(f"Status: {json.dumps(status, indent=2)}")
    except Exception as e:
        print(f"Error: {e}")


def renew_slice(context, args):
    try:
        print("Renewing slice...")
        new_expiration = datetime.datetime.now() + datetime.timedelta(hours=args.hours)
        context.cf.renewSlice(context, args.slice_name, new_expiration)
        print(f"Slice '{args.slice_name}' renewed")
    except Exception as e:
        print(f"Error: {e}")


def renew_sliver(context, args):
    try:
        print("Renewing sliver...")
        aggregate = get_aggregate(args.site)
        new_expiration = datetime.datetime.now() + datetime.timedelta(hours=args.hours)
        aggregate.renewsliver(context, args.slice_name, new_expiration)
        print(f"Sliver '{args.slice_name}' renewed")
    except Exception as e:
        print(f"Error: {e}")


def list_slices(context, args):
    try:
        print("Listing slices...")
        res = context.cf.listSlices(context)
        print(json.dumps(res, indent=2))
    except Exception as e:
        print(f"Error: {e}")


def list_sliver_spec(context, args):
    try:
        print("Listing slivers...")
        aggregate = get_aggregate(args.site)
        res = aggregate.listresources(context, args.slice_name, available=True)

        # Parse and display the information
        sliver_info = parse_sliver_info(res.text)

        print("\nExperiment Information:")
        print(f"Description: {sliver_info['description']}")
        print(f"Expiration: {sliver_info['expiration']}")

        print("\nNodes:")
        for node in sliver_info["nodes"]:
            print(f"\nNode: {node['client_id']}")
            print(f"  Hostname: {node['hostname']}")
            print(f"  Public IP: {node['public_ip']}")
            print(f"  Internal IP: {node['internal_ip']}")
            print(f"  Hardware: {node['hardware']}")
            print(f"  OS Image: {node['os_image']}")

        print("\nLocation:")
        print(f"  Country: {sliver_info['location']['country']}")
        print(f"  Latitude: {sliver_info['location']['latitude']}")
        print(f"  Longitude: {sliver_info['location']['longitude']}")
    except Exception as e:
        print(f"Error: {e}")


def delete_sliver(context, args):
    try:
        print(f"Deleting sliver '{args.slice_name}'...")
        aggregate = get_aggregate(args.site)
        aggregate.deletesliver(context, args.slice_name)
        print(f"Sliver '{args.slice_name}' deleted.")
    except Exception as e:
        print(f"Error: {e}")


def get_aggregate(site):
    sites = {"utah": Utah, "clemson": Clemson, "wisconsin": Wisconsin}
    return sites.get(site.lower(), Utah)


def get_hardware_info(context=None, args=None):
    hardware_info_list = collect_and_parse_hardware_info()
    if hardware_info_list:
        print(
            f"\n{'Hardware Name':<20} | {'Cluster Name':<30} | {'Total':<7} | {'Free':<7}"
        )
        print("-" * 100)

        for item in hardware_info_list:
            if item["total"] > 0 or item["free"] > 0:
                print(
                    f"{item['hardware_name']:<20} | {item['cluster_name']:<30} | {item['total']:<7} | {item['free']:<7}"
                )
    else:
        print("No hardware information available")


# Kubernetes bootstrapper
from cluster_setup import setup_cloudlab_cluster


# ╭──────────────────────────────────────────────────────────────────────────╮
# │  CLI configuration                                                      │
# ╰──────────────────────────────────────────────────────────────────────────╯
parser = argparse.ArgumentParser("genictl", description="GENI / CloudLab CLI")
sub = parser.add_subparsers(dest="cmd", required=True)

# quick-experiment ------------------------------------------------------------
p_q = sub.add_parser("quick-experiment", help="slice + sliver quickly")
p_q.add_argument("--site", choices=["utah", "clemson", "wisconsin"],
                 default="wisconsin")
p_q.add_argument("--hardware-type", default="c220g5")
p_q.add_argument("--nodes", type=int, default=3)
p_q.add_argument("--duration", type=int, default=1, help="hours")
p_q.add_argument("--os-type", default="UBUNTU22-64-STD")
p_q.add_argument("--ssh-user", required=True)
p_q.add_argument("--ssh-key",
                help="private key file (optional – if omitted, "
                     "keys from ssh-agent / ~/.ssh are used)")
p_q.add_argument("--k8s", action="store_true",
                 help="bootstrap Kubernetes after sliver is ready")
p_q.add_argument("--pod-network-cidr", default="192.168.0.0/16",
                 help="Calico pod CIDR (default 192.168.0.0/16)")
p_q.add_argument("--deploy-srearena", action="store_true",
                 help="deploy SREArena after K8s cluster is ready")
p_q.add_argument("--deploy-key", 
                 help="path to SSH deploy key for SREArena private repo")


# ╭──────────────────────────────────────────────────────────────────────────╮
# │  quick-experiment implementation                                        │
# ╰──────────────────────────────────────────────────────────────────────────╯
def _host_list_from_logininfo(logininfo) -> list[str]:
    """
    Extract hostnames from GENI login info.
    
    Input format examples:
    - "[node0][saleha] c220g5-110426.wisc.cloudlab.us: 22"
    - Raw tuples: (node_name, user, hostname, port)
    
    Returns list[str] of hostnames.
    """
    hosts: list[str] = []
    
    for item in logininfo:
        # Case 1: Raw tuple format (node_name, user, hostname, port)
        if isinstance(item, (tuple, list)) and len(item) >= 3:
            # The hostname is at index 2 in the tuple format
            hostname = item[2]
            if hostname and isinstance(hostname, str) and '.' in hostname:
                hosts.append(hostname)
            continue
        
        # Case 2: String format "[nodeX][user] hostname: port"
        if isinstance(item, str):
            # Pattern to match: ] hostname: or ] hostname (space before colon)
            # This will capture the hostname between the last ] and either : or end of string
            pattern = r'\]\s*([^\s\[\]:]+\.(?:wisc\.cloudlab\.us|utah\.cloudlab\.us|clemson\.cloudlab\.us|[a-z0-9.-]+))(?:\s*:|$)'
            match = re.search(pattern, item)
            if match:
                hosts.append(match.group(1))
                continue
            
            # Fallback pattern for any hostname-like string after ]
            pattern = r'\]\s*([a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+)'
            match = re.search(pattern, item)
            if match:
                hostname = match.group(1)
                # Make sure it's not just the username
                if '.' in hostname and hostname != 'saleha':
                    hosts.append(hostname)
                continue
    
    # Remove duplicates while preserving order
    unique_hosts = []
    for host in hosts:
        if host not in unique_hosts:
            unique_hosts.append(host)
    
    return unique_hosts


def nodes_reachable_simple(cloud: dict, verbose: bool = True) -> bool:
    """Simplified nodes reachable check compatible with original RemoteExecutor"""
    from remote import RemoteExecutor
    
    print(f"🔍 Checking {len(cloud['nodes'])} nodes for SSH connectivity...")
    
    for i, host in enumerate(cloud["nodes"], 1):
        print(f"   [{i}/{len(cloud['nodes'])}] Testing {host}...", end=" ")
        
        # Try multiple times for each host
        max_retries = 3
        success = False
        
        for retry in range(max_retries):
            try:
                executor = RemoteExecutor(host, cloud["ssh_user"], cloud.get("ssh_key"))
                rc, stdout, stderr = executor.exec("echo 'SSH test successful'")
                executor.close()
                
                if rc == 0:
                    print("✅")
                    success = True
                    break
                else:
                    if retry < max_retries - 1:
                        print(".", end="")
                        time.sleep(3)
                    else:
                        print(f"❌ (command failed: rc={rc})")
                        if verbose:
                            print(f"      stderr: {stderr.strip()}")
                    
            except Exception as e:
                if retry < max_retries - 1:
                    print(".", end="")  # Show retry progress
                    time.sleep(3)  # Wait between retries
                else:
                    print(f"❌ ({type(e).__name__}: {str(e)[:50]}...)")
                    if verbose:
                        print(f"      Full error: {e}")
        
        if not success:
            return False
    
    print("✅ All nodes reachable!")
    return True


def quick_experiment(a: argparse.Namespace) -> None:
    ctx = geni.util.loadContext()

    slice_name = f"exp-{random.randint(100000,999999)}"
    expires    = datetime.datetime.now() + datetime.timedelta(hours=a.duration)

    # Build simple RSpec
    req = portal.context.makeRequestRSpec()
    pcs = []
    for i in range(a.nodes):
        n = req.RawPC(f"node{i}")
        n.hardware_type = a.hardware_type
        n.disk_image = (f"urn:publicid:IDN+emulab.net+image+emulab-ops//"
                        f"{a.os_type}")
        n.routable_control_ip = True
        pcs.append(n)
    req.Link(members=pcs)

    agg = {"utah": Utah, "clemson": Clemson, "wisconsin": Wisconsin}[a.site]

    print(f"🔧  Creating slice {slice_name} …")
    ctx.cf.createSlice(ctx, slice_name, exp=expires,
                       desc="Quick experiment via genictl")

    print(f"🚜  Allocating sliver on {a.site.title()} …")
    manifest = agg.createsliver(ctx, slice_name, req)

    geni.util.printlogininfo(manifest=manifest)

    if not a.k8s:
        return  # user didn't ask for Kubernetes

    # ── Kubernetes path ───────────────────────────────────────────────────
    print("\n⚙️  --k8s flag detected → bootstrapping Kubernetes once nodes are reachable")

    logininfo = geni.util._corelogininfo(manifest)
    hosts = _host_list_from_logininfo(logininfo)
    
    print(f"🔍 Debug: Raw logininfo: {logininfo}")
    print(f"🔍 Debug: Extracted hosts: {hosts}")
    
    if not hosts:
        sys.exit("❌  Couldn't parse node hostnames from login info")

    # Validate that we got actual hostnames, not usernames
    valid_hosts = []
    for host in hosts:
        if '.' in host and not host == a.ssh_user:
            valid_hosts.append(host)
        else:
            print(f"⚠️  Skipping invalid hostname: {host}")
    
    if not valid_hosts:
        print("❌  No valid hostnames found! Raw login info:")
        for item in logininfo:
            print(f"    {item}")
        sys.exit("Cannot proceed without valid hostnames")
    
    hosts = valid_hosts
    print(f"✅  Using hosts: {hosts}")

    cfg = {
        "cloudlab": {
            "ssh_user": a.ssh_user,
            "ssh_key":  a.ssh_key,
            "nodes":    hosts,
        },
        "pod_network_cidr": a.pod_network_cidr,
        "deploy_srearena": a.deploy_srearena,
        "deploy_key": a.deploy_key,
    }

    print("⌛  Waiting (≤20 min) for SSH on all nodes …")
    t0 = time.time()
    check_count = 0
    while time.time() - t0 < 1200:  # 20 minutes
        elapsed = time.time() - t0
        check_count += 1
        
        try:
            if nodes_reachable_simple(cfg["cloudlab"]):
                print(f"✅  All nodes reachable after {elapsed:.1f}s!")
                break
        except Exception as e:
            print(f"⚠️  Error checking node reachability (attempt {check_count}): {e}")
        
        # Print status every minute
        if check_count == 1 or elapsed % 60 < 30:  # First check or every ~minute
            print(f"  Still waiting... {elapsed:.0f}s elapsed, checking {len(hosts)} hosts")
        
        time.sleep(30)  # Check every 30 seconds
    else:
        print("⚠️  Nodes not reachable after 20 min – skipping K8s bootstrap")
        print("    You can try running the following manually once nodes are ready:")
        print(f"    ssh {a.ssh_user}@{hosts[0]}")
        return

    print("🚀  Running cluster_setup …")
    try:
        if a.deploy_srearena:
            from cluster_setup import setup_cloudlab_cluster_with_srearena
            setup_cloudlab_cluster_with_srearena(cfg, a.deploy_key)

        else:
            setup_cloudlab_cluster(cfg)
        print("✅  Kubernetes cluster ready!")
    except Exception as e:
        print(f"❌  Cluster setup failed: {e}")
        print("    Nodes are reachable but Kubernetes setup encountered an error.")


# def get_srearena_setup():
#     try:
#         # from srearena_deployment import setup_cloudlab_cluster_with_srearena
#         return setup_cloudlab_cluster_with_srearena
#     except ImportError as e:
#         print(f"⚠️  SREArena deployment not available: {e}")
#         return None
# ╭──────────────────────────────────────────────────────────────────────────╮
# │  Main dispatcher                                                         │
# ╰──────────────────────────────────────────────────────────────────────────╯
def main() -> None:
    args = parser.parse_args()
    match args.cmd:
        case "quick-experiment":
            quick_experiment(args)
        # … other sub-commands …
        case _:
            parser.error(f"unknown command {args.cmd!r}")


if __name__ == "__main__":
    main()