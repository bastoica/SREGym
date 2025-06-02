import time
import datetime
import signal
import threading
from typing import Optional
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from provisioner.config.settings import DefaultSettings, DELETE_EXPERIMENT_ERRORS
from provisioner.utils.logger import logger
from provisioner.state_manager import StateManager, CLUSTER_STATUS, SREARENA_STATUS
from provisioner.provisioner import CloudlabProvisioner
from provisioner.utils.ssh import SSHManager, SSHUtilError

# Global stop event for graceful shutdown
stop_event = threading.Event()


class ProvisionerDaemon:
    def __init__(self):
        logger.info("Initializing Provisioner Daemon...")
        self.state_manager = StateManager(db_path=DefaultSettings.DATABASE_PATH)
        self.cloudlab = CloudlabProvisioner(context_path=DefaultSettings.CLOUDLAB_CONTEXT_PATH)

        self.scheduler = BlockingScheduler()
        logger.info("Provisioner Daemon initialized.")

    def _get_ssh_manager(
        self, hostname: str, port: int = 22, timeout: int = DefaultSettings.DEFAULT_SSH_TIME_OUT_SECONDS
    ) -> SSHManager:
        """
        Create an SSHManager instance for a given host.
        """
        return SSHManager(
            hostname=hostname,
            username=DefaultSettings.PROVISIONER_DEFAULT_SSH_USERNAME,
            private_key_path=DefaultSettings.PROVISIONER_SSH_PRIVATE_KEY_PATH,
            port=port,
            timeout=timeout,
        )

    def check_automatic_provisioning(self):
        logger.info("Running: Automatic Provisioning Check")
        try:
            effective_pool_size = self.state_manager.count_total_available_clusters()
            needed = DefaultSettings.MIN_AVAILABLE_CLUSTERS - effective_pool_size

            logger.info(f"Pool Status: EffectivePool={effective_pool_size}. Needed={needed}")

            for _ in range(max(0, needed)):
                current_total_managed = self.state_manager.count_total_managed_clusters()
                if current_total_managed >= DefaultSettings.MAX_TOTAL_CLUSTERS:
                    logger.warning(
                        f"Max total clusters ({DefaultSettings.MAX_TOTAL_CLUSTERS}) reached. Cannot auto-provision more."
                    )
                    break

                logger.info(f"Attempting to auto-provision a new cluster. Current total: {current_total_managed}")
                slice_name = self.cloudlab.generate_slice_name()

                # Record intention to provision
                self.state_manager.create_cluster_record(
                    slice_name=slice_name,
                    aggregate_name="<PENDING>",
                    hardware_type=DefaultSettings.DEFAULT_HARDWARE_TYPE,
                    os_type=DefaultSettings.DEFAULT_OS_TYPE,
                    node_count=DefaultSettings.DEFAULT_NODE_COUNT,
                    status=CLUSTER_STATUS.STATUS_PROVISIONING,
                )

                experiment_info = None

                try:
                    experiment_info = self.cloudlab.create_experiment(
                        slice_name=slice_name,
                        hardware_type=DefaultSettings.DEFAULT_HARDWARE_TYPE,
                        os_type=DefaultSettings.DEFAULT_OS_TYPE,
                        node_count=DefaultSettings.DEFAULT_NODE_COUNT,
                        # +1 to account for the buffer time. After default timeout, the cluster might not need to be deleted if deleing it will cause the available pool to be too low
                        duration=DefaultSettings.UNCLAIMED_CLUSTER_TIMEOUT_HOURS + 1,
                    )

                    if experiment_info and experiment_info.get("login_info"):
                        control_node_info = next((n for n in experiment_info["login_info"] if n[0] == "control"), None)
                        if not control_node_info:
                            raise ValueError("Control node info not found in login_info")

                        hostname = control_node_info[2]
                        expires_at = datetime.datetime.now() + datetime.timedelta(hours=experiment_info["duration"])

                        self.state_manager.update_cluster_record(
                            slice_name,
                            aggregate_name=experiment_info["aggregate_name"],
                            control_node_hostname=hostname,
                            login_info=experiment_info["login_info"],
                            cloudlab_expires_at=expires_at,
                            # Status remains PROVISIONING until SRE Arena setup
                        )
                        logger.info(f"Cluster {slice_name} provisioned by Cloudlab. Host: {hostname}")

                        self._setup_sre_arena_and_finalize(slice_name, hostname)

                    else:
                        logger.error(f"Failed to create experiment {slice_name} via Cloudlab.")
                        self.state_manager.update_cluster_record(
                            slice_name,
                            status=CLUSTER_STATUS.STATUS_ERROR,
                            last_error_message="Cloudlab provisioning failed",
                        )
                except Exception as e:
                    logger.error(f"Error during Cloudlab provisioning for {slice_name}: {e}", exc_info=True)
                    self.state_manager.update_cluster_record(
                        slice_name, status=CLUSTER_STATUS.STATUS_ERROR, last_error_message=str(e)
                    )

                    # If was provisioned, delete the cluster
                    if experiment_info and experiment_info.get("aggregate_name"):
                        self.cloudlab.delete_experiment(slice_name, experiment_info["aggregate_name"])
        except Exception as e:
            logger.error(f"Critical error in automatic provisioning check: {e}", exc_info=True)

    # TODO: Add SRE Arena setup here
    def _setup_sre_arena_and_finalize(self, slice_name: str, hostname: str):
        """Placeholder for SRE Arena setup and finalizing cluster state."""
        logger.info(f"Starting SRE Arena setup for {slice_name} on {hostname} (Placeholder)...")
        sre_arena_status = SREARENA_STATUS.SRE_ARENA_NOT_ATTEMPTED

        try:
            print("Setting up SRE Arena...")
            self.state_manager.update_cluster_record(
                slice_name,
                status=CLUSTER_STATUS.STATUS_UNCLAIMED_READY,
                sre_arena_setup_status=SREARENA_STATUS.SRE_ARENA_SUCCESS,
            )
        except Exception as e:
            logger.error(f"Error during SRE Arena setup for {slice_name}: {e}", exc_info=True)
            self.state_manager.update_cluster_record(
                slice_name,
                status=CLUSTER_STATUS.STATUS_ERROR,
                sre_arena_setup_status=SREARENA_STATUS.SRE_ARENA_FAILED,
                last_error_message="SRE Arena setup failed",
            )
            raise e

    def check_unclaimed_cluster_timeout(self):
        logger.info("Running: Unclaimed Cluster Timeout Check")
        try:
            unclaimed_clusters = self.state_manager.get_clusters_by_status(CLUSTER_STATUS.STATUS_UNCLAIMED_READY)
            now = datetime.datetime.now()

            for cluster in unclaimed_clusters:
                slice_name = cluster["slice_name"]

                # Using last_extended_at to track the pool entry time
                pool_entry_time = cluster["last_extended_at"]

                if not isinstance(pool_entry_time, datetime.datetime):
                    pool_entry_time = datetime.datetime.fromisoformat(str(pool_entry_time))

                if now - pool_entry_time > datetime.timedelta(hours=DefaultSettings.UNCLAIMED_CLUSTER_TIMEOUT_HOURS):
                    logger.info(f"Unclaimed cluster {slice_name} timed out (pool entry time: {pool_entry_time}).")

                    # Don't delete if pool is too low
                    if self.state_manager.count_total_available_clusters() <= DefaultSettings.MIN_AVAILABLE_CLUSTERS:
                        logger.info(f"Pool is low. Extending {slice_name} instead of deleting.")
                        new_expiry_duration = DefaultSettings.UNCLAIMED_CLUSTER_TIMEOUT_HOURS

                        try:
                            if self.cloudlab.renew_experiment(
                                slice_name, new_expiry_duration + 1, cluster["aggregate_name"]
                            ):
                                new_cloudlab_expires_at = now + datetime.timedelta(hours=new_expiry_duration)
                                self.state_manager.update_cluster_record(
                                    slice_name,
                                    last_extended_at=now,
                                    cloudlab_expires_at=new_cloudlab_expires_at,
                                )
                                logger.info(f"Extended {slice_name}. New 'pool_entry_time' for timeout: {now}")
                            else:
                                logger.error(f"Failed to extend {slice_name}. Marking for termination.")
                                self.state_manager.update_cluster_record(
                                    slice_name, status=CLUSTER_STATUS.STATUS_TERMINATING
                                )
                        except Exception as e:
                            logger.error(f"Error extending {slice_name}: {e}. Marking for termination.", exc_info=True)
                            self.state_manager.update_cluster_record(
                                slice_name, status=CLUSTER_STATUS.STATUS_TERMINATING
                            )
                    else:
                        logger.info(f"Deleting unclaimed cluster {slice_name}.")
                        self.state_manager.update_cluster_record(slice_name, status=CLUSTER_STATUS.STATUS_TERMINATING)
        except Exception as e:
            logger.error(f"Critical error in unclaimed cluster timeout check: {e}", exc_info=True)

    # The provisioner should extend the cluster daily until the user reliquishing timeout
    def check_claimed_cluster_extension(self):
        logger.info("Running: Claimed Cluster Extension Check")
        try:
            claimed_clusters = self.state_manager.get_clusters_by_status(CLUSTER_STATUS.STATUS_CLAIMED)
            now = datetime.datetime.now()
            for cluster in claimed_clusters:
                # Check if we need to extend based on last extension time
                last_extended_at = cluster.get("last_extended_at")
                if last_extended_at:
                    if not isinstance(last_extended_at, datetime.datetime):
                        last_extended_at = datetime.datetime.fromisoformat(str(last_extended_at))
                    # If last extension was less than 24 hours ago, skip
                    if now - last_extended_at < datetime.timedelta(hours=24):
                        continue

                logger.info(f"Performing daily extension for claimed cluster {cluster['slice_name']}.")
                new_duration_hours = DefaultSettings.CLAIMED_CLUSTER_DEFAULT_DURATION_HOURS
                try:
                    if self.cloudlab.renew_experiment(
                        cluster["slice_name"], new_duration_hours, cluster["aggregate_name"]
                    ):
                        new_cloudlab_expires_at = now + datetime.timedelta(hours=new_duration_hours)
                        self.state_manager.update_cluster_record(
                            cluster["slice_name"], cloudlab_expires_at=new_cloudlab_expires_at, last_extended_at=now
                        )
                        logger.info(f"Successfully extended {cluster['slice_name']} to {new_cloudlab_expires_at}.")
                        # TODO: Notify user of successful extension (optional)
                    else:
                        logger.error(
                            f"Failed to extend claimed cluster {cluster['slice_name']}. User should be notified."
                        )
                        # TODO: Notify user of extension failure
                except Exception as e:
                    logger.error(f"Error extending claimed cluster {cluster['slice_name']}: {e}", exc_info=True)
                    # TODO: Notify user of extension failure
        except Exception as e:
            logger.error(f"Critical error in claimed cluster extension check: {e}", exc_info=True)

    # TODO: Implement this
    def _get_last_ssh_time(self, hostname: str) -> Optional[datetime.datetime]:
        logger.info(f"Attempting to get actual last SSH time for {hostname} (Placeholder).")
        return datetime.datetime.now()

    def check_claimed_cluster_inactivity(self):
        logger.info("Running: Claimed Cluster Inactivity Check")
        try:
            claimed_clusters = self.state_manager.get_clusters_by_status(CLUSTER_STATUS.STATUS_CLAIMED)
            now = datetime.datetime.now()
            for cluster in claimed_clusters:
                slice_name = cluster["slice_name"]
                if cluster.get("evaluation_override", False):
                    logger.debug(f"Cluster {slice_name} has evaluation override. Skipping inactivity check.")
                    continue

                last_ssh_time = self._get_last_ssh_time(cluster["control_node_hostname"])

                self.state_manager.update_cluster_record(slice_name, last_activity_at=last_ssh_time)

                if now - last_ssh_time > datetime.timedelta(
                    hours=DefaultSettings.CLAIMED_CLUSTER_INACTIVITY_TIMEOUT_HOURS
                ):
                    logger.info(f"Claimed cluster {slice_name} inactive since {last_ssh_time}. Relinquishing.")
                    self.state_manager.update_cluster_record(
                        slice_name,
                        status=CLUSTER_STATUS.STATUS_PENDING_CLEANUP,
                        claimed_by_user_id=None,  # Disassociate user
                        user_ssh_key_installed=False,  # Mark key for removal during cleanup
                    )
                    # TODO: Notify user of auto-relinquishment
                else:
                    logger.debug(f"Cluster {slice_name} last activity at {last_ssh_time} is within inactivity window.")
        except Exception as e:
            logger.error(f"Critical error in claimed cluster inactivity check: {e}", exc_info=True)

    # TODO: Implement this
    def _reset_vm(self, slice_name: str, hostname: str):
        logger.info(f"Resetting VM for {slice_name} on {hostname} (Placeholder)...")
        return True

    def process_pending_cleanup_clusters(self):
        logger.info("Running: Process Pending Cleanup Clusters")
        try:
            cleanup_clusters = self.state_manager.get_clusters_by_status(CLUSTER_STATUS.STATUS_PENDING_CLEANUP)
            for cluster in cleanup_clusters:
                slice_name = cluster["slice_name"]
                hostname = cluster["control_node_hostname"]

                logger.info(f"Processing cleanup for {slice_name} on {hostname}.")

                self._reset_vm(slice_name, hostname)
                self._setup_sre_arena_and_finalize(slice_name, hostname)

        except Exception as e:
            logger.error(f"Critical error in processing pending cleanup clusters: {e}", exc_info=True)

    def process_terminating_clusters(self):
        logger.info("Running: Process Terminating Clusters")
        try:
            terminating_clusters = self.state_manager.get_clusters_by_status(CLUSTER_STATUS.STATUS_TERMINATING)
            for cluster in terminating_clusters:
                slice_name = cluster["slice_name"]
                aggregate_name = cluster["aggregate_name"]
                logger.info(f"Attempting to terminate cluster {slice_name} on {aggregate_name}.")
                try:
                    if not aggregate_name or aggregate_name == "<PENDING>":
                        logger.warning(
                            f"Cannot terminate {slice_name}, aggregate_name is unknown ('{aggregate_name}'). Deleting DB record only."
                        )
                        self.state_manager.delete_cluster_record(slice_name)
                        continue

                    if self.cloudlab.delete_experiment(slice_name, aggregate_name):
                        logger.info(f"Successfully deleted experiment {slice_name} from Cloudlab.")
                        self.state_manager.delete_cluster_record(slice_name)
                        logger.info(f"Removed cluster record for {slice_name}.")
                    else:
                        err_msg = f"Cloudlab API failed to delete {slice_name}. Will retry."
                        logger.error(err_msg)
                        self.state_manager.update_cluster_record(
                            slice_name, last_error_message=err_msg, status=CLUSTER_STATUS.STATUS_TERMINATING
                        )
                except Exception as e:
                    err_msg = f"Error deleting {slice_name} from Cloudlab: {e}"
                    logger.error(err_msg + ". Will retry.", exc_info=True)
                    self.state_manager.update_cluster_record(slice_name, last_error_message=err_msg, status=CLUSTER_STATUS.STATUS_TERMINATING)

        except Exception as e:
            logger.error(f"Critical error in processing terminating clusters: {e}", exc_info=True)

    def run_all_checks(self):
        """Runs all periodic checks in sequence."""
        if stop_event.is_set():
            logger.info("Stop event received by run_all_checks, skipping scheduled run.")
            return

        logger.info("======== Starting Periodic Checks Cycle ========")
        try:
            self.check_automatic_provisioning()
            self.check_unclaimed_cluster_timeout()
            self.check_claimed_cluster_extension()
            self.check_claimed_cluster_inactivity()
            self.process_pending_cleanup_clusters()
            self.process_terminating_clusters()
        except Exception as e:
            logger.critical(f"Unhandled exception during periodic checks cycle: {e}", exc_info=True)
        logger.info("======== Finished Periodic Checks Cycle ========")

    def start(self):
        logger.info("Starting Provisioner Daemon Scheduler...")
        # Run once immediately at start, then schedule
        try:
            logger.info("Performing initial run of all checks...")
            self.run_all_checks()
            logger.info("Initial run of checks complete.")
        except Exception as e:
            logger.critical(f"Initial run of checks failed critically: {e}", exc_info=True)

        # Schedule jobs
        self.scheduler.add_job(
            self.run_all_checks,
            trigger=IntervalTrigger(minutes=DefaultSettings.SCHEDULER_INTERVAL_MINUTES),
            id="provisioner_main_checks_job",
            name="Run all provisioner checks",
            replace_existing=True,
            misfire_grace_time=300,
            max_instances=1
        )
        
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped by user/system.")
        finally:
            if self.scheduler.running:
                logger.info("Shutting down scheduler...")
                self.scheduler.shutdown(wait=True)
            logger.info("Provisioner Daemon scheduler shut down.")

    # --- Signal Handler and Main Execution ---
    _scheduler_instance = None

    def signal_handler(signum, frame):
        global _scheduler_instance
        logger.info(f"Signal {signal.Signals(signum).name} received, initiating graceful shutdown...")
        stop_event.set()
        if _scheduler_instance and _scheduler_instance.running:
            logger.info("Requesting scheduler shutdown...")
            _scheduler_instance.shutdown(wait=False)
        else:
            logger.info("Scheduler not running or not initialized for signal handler.")