"""Machine data model."""

from __future__ import annotations

from dataclasses import dataclass, field

from traxistransfer.constants import DriverType


@dataclass
class Machine:
    """Represents a CNC machine on the shop floor."""

    id: str
    name: str
    type: str  # "Mill" or "Lathe"
    driver: DriverType
    ip: str
    port: int
    enabled: bool = True
    proshop_pot_id: str = ""
    notes: str = ""
    # Haas SSH-specific
    ssh_host: str = ""
    ssh_user: str = ""
    # Runtime state (not persisted)
    reachable: bool = field(default=False, repr=False)

    @classmethod
    def from_dict(cls, data: dict) -> Machine:
        """Create a Machine from a machines.json entry."""
        driver_str = data.get("driver", "focas")
        try:
            driver = DriverType(driver_str)
        except ValueError:
            driver = DriverType.FOCAS

        return cls(
            id=data["id"],
            name=data["name"],
            type=data.get("type", "Mill"),
            driver=driver,
            ip=data.get("ip", ""),
            port=data.get("port", 8193),
            enabled=data.get("enabled", True),
            proshop_pot_id=data.get("proshop_pot_id", ""),
            notes=data.get("notes", ""),
            ssh_host=data.get("ssh_host", ""),
            ssh_user=data.get("ssh_user", ""),
        )

    @property
    def display_name(self) -> str:
        """Short label for UI: 'M6 — FANUC Mill 6'."""
        return f"{self.id} \u2014 {self.name}"
