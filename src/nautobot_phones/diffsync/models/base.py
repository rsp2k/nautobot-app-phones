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
    # device_name is the canonical CCM identifier across all device types.
    # mac_address is optional (only SEP/ATA have one) — moved to attributes.
    _identifiers = ("device_name", "phone_system__name")
    _attributes = (
        "mac_address", "device_kind", "description",
        "registration_status", "last_registered_ip",
        "ccm_location", "network_location",
        # Device Information
        "device_pool", "common_phone_profile", "common_device_configuration",
        "phone_button_template", "softkey_template",
        "owner_user_id", "mobility_user_id",
        "built_in_bridge", "privacy", "device_mobility_mode",
        "always_use_prime_line", "always_use_prime_line_for_voice",
        "user_locale", "network_locale", "aar_neighborhood",
        "dnd_status", "dnd_option",
        # Protocol Specific
        "device_security_profile", "sip_profile", "rerouting_css", "subscribe_css",
        "mtp_required", "packet_capture_mode",
        # Vendor extras (carries axl_model used by post-sync device-creation)
        "vendor_extras",
    )

    device_name: str
    phone_system__name: str
    mac_address: Optional[str] = None
    device_kind: str = "sep"
    description: str = ""
    registration_status: str = "unknown"
    last_registered_ip: Optional[str] = None
    ccm_location: str = ""
    network_location: str = ""
    # Device Information
    device_pool: str = ""
    common_phone_profile: str = ""
    common_device_configuration: str = ""
    phone_button_template: str = ""
    softkey_template: str = ""
    owner_user_id: str = ""
    mobility_user_id: str = ""
    built_in_bridge: str = ""
    privacy: str = ""
    device_mobility_mode: str = ""
    always_use_prime_line: str = ""
    always_use_prime_line_for_voice: str = ""
    user_locale: str = ""
    network_locale: str = ""
    aar_neighborhood: str = ""
    dnd_status: bool = False
    dnd_option: str = ""
    # Protocol Specific
    device_security_profile: str = ""
    sip_profile: str = ""
    rerouting_css: str = ""
    subscribe_css: str = ""
    mtp_required: bool = False
    packet_capture_mode: str = ""
    # Vendor extras
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

    Per-line fields (max_num_calls, busy_trigger, MWI policy, recording flag)
    come from getPhone enrichment — they're nested in lines.line[*] and
    not present in the bulk listPhone response.
    """

    _model = models.Line
    _modelname = "line"
    _identifiers = ("phone__device_name", "phone__phone_system__name", "button_index")
    _attributes = (
        "directory_number__extension", "directory_number__partition__name",
        "label", "ring_setting",
        # Per-line enrichment from getPhone
        "max_num_calls", "busy_trigger", "mwl_policy", "audible_mwi",
        "recording_flag", "missed_call_logging", "partition_usage",
        "consecutive_ring_setting",
        "ring_setting_idle_pickup_alert", "ring_setting_active_pickup_alert",
    )

    phone__device_name: str
    phone__phone_system__name: str
    button_index: int
    directory_number__extension: str
    directory_number__partition__name: str
    label: str = ""
    ring_setting: str = ""
    # Per-line enrichment
    max_num_calls: Optional[int] = None
    busy_trigger: Optional[int] = None
    mwl_policy: str = ""
    audible_mwi: str = ""
    recording_flag: str = ""
    missed_call_logging: bool = True
    partition_usage: str = ""
    consecutive_ring_setting: str = ""
    ring_setting_idle_pickup_alert: str = ""
    ring_setting_active_pickup_alert: str = ""


class BusyLampFieldModel(NautobotModel):
    """DiffSync model for a Busy Lamp Field button."""

    _model = models.BusyLampField
    _modelname = "busy_lamp_field"
    _identifiers = ("phone__device_name", "phone__phone_system__name", "button_index")
    _attributes = ("destination", "label", "asterisk_service")

    phone__device_name: str
    phone__phone_system__name: str
    button_index: int
    destination: str
    label: str = ""
    asterisk_service: bool = False


class SpeedDialModel(NautobotModel):
    """DiffSync model for a SpeedDial button."""

    _model = models.SpeedDial
    _modelname = "speed_dial"
    _identifiers = ("phone__device_name", "phone__phone_system__name", "button_index")
    _attributes = ("number", "label")

    phone__device_name: str
    phone__phone_system__name: str
    button_index: int
    number: str
    label: str = ""


class PhoneServiceUrlModel(NautobotModel):
    """DiffSync model for a Phone Service URL button."""

    _model = models.PhoneServiceUrl
    _modelname = "phone_service_url"
    _identifiers = ("phone__device_name", "phone__phone_system__name", "button_index")
    _attributes = ("url", "label")

    phone__device_name: str
    phone__phone_system__name: str
    button_index: int
    url: str
    label: str = ""


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


class TranslationPatternModel(NautobotModel):
    """DiffSync model for TranslationPattern.

    `_attributes` declares the fields that flow through the diff —
    grouped to mirror the CCM admin form's three sections. Long-tail
    AXL fields (presentation bits, numbering plans, number types)
    accumulate in `vendor_extras` so the diff sees them as a single
    JSON blob rather than ~10 individual attributes that would never
    differ between syncs (those values are almost universally Default).
    """

    _model = models.TranslationPattern
    _modelname = "translation_pattern"
    _identifiers = ("pattern", "partition__name", "partition__phone_system__name")
    _attributes = (
        "description", "css__name",
        # Pattern Definition
        "block_enable", "release_clause", "urgent_priority",
        "provide_outside_dial_tone", "use_originator_css",
        "dont_wait_for_idt", "route_next_hop_by_cgpn",
        "is_emergency_service_number", "route_class",
        # Calling Party Transformations
        "use_calling_party_phone_mask", "calling_party_transformation_mask",
        "calling_party_prefix_digits",
        # Called Party Transformations
        "digit_discard_instruction", "called_party_transformation_mask",
        "prefix_digits_out",
        # Long-tail JSON
        "vendor_extras",
    )

    pattern: str
    partition__name: str
    partition__phone_system__name: str
    description: str = ""
    css__name: Optional[str] = None
    # Pattern Definition
    block_enable: bool = False
    release_clause: str = ""
    urgent_priority: bool = False
    provide_outside_dial_tone: bool = False
    use_originator_css: bool = False
    dont_wait_for_idt: bool = False
    route_next_hop_by_cgpn: bool = False
    is_emergency_service_number: bool = False
    route_class: str = ""
    # Calling Party Transformations
    use_calling_party_phone_mask: str = ""
    calling_party_transformation_mask: str = ""
    calling_party_prefix_digits: str = ""
    # Called Party Transformations
    digit_discard_instruction: str = ""
    called_party_transformation_mask: str = ""
    prefix_digits_out: str = ""
    # Long-tail JSON
    vendor_extras: dict = {}


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
