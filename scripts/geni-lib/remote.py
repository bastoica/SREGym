import os
from pathlib import Path
import paramiko
from paramiko.ssh_exception import PasswordRequiredException


class RemoteExecutor:
    """Thin SSH helper around paramiko suitable for non-interactive commands."""

    def __init__(self, host: str, user: str, key_path: str | None = None):
        self.host = host
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        keyfile: str | None = None
        if key_path:
            keyfile = os.path.expanduser(os.path.expandvars(key_path))
            if not Path(keyfile).is_file():     
                keyfile = None

        try:
            self.client.connect(
                hostname=host,
                username=user,
                key_filename=keyfile,
                look_for_keys=(keyfile is None),
                allow_agent=(keyfile is None),
                timeout=10,
            )
        except PasswordRequiredException:
            self.client.connect(
                hostname=host,
                username=user,
                look_for_keys=True,
                allow_agent=True,
                timeout=10,
            )

    def exec(self, cmd: str, timeout: int | None = None) -> tuple[int, str, str]:
        """Execute a command with optional timeout"""
        stdin, stdout, stderr = self.client.exec_command(cmd, timeout=timeout)
        rc = stdout.channel.recv_exit_status()
        return rc, stdout.read().decode(), stderr.read().decode()

    def close(self) -> None:
        self.client.close()
