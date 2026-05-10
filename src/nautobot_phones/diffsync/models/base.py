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

from datetime import datetime
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
    _attributes = ("alerting_name", "voicemail_profile__name", "vendor_extras")

    extension: str
    partition__name: str
    partition__phone_system__name: str
    alerting_name: str = ""
    voicemail_profile__name: Optional[str] = None
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
        "media_zone",
        # Live Status (from RisPort70 — only diffed when RIS enrichment is on)
        "active_load", "inactive_load", "live_login_user", "status_reason",
        "live_status_polled_at",
        # Vendor-agnostic device profile FK + general identity fields
        "device_profile__name",
        "owner_user_id", "user_locale",
        "dnd_status",
        # Vendor extras carries CCM-specific config (built_in_bridge,
        # device_mobility_mode, CSS refs, MTP, button templates, etc.)
        # plus axl_model used by post-sync device-creation.
        "vendor_extras",
    )

    device_name: str
    phone_system__name: str
    mac_address: Optional[str] = None
    device_kind: str = "sep"
    description: str = ""
    registration_status: str = "unknown"
    last_registered_ip: Optional[str] = None
    media_zone: str = ""
    # Live Status
    active_load: str = ""
    inactive_load: str = ""
    live_login_user: str = ""
    status_reason: str = ""
    live_status_polled_at: Optional[datetime] = None
    # Device Profile + general identity
    device_profile__name: Optional[str] = None
    owner_user_id: str = ""
    user_locale: str = ""
    dnd_status: bool = False
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
        # Per-line enrichment (general telephony — kept as columns)
        "max_num_calls", "busy_trigger", "missed_call_logging",
        # Vendor-specific per-line config (CCM MWI policy, partition usage,
        # ring-setting variants, recording flag) lives in vendor_extras.
        "vendor_extras",
    )

    phone__device_name: str
    phone__phone_system__name: str
    button_index: int
    directory_number__extension: str
    directory_number__partition__name: str
    label: str = ""
    ring_setting: str = ""
    max_num_calls: Optional[int] = None
    busy_trigger: Optional[int] = None
    missed_call_logging: bool = True
    vendor_extras: dict = {}


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


class RouteListMemberModel(NautobotModel):
    """DiffSync through-table — RouteList ↔ RouteGroup with priority.

    Identifier shape (route_list_name, phone_system_name, route_group_name)
    — phone_system is denormalized for stability since both RouteList and
    RouteGroup belong to the same PhoneSystem and we want priority order
    cross-vendor-portable.
    """

    _model = models.RouteListMember
    _modelname = "route_list_member"
    _identifiers = (
        "route_list__name", "route_list__phone_system__name",
        "route_group__name",
    )
    _attributes = ("priority",)

    route_list__name: str
    route_list__phone_system__name: str
    route_group__name: str
    priority: int = 0


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
        "target_dn__extension",
        "target_dn__partition__name",
        "css__name",
    )

    pattern: str
    partition__name: str
    partition__phone_system__name: str
    urgent: bool = False
    discard_digits: str = ""
    target_trunk__name: Optional[str] = None
    target_route_list__name: Optional[str] = None
    # target_dn is a FK to DirectoryNumber. The natural-key chain here
    # mirrors how DirectoryNumber is identified (by extension within
    # a partition), so the contrib framework can resolve it at sync time.
    target_dn__extension: Optional[str] = None
    target_dn__partition__name: Optional[str] = None
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


class HuntListModel(NautobotModel):
    """DiffSync model for HuntList — priority list of LineGroups."""

    _model = models.HuntList
    _modelname = "hunt_list"
    _identifiers = ("name", "phone_system__name")
    _attributes = ("description", "route_list_enabled", "voice_mail_usage", "vendor_extras")

    name: str
    phone_system__name: str
    description: str = ""
    route_list_enabled: bool = True
    voice_mail_usage: bool = False
    vendor_extras: dict = {}


class LineGroupModel(NautobotModel):
    """DiffSync model for LineGroup — distribution algorithm over a list of DNs."""

    _model = models.LineGroup
    _modelname = "line_group"
    _identifiers = ("name", "phone_system__name")
    _attributes = (
        "distribution_algorithm", "rna_reversion_timeout",
        "hunt_algorithm_no_answer", "hunt_algorithm_busy", "hunt_algorithm_not_available",
        "auto_log_off_hunt", "vendor_extras",
    )

    name: str
    phone_system__name: str
    distribution_algorithm: str = ""
    rna_reversion_timeout: Optional[int] = None
    hunt_algorithm_no_answer: str = ""
    hunt_algorithm_busy: str = ""
    hunt_algorithm_not_available: str = ""
    auto_log_off_hunt: bool = False
    vendor_extras: dict = {}


