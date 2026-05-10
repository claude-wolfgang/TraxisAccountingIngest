"""Haas CHC transfer driver using SSH/SCP via a Pi Zero USB bridge.

Transfer workflow (Haas VF5/40 at 10.1.1.149):
  1. SSH: Run pre-copy.sh  (disconnects USB from Haas, mounts on Pi)
  2. SCP: Copy file to /mnt/usb_share/ on Pi
  3. SSH: Run post-copy.sh (unmounts from Pi, reconnects USB to Haas)

The post-copy step MUST always execute so the Haas regains access to
its USB storage, even if the SCP transfer fails.
"""

from __future__ import annotations

import logging
import socket
import time
from pathlib import Path

import paramiko

from traxistransfer.constants import (
    HAAS_POST_COPY_SCRIPT,
    HAAS_PRE_COPY_SCRIPT,
    HAAS_SSH_MAX_RETRIES,
    HAAS_SSH_RETRY_DELAY_S,
    HAAS_USB_SHARE_PATH,
)
from traxistransfer.drivers.base import (
    ProgramInfo,
    ProgressCallback,
    TransferDriver,
    TransferError,
)
from traxistransfer.models.machine import Machine

log = logging.getLogger(__name__)


class HaasChcSshDriver(TransferDriver):
    """SSH/SCP driver for Haas CHC machines via a Pi Zero USB bridge."""

    def __init__(self, machine: Machine) -> None:
        super().__init__(machine)
        self._ssh_host: str = machine.ssh_host or machine.ip
        self._ssh_user: str = machine.ssh_user or "haasmill1"

    # ------------------------------------------------------------------
    # SSH helpers
    # ------------------------------------------------------------------

    def _get_ssh_client(self) -> paramiko.SSHClient:
        """Create a connected SSH client with retry logic."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        last_error: Exception | None = None
        for attempt in range(HAAS_SSH_MAX_RETRIES):
            try:
                client.connect(
                    self._ssh_host,
                    username=self._ssh_user,
                    timeout=10,
                    look_for_keys=True,
                    allow_agent=True,
                )
                return client
            except Exception as exc:
                last_error = exc
                if attempt < HAAS_SSH_MAX_RETRIES - 1:
                    log.warning(
                        "SSH connect attempt %d/%d failed: %s — retrying in %ds",
                        attempt + 1,
                        HAAS_SSH_MAX_RETRIES,
                        exc,
                        HAAS_SSH_RETRY_DELAY_S,
                    )
                    time.sleep(HAAS_SSH_RETRY_DELAY_S)

        raise TransferError(
            f"SSH connect to {self._ssh_host} failed after "
            f"{HAAS_SSH_MAX_RETRIES} attempts: {last_error}"
        )

    def _ssh_exec(self, client: paramiko.SSHClient, command: str) -> str:
        """Execute a command via SSH.  Raises TransferError on non-zero exit."""
        log.debug("SSH exec: %s", command)
        _stdin, stdout, stderr = client.exec_command(command, timeout=30)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            err = stderr.read().decode().strip()
            raise TransferError(
                f"Remote command failed (exit {exit_code}): {command}: {err}"
            )
        return stdout.read().decode()

    # ------------------------------------------------------------------
    # TransferDriver interface
    # ------------------------------------------------------------------

    def send_program(
        self,
        file_path: Path,
        program_number: str | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        """Send an NC program to the Haas via the Pi Zero USB bridge."""
        from scp import SCPClient

        client = self._get_ssh_client()
        try:
            # Step 1: Disconnect USB from Haas, mount on Pi
            log.info("Running pre-copy script on %s", self._ssh_host)
            self._ssh_exec(client, HAAS_PRE_COPY_SCRIPT)

            try:
                # Step 2: SCP the file to /mnt/usb_share/
                remote_path = f"{HAAS_USB_SHARE_PATH}/{file_path.name}"
                file_size = file_path.stat().st_size
                log.info(
                    "SCP put %s -> %s:%s (%d bytes)",
                    file_path,
                    self._ssh_host,
                    remote_path,
                    file_size,
                )

                def _progress(filename: bytes, size: int, sent: int) -> None:
                    if progress_cb:
                        progress_cb(sent, file_size)

                with SCPClient(client.get_transport(), progress=_progress) as scp:
                    scp.put(str(file_path), remote_path)

            finally:
                # Step 3: MUST always run — reconnect USB to Haas
                log.info("Running post-copy script on %s", self._ssh_host)
                self._ssh_exec(client, HAAS_POST_COPY_SCRIPT)

        except TransferError:
            raise
        except Exception as exc:
            # Belt-and-suspenders: try post-copy even on unexpected errors
            try:
                self._ssh_exec(client, HAAS_POST_COPY_SCRIPT)
            except Exception:
                log.warning("Post-copy safety attempt also failed", exc_info=True)
            raise TransferError(f"Send failed: {exc}") from exc
        finally:
            client.close()

    def receive_program(
        self,
        program_number: str,
        dest_path: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        """Receive an NC program from the Haas via the Pi Zero USB bridge."""
        from scp import SCPClient

        client = self._get_ssh_client()
        try:
            # Step 1: Disconnect USB from Haas, mount on Pi
            log.info("Running pre-copy script on %s", self._ssh_host)
            self._ssh_exec(client, HAAS_PRE_COPY_SCRIPT)

            try:
                # Step 2: SCP get
                remote_path = f"{HAAS_USB_SHARE_PATH}/{program_number}"
                log.info(
                    "SCP get %s:%s -> %s",
                    self._ssh_host,
                    remote_path,
                    dest_path,
                )
                with SCPClient(client.get_transport()) as scp:
                    scp.get(remote_path, str(dest_path))

            finally:
                # Step 3: MUST always run — reconnect USB to Haas
                log.info("Running post-copy script on %s", self._ssh_host)
                self._ssh_exec(client, HAAS_POST_COPY_SCRIPT)

        except TransferError:
            raise
        except Exception as exc:
            try:
                self._ssh_exec(client, HAAS_POST_COPY_SCRIPT)
            except Exception:
                log.warning("Post-copy safety attempt also failed", exc_info=True)
            raise TransferError(f"Receive failed: {exc}") from exc
        finally:
            client.close()

    def list_programs(self) -> list[ProgramInfo]:
        """List .nc files on the Haas USB share."""
        client = self._get_ssh_client()
        try:
            # Step 1: Disconnect USB from Haas, mount on Pi
            self._ssh_exec(client, HAAS_PRE_COPY_SCRIPT)

            try:
                # Step 2: List files
                output = self._ssh_exec(
                    client,
                    f"ls -la {HAAS_USB_SHARE_PATH}/*.nc 2>/dev/null || true",
                )
                programs: list[ProgramInfo] = []
                for line in output.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 9:
                        name = parts[-1]
                        size = int(parts[4]) if parts[4].isdigit() else 0
                        programs.append(
                            ProgramInfo(number=name, name=name, size=size)
                        )
                return programs

            finally:
                # Step 3: MUST always run — reconnect USB to Haas
                self._ssh_exec(client, HAAS_POST_COPY_SCRIPT)

        except TransferError:
            raise
        except Exception as exc:
            # Try to reconnect USB on unexpected error with a fresh client
            try:
                recovery = self._get_ssh_client()
                self._ssh_exec(recovery, HAAS_POST_COPY_SCRIPT)
                recovery.close()
            except Exception:
                log.warning("Post-copy recovery attempt also failed", exc_info=True)
            raise TransferError(f"List failed: {exc}") from exc
        finally:
            client.close()

    def is_reachable(self) -> bool:
        """Quick check if the Pi Zero SSH port is open (3s timeout).

        Uses a raw socket probe instead of full SSH handshake to avoid
        the ~30s blocking caused by _get_ssh_client() retries.
        """
        try:
            sock = socket.create_connection((self._ssh_host, 22), timeout=3)
            sock.close()
            return True
        except Exception:
            return False
