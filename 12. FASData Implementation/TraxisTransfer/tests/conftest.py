"""Shared test fixtures for TraxisTransfer."""

import pytest

from traxistransfer.constants import DriverType
from traxistransfer.models.machine import Machine


@pytest.fixture
def fanuc_machine() -> Machine:
    """A test Fanuc machine."""
    return Machine(
        id="M6",
        name="FANUC Mill 6",
        type="Mill",
        driver=DriverType.FOCAS,
        ip="10.1.1.106",
        port=8193,
        proshop_pot_id="Mill-6",
    )


@pytest.fixture
def haas_machine() -> Machine:
    """A test Haas CHC machine."""
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