class HuntListMemberModel(NautobotModel):
    """DiffSync model for HuntListMember — through-table linking HuntList → LineGroup."""

    _model = models.HuntListMember
    _modelname = "hunt_list_member"
    _identifiers = (
        "hunt_list__name", "hunt_list__phone_system__name",
        "line_group__name",
    )
    _attributes = ("selection_order",)

    hunt_list__name: str
    hunt_list__phone_system__name: str
    line_group__name: str
    selection_order: int = 1


class LineGroupMemberModel(NautobotModel):
    """DiffSync model for LineGroupMember — through-table linking LineGroup → DN."""

    _model = models.LineGroupMember
    _modelname = "line_group_member"
    _identifiers = (
        "line_group__name", "line_group__phone_system__name",
        "directory_number__extension", "directory_number__partition__name",
    )
    _attributes = ("line_selection_order",)

    line_group__name: str
    line_group__phone_system__name: str
    directory_number__extension: str
    directory_number__partition__name: str
    line_selection_order: int = 0


class HuntPilotModel(NautobotModel):
    """DiffSync model for HuntPilot — dial pattern that triggers hunt-list distribution."""

    _model = models.HuntPilot
    _modelname = "hunt_pilot"
    _identifiers = ("pattern", "partition__name", "partition__phone_system__name")
    _attributes = (
        "description", "hunt_list__name", "alerting_name", "max_hunt_duration",
        "forward_hunt_no_answer_destination", "forward_hunt_busy_destination",
        "vendor_extras",
    )

    pattern: str
    partition__name: str
    partition__phone_system__name: str
    description: str = ""
    hunt_list__name: Optional[str] = None
    alerting_name: str = ""
    max_hunt_duration: Optional[int] = None
    forward_hunt_no_answer_destination: str = ""
    forward_hunt_busy_destination: str = ""
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
    """DiffSync model for AnalogPort.

    Each AnalogPort is one (gateway, port_index) slot. For FXS ports
    that have an analog phone connected, directory_number__extension
    + directory_number__partition__name identify the bound DN.
    """

    _model = models.AnalogPort
    _modelname = "analog_port"
    _identifiers = ("port_index", "gateway__name", "gateway__phone_system__name")
    _attributes = (
        "port_type",
        "directory_number__extension",
        "directory_number__partition__name",
    )

    port_index: int
    gateway__name: str
    gateway__phone_system__name: str
    port_type: str
    directory_number__extension: Optional[str] = None
    directory_number__partition__name: Optional[str] = None


# --------------------------------------------------------------------------
# Vendor-agnostic feature config — DeviceProfile, VoicemailProfile,
# CallPickupGroup. These are referenced by FK from Phone/DN, so they MUST
# load before Phone and DirectoryNumber in the adapter top_level.
# --------------------------------------------------------------------------


class DeviceProfileModel(NautobotModel):
    """DiffSync model for DeviceProfile (CCM DevicePool / FreePBX device template)."""

    _model = models.DeviceProfile
    _modelname = "device_profile"
    _identifiers = ("name", "phone_system__name")
    _attributes = ("description", "vendor_extras")

    name: str
    phone_system__name: str
    description: str = ""
    vendor_extras: dict = {}


class VoicemailProfileModel(NautobotModel):
    """DiffSync model for VoicemailProfile."""

    _model = models.VoicemailProfile
    _modelname = "voicemail_profile"
    _identifiers = ("name", "phone_system__name")
    _attributes = ("description", "pilot_dn", "is_default", "vendor_extras")

    name: str
    phone_system__name: str
    description: str = ""
    pilot_dn: str = ""
    is_default: bool = False
    vendor_extras: dict = {}


class CallPickupGroupModel(NautobotModel):
    """DiffSync model for CallPickupGroup."""

    _model = models.CallPickupGroup
    _modelname = "call_pickup_group"
    _identifiers = ("name", "phone_system__name")
    _attributes = (
        "pattern", "partition__name", "description", "vendor_extras",
    )

    name: str
    phone_system__name: str
    pattern: str = ""
    partition__name: Optional[str] = None
    description: str = ""
    vendor_extras: dict = {}


class CallPickupGroupMemberModel(NautobotModel):
    """DiffSync through-table for CallPickupGroup ↔ DirectoryNumber."""

    _model = models.CallPickupGroupMember
    _modelname = "call_pickup_group_member"
    _identifiers = (
        "pickup_group__name", "pickup_group__phone_system__name",
        "directory_number__extension", "directory_number__partition__name",
    )
    _attributes = ("priority",)

    pickup_group__name: str
    pickup_group__phone_system__name: str
    directory_number__extension: str
    directory_number__partition__name: str
    priority: int = 0
