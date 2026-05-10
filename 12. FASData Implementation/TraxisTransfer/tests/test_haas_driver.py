"""Tests for the Haas CHC SSH/SCP transfer driver."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from traxistransfer.constants import (
    HAAS_POST_COPY_SCRIPT,
    HAAS_PRE_COPY_SCRIPT,
    HAAS_SSH_MAX_RETRIES,
    HAAS_USB_SHARE_PATH,
    DriverType,
)
from traxistransfer.drivers.base import TransferError
from traxistransfer.drivers.haas_chc_ssh import HaasChcSshDriver
from traxistransfer.models.machine import Machine


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture
def machine() -> Machine:
    """Standard Haas test machine (matches conftest.haas_machine)."""
    return Machine(
        id="M1",
        name="Haas VF5/40",
        type="Mill",
        driver=DriverType.HAAS_CHC,
        ip="10.1.1.149",
        port=22,
        proshop_pot_id="Mill-1",
        ssh_host="10.1.1.149",
        ssh_user="haasmill1",
    )


@pytest.fixture
def driver(machine: Machine) -> HaasChcSshDriver:
    return HaasChcSshDriver(machine)


@pytest.fixture
def mock_ssh_client() -> MagicMock:
    """A fully-wired mock paramiko.SSHClient."""
    client = MagicMock()
    transport = MagicMock()
    client.get_transport.return_value = transport

    # exec_command returns (stdin, stdout, stderr) — stdout has a channel
    def _make_exec_result(output: str = "", exit_code: int = 0):
        stdin = MagicMock()
        stdout = MagicMock()
        stderr = MagicMock()
        stdout.read.return_value = output.encode()
        stderr.read.return_value = b""
        stdout.channel.recv_exit_status.return_value = exit_code
        return stdin, stdout, stderr

    # Default: every exec_command succeeds with empty output
    client.exec_command.side_effect = lambda cmd, **kw: _make_exec_result()
    client._make_exec_result = _make_exec_result  # expose helper for tests

    return client


@pytest.fixture
def nc_file(tmp_path: Path) -> Path:
    """Minimal NC file for tests."""
    p = tmp_path / "O1234.nc"
    p.write_text("%\nO1234\nG0 X0 Y0\nM30\n%\n")
    return p


# -------------------------------------------------------------------
# send_program — happy path
# -------------------------------------------------------------------


@patch("traxistransfer.drivers.haas_chc_ssh.paramiko")
@patch("scp.SCPClient")
def test_send_calls_pre_scp_post_in_order(
    mock_scp_cls: MagicMock,
    mock_paramiko: MagicMock,
    driver: HaasChcSshDriver,
    mock_ssh_client: MagicMock,
    nc_file: Path,
) -> None:
    """send_program must execute pre-copy, SCP put, post-copy in that order."""
    mock_paramiko.SSHClient.return_value = mock_ssh_client
    mock_paramiko.AutoAddPolicy = MagicMock()

    # Track call order
    call_order: list[str] = []

    def _exec_side_effect(cmd: str, **kw):
        if HAAS_PRE_COPY_SCRIPT in cmd:
            call_order.append("pre-copy")
        elif HAAS_POST_COPY_SCRIPT in cmd:
            call_order.append("post-copy")
        return mock_ssh_client._make_exec_result()

    mock_ssh_client.exec_command.side_effect = _exec_side_effect

    # SCP mock
    scp_instance = MagicMock()
    mock_scp_cls.return_value.__enter__ = MagicMock(return_value=scp_instance)
    mock_scp_cls.return_value.__exit__ = MagicMock(return_value=False)

    def _scp_put(*args, **kwargs):
        call_order.append("scp-put")

    scp_instance.put.side_effect = _scp_put

    driver.send_program(nc_file)

    assert call_order == ["pre-copy", "scp-put", "post-copy"]


# -------------------------------------------------------------------
# send_program — post-copy runs even when SCP fails
# -------------------------------------------------------------------


@patch("traxistransfer.drivers.haas_chc_ssh.paramiko")
@patch("scp.SCPClient")
def test_send_runs_postcopy_on_scp_failure(
    mock_scp_cls: MagicMock,
    mock_paramiko: MagicMock,
    driver: HaasChcSshDriver,
    mock_ssh_client: MagicMock,
    nc_file: Path,
) -> None:
    """Post-copy MUST execute even when SCP put raises an exception."""
    mock_paramiko.SSHClient.return_value = mock_ssh_client
    mock_paramiko.AutoAddPolicy = MagicMock()

    post_copy_ran = False

    def _exec_side_effect(cmd: str, **kw):
        nonlocal post_copy_ran
        if HAAS_POST_COPY_SCRIPT in cmd:
            post_copy_ran = True
        return mock_ssh_client._make_exec_result()

    mock_ssh_client.exec_command.side_effect = _exec_side_effect

    # Make SCP blow up
    scp_instance = MagicMock()
    mock_scp_cls.return_value.__enter__ = MagicMock(return_value=scp_instance)
    mock_scp_cls.return_value.__exit__ = MagicMock(return_value=False)
    scp_instance.put.side_effect = OSError("SCP exploded")

    with pytest.raises(TransferError, match="Send failed"):
        driver.send_program(nc_file)

    assert post_copy_ran, "post-copy script must run even when SCP fails"


# -------------------------------------------------------------------
# receive_program — post-copy runs even when SCP get fails
# -------------------------------------------------------------------


@patch("traxistransfer.drivers.haas_chc_ssh.paramiko")
@patch("scp.SCPClient")
def test_receive_runs_postcopy_on_scp_failure(
    mock_scp_cls: MagicMock,
    mock_paramiko: MagicMock,
    driver: HaasChcSshDriver,
    mock_ssh_client: MagicMock,
    tmp_path: Path,
) -> None:
    """Post-copy MUST execute even when SCP get raises an exception."""
    mock_paramiko.SSHClient.return_value = mock_ssh_client
    mock_paramiko.AutoAddPolicy = MagicMock()

    post_copy_ran = False

    def _exec_side_effect(cmd: str, **kw):
        nonlocal post_copy_ran
        if HAAS_POST_COPY_SCRIPT in cmd:
            post_copy_ran = True
        return mock_ssh_client._make_exec_result()

    mock_ssh_client.exec_command.side_effect = _exec_side_effect

    scp_instance = MagicMock()
    mock_scp_cls.return_value.__enter__ = MagicMock(return_value=scp_instance)
    mock_scp_cls.return_value.__exit__ = MagicMock(return_value=False)
    scp_instance.get.side_effect = OSError("SCP get exploded")

    dest = tmp_path / "output.nc"

    with pytest.raises(TransferError, match="Receive failed"):
        driver.receive_program("O1234.nc", dest)

    assert post_copy_ran, "post-copy script must run even when SCP get fails"


# -------------------------------------------------------------------
# SSH connect retry logic
# -------------------------------------------------------------------


@patch("traxistransfer.drivers.haas_chc_ssh.time.sleep")
@patch("traxistransfer.drivers.haas_chc_ssh.paramiko")
def test_ssh_retry_on_connect_failure(
    mock_paramiko: MagicMock,
    mock_sleep: MagicMock,
    driver: HaasChcSshDriver,
) -> None:
    """SSH connect should retry HAAS_SSH_MAX_RETRIES times before giving up."""
    client = MagicMock()
    mock_paramiko.SSHClient.return_value = client
    mock_paramiko.AutoAddPolicy = MagicMock()

    client.connect.side_effect = ConnectionRefusedError("refused")

    with pytest.raises(TransferError, match=f"after {HAAS_SSH_MAX_RETRIES} attempts"):
        driver._get_ssh_client()

    assert client.connect.call_count == HAAS_SSH_MAX_RETRIES
    # Sleep is called between retries (one fewer than total attempts)
    assert mock_sleep.call_count == HAAS_SSH_MAX_RETRIES - 1


@patch("traxistransfer.drivers.haas_chc_ssh.time.sleep")
@patch("traxistransfer.drivers.haas_chc_ssh.paramiko")
def test_ssh_retry_succeeds_on_second_attempt(
    mock_paramiko: MagicMock,
    mock_sleep: MagicMock,
    driver: HaasChcSshDriver,
) -> None:
    """SSH should return successfully if a retry succeeds."""
    client = MagicMock()
    mock_paramiko.SSHClient.return_value = client
    mock_paramiko.AutoAddPolicy = MagicMock()

    # Fail once, then succeed
    client.connect.side_effect = [ConnectionRefusedError("refused"), None]

    result = driver._get_ssh_client()
    assert result is client
    assert client.connect.call_count == 2
    assert mock_sleep.call_count == 1


# -------------------------------------------------------------------
# is_reachable
# -------------------------------------------------------------------


@patch("traxistransfer.drivers.haas_chc_ssh.socket.create_connection")
def test_is_reachable_true(
    mock_create_conn: MagicMock,
    driver: HaasChcSshDriver,
) -> None:
    """is_reachable returns True when the SSH port is open."""
    mock_sock = MagicMock()
    mock_create_conn.return_value = mock_sock

    assert driver.is_reachable() is True
    mock_create_conn.assert_called_once_with(("10.1.1.149", 22), timeout=3)
    mock_sock.close.assert_called_once()


@patch("traxistransfer.drivers.haas_chc_ssh.socket.create_connection")
def test_is_reachable_false(
    mock_create_conn: MagicMock,
    driver: HaasChcSshDriver,
) -> None:
    """is_reachable returns False when the SSH port is unreachable."""
    mock_create_conn.side_effect = OSError("Connection refused")

    assert driver.is_reachable() is False


# -------------------------------------------------------------------
# list_programs
# -------------------------------------------------------------------


@patch("traxistransfer.drivers.haas_chc_ssh.paramiko")
def test_list_programs_parses_ls_output(
    mock_paramiko: MagicMock,
    driver: HaasChcSshDriver,
    mock_ssh_client: MagicMock,
) -> None:
    """list_programs parses ls -la output into ProgramInfo objects."""
    mock_paramiko.SSHClient.return_value = mock_ssh_client
    mock_paramiko.AutoAddPolicy = MagicMock()

    ls_output = (
        "-rw-r--r-- 1 haasmill1 haasmill1 1234 Mar 18 10:00 O1234.nc\n"
        "-rw-r--r-- 1 haasmill1 haasmill1 5678 Mar 18 10:05 O5678.nc\n"
    )

    call_count = 0

    def _exec_side_effect(cmd: str, **kw):
        nonlocal call_count
        call_count += 1
        if "ls -la" in cmd:
            return mock_ssh_client._make_exec_result(output=ls_output)
        return mock_ssh_client._make_exec_result()

    mock_ssh_client.exec_command.side_effect = _exec_side_effect

    programs = driver.list_programs()

    assert len(programs) == 2
    assert programs[0].number == "O1234.nc"
    assert programs[0].size == 1234
    assert programs[1].number == "O5678.nc"
    assert programs[1].size == 5678


# -------------------------------------------------------------------
# ssh_exec error handling
# -------------------------------------------------------------------


@patch("traxistransfer.drivers.haas_chc_ssh.paramiko")
def test_ssh_exec_raises_on_nonzero_exit(
    mock_paramiko: MagicMock,
    driver: HaasChcSshDriver,
    mock_ssh_client: MagicMock,
) -> None:
    """_ssh_exec raises TransferError when the remote command exits non-zero."""
    mock_paramiko.SSHClient.return_value = mock_ssh_client
    mock_paramiko.AutoAddPolicy = MagicMock()

    client = driver._get_ssh_client()

    stdin = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stdout.read.return_value = b""
    stderr.read.return_value = b"mount: permission denied"
    stdout.channel.recv_exit_status.return_value = 1
    mock_ssh_client.exec_command.side_effect = None
    mock_ssh_client.exec_command.return_value = (stdin, stdout, stderr)

    with pytest.raises(TransferError, match="permission denied"):
        driver._ssh_exec(client, "some-command")


# -------------------------------------------------------------------
# Progress callback
# -------------------------------------------------------------------


@patch("traxistransfer.drivers.haas_chc_ssh.paramiko")
@patch("scp.SCPClient")
def test_send_invokes_progress_callback(
    mock_scp_cls: MagicMock,
    mock_paramiko: MagicMock,
    driver: HaasChcSshDriver,
    mock_ssh_client: MagicMock,
    nc_file: Path,
) -> None:
    """send_program should forward SCP progress to the caller's callback."""
    mock_paramiko.SSHClient.return_value = mock_ssh_client
    mock_paramiko.AutoAddPolicy = MagicMock()

    progress_calls: list[tuple[int, int]] = []

    def _progress_cb(sent: int, total: int) -> None:
        progress_calls.append((sent, total))

    # Capture the progress kwarg SCPClient was constructed with
    captured_progress = None

    def _scp_init(transport, progress=None):
        nonlocal captured_progress
        captured_progress = progress
        return MagicMock()

    scp_instance = MagicMock()

    # Make SCPClient context manager work
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=scp_instance)
    ctx.__exit__ = MagicMock(return_value=False)
    mock_scp_cls.return_value = ctx
    mock_scp_cls.side_effect = None

    # We need to capture the progress function passed to SCPClient()
    original_init = mock_scp_cls

    def _capture_scp_init(*args, **kwargs):
        nonlocal captured_progress
        captured_progress = kwargs.get("progress")
        return ctx

    mock_scp_cls.side_effect = _capture_scp_init

    driver.send_program(nc_file, progress_cb=_progress_cb)

    # Simulate what SCP would do: call the captured progress function
    assert captured_progress is not None, "SCPClient should receive a progress callback"
    file_size = nc_file.stat().st_size
    captured_progress(b"O1234.nc", file_size, file_size // 2)
    captured_progress(b"O1234.nc", file_size, file_size)

    assert len(progress_calls) == 2
    assert progress_calls[0] == (file_size // 2, file_size)
    assert progress_calls[1] == (file_size, file_size)


# -------------------------------------------------------------------
# Default ssh_host/ssh_user fallbacks
# -------------------------------------------------------------------


def test_defaults_to_ip_and_haasmill1() -> None:
    """When ssh_host/ssh_user are empty, driver falls back to ip / 'haasmill1'."""
    m = Machine(
        id="M1",
        name="Haas Test",
        type="Mill",
        driver=DriverType.HAAS_CHC,
        ip="192.168.1.50",
        port=22,
        ssh_host="",
        ssh_user="",
    )
    d = HaasChcSshDriver(m)
    assert d._ssh_host == "192.168.1.50"
    assert d._ssh_user == "haasmill1"
