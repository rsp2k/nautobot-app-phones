"""DiffSync model classes mirroring our Nautobot models.

Subclasses `nautobot_ssot.contrib.NautobotModel` which auto-generates
`create()`, `update()`, and `delete()` methods from the type annotations
and `_model` reference. We declare the schema (identifiers, attributes,
field types) and the framework handles ORM CRUD.

Convention: `_identifiers` mirrors the Django `unique_together` /
`unique=True` constraints for each model so DiffSync can match records
across source and destination adapters consistently.

Foreign-key fields use the `relation__name` form (double-underscore) —
this lets the contrib framework navigate FKs by their natural key without
us hand-writing prefetch logic.
"""

from typing import Optional

from nautobot_ssot.contrib import NautobotModel
from pydantic import field_validator

from nautobot_phones import models


class PhoneSystemModel(NautobotModel):
    """DiffSync model for PhoneSystem."""

    _model = models.PhoneSystem
    _modelname = "phone_system"
    _identifiers = ("name",)
    _attributes = ("vendor", "version", "hostname")

    name: str
    vendor: str
    version: str = ""
    hostname: str = ""


class PartitionModel(NautobotModel):
    """DiffSync model for Partition."""

    _model = models.Partition
    _modelname = "partition"
    _identifiers = ("name", "phone_system__name")
    _attributes = ("description",)

    name: str
    phone_system__name: str
    description: str = ""


class CallingSearchSpaceModel(NautobotModel):
    """DiffSync model for CallingSearchSpace."""

    _model = models.CallingSearchSpace
    _modelname = "calling_search_space"
    _identifiers = ("name", "phone_system__name")
    _attributes = ("description",)

    name: str
    phone_system__name: str
    description: str = ""


class CSSPartitionMembershipModel(NautobotModel):
    """DiffSync model for CSSPartitionMembership (through-table).

    Identifier shape: (css's phone_system, css's name, partition's name).
    Partition's phone_system is implied — CCM never lets a CSS reference a
    partition from a different phone system.
    """

    _model = models.CSSPartitionMembership
    _modelname = "css_partition_membership"
    _identifiers = ("css__phone_system__name", "css__name", "partition__name")
    _attributes = ("priority",)

    css__phone_system__name: str
    css__name: str
    partition__name: str
    priority: int = 1


class DirectoryNumberModel(NautobotModel):
    """DiffSync model for DirectoryNumber."""

    _model = models.DirectoryNumber
    _modelname = "directory_number"
    _identifiers = ("extension", "partition__name", "partition__phone_system__name")
    _attributes = ("alerting_name", "voicemail_profile", "vendor_extras")

    extension: str
    partition__name: str
    partition__phone_system__name: str
    alerting_name: str = ""
    voicemail_profile: str = ""
    vendor_extras: dict = {}


class PhoneModel(NautobotModel):
    """DiffSync model for Phone.

    `mac_address` comes from Nautobot's MACAddressCharField as a netaddr `EUI`
    object — Pydantic doesn't auto-coerce that to str, so we add a validator.
    """

    _model = models.Phone
    _modelname = "phone"
    _identifiers = ("mac_address", "phone_system__name")
    _attributes = ("device_name", "model", "registration_status", "last_registered_ip", "vendor_extras")

    mac_address: str
    phone_system__name: str
    device_name: str
    model: str = ""
    registration_status: str = "unknown"
    last_registered_ip: Optional[str] = None
    vendor_extras: dict = {}

    @field_validator("mac_address", mode="before")
    @classmethod
    def _coerce_mac_to_str(cls, v):
        """Convert netaddr.EUI to canonical lowercase string for diff stability."""
        return str(v).lower() if v is not None else v


class LineModel(NautobotModel):
    """DiffSync model for Line (phone-button appearance).

    Identifier shape (phone, button_index) matches the Django unique_together;
    AXL returns lines as ordered children of phones, so the integer
    button_index lets DiffSync diff them set-comparably.
    """

    _model = models.Line
    _modelname = "line"
    _identifiers = ("phone__device_name", "phone__phone_system__name", "button_index")
    _attributes = ("directory_number__extension", "directory_number__partition__name", "label", "ring_setting")

    phone__device_name: str
    phone__phone_system__name: str
    button_index: int
    directory_number__extension: str
    directory_number__partition__name: str
    label: str = ""
    ring_setting: str = ""


class TrunkModel(NautobotModel):
    """DiffSync model for Trunk."""

    _model = models.Trunk
    _modelname = "trunk"
    _identifiers = ("name", "phone_system__name")
    _attributes = ("trunk_type", "destination_address", "destination_port", "vendor_extras")

    name: str
    phone_system__name: str
    trunk_type: str
    destination_address: str = ""
    destination_port: Optional[int] = None
    vendor_extras: dict = {}


class RouteListModel(NautobotModel):
    """DiffSync model for RouteList."""

    _model = models.RouteList
    _modelname = "route_list"
    _identifiers = ("name", "phone_system__name")
    _attributes = ("description", "vendor_extras")

    name: str
    phone_system__name: str
    description: str = ""
    vendor_extras: dict = {}


class RouteGroupModel(NautobotModel):
    """DiffSync model for RouteGroup."""

    _model = models.RouteGroup
    _modelname = "route_group"
    _identifiers = ("name", "phone_system__name")
    _attributes = ("distribution_algorithm", "description", "vendor_extras")

    name: str
    phone_system__name: str
    distribution_algorithm: str = "top_down"
    description: str = ""
    vendor_extras: dict = {}


class RoutePatternModel(NautobotModel):
    """DiffSync model for RoutePattern.

    Exactly one of target_trunk / target_route_list / target_dn is set
    (XOR check constraint at the DB layer). Resolution happens via the
    natural-key __name attributes — the contrib framework looks up the
    matching ORM record at create/update time.
    """

    _model = models.RoutePattern
    _modelname = "route_pattern"
    _identifiers = ("pattern", "partition__name", "partition__phone_system__name")
    _attributes = (
        "urgent",
        "discard_digits",
        "target_trunk__name",
        "target_route_list__name",
        "css__name",
    )

    pattern: str
    partition__name: str
    partition__phone_system__name: str
    urgent: bool = False
    discard_digits: str = ""
    target_trunk__name: Optional[str] = None
    target_route_list__name: Optional[str] = None
    css__name: Optional[str] = None


class AnalogGatewayModel(NautobotModel):
    """DiffSync model for AnalogGateway."""

    _model = models.AnalogGateway
    _modelname = "analog_gateway"
    _identifiers = ("name", "phone_system__name")
    _attributes = ("model", "protocol", "vendor_extras")

    name: str
    phone_system__name: str
    model: str = ""
    protocol: str
    vendor_extras: dict = {}


class AnalogPortModel(NautobotModel):
    """DiffSync model for AnalogPort."""

    _model = models.AnalogPort
    _modelname = "analog_port"
    _identifiers = ("port_index", "gateway__name", "gateway__phone_system__name")
    _attributes = ("port_type",)

    port_index: int
    gateway__name: str
    gateway__phone_system__name: str
    port_type: str
