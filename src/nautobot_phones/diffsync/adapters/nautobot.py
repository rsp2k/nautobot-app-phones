"""Nautobot-side DiffSync adapter.

This adapter loads from Nautobot's ORM (the destination side of our
mirror flow) and provides the CRUD methods that DiffSync calls when
applying source-side changes.

`NautobotAdapter` from `nautobot_ssot.contrib` auto-generates the `load()`
implementation: it walks `top_level` models, queries the ORM via each
model's `_get_queryset()`, and instantiates DiffSync model objects from
the rows. We just have to register the classes.

`top_level` is the discovery order: PhoneSystem first (it's the root),
then dial-plan structure (Partition, CSS), then numbers (DirectoryNumber),
then endpoints (Phone, AnalogGateway), then their children (Line,
AnalogPort), then routing (Trunk, RoutePattern). Order matters for
identifier resolution — children reference parents by natural key.
"""

from nautobot_ssot.contrib import NautobotAdapter as ContribNautobotAdapter

from nautobot_phones.diffsync.models import (
    AnalogGatewayModel,
    AnalogPortModel,
    BusyLampFieldModel,
    CallPickupGroupMemberModel,
    CallPickupGroupModel,
    CallingSearchSpaceModel,
    CSSPartitionMembershipModel,
    DeviceProfileModel,
    DirectoryNumberModel,
    HuntListMemberModel,
    HuntListModel,
    HuntPilotModel,
    LineGroupMemberModel,
    LineGroupModel,
    LineModel,
    PartitionModel,
    PhoneModel,
    PhoneServiceUrlModel,
    PhoneSystemModel,
    RouteGroupModel,
    RouteListMemberModel,
    RouteListModel,
    RoutePatternModel,
    SpeedDialModel,
    TranslationPatternModel,
    TrunkModel,
    VoicemailProfileModel,
)


class PhonesNautobotAdapter(ContribNautobotAdapter):
    """Loads our app's models from Nautobot for DiffSync comparison."""

    phone_system = PhoneSystemModel
    partition = PartitionModel
    calling_search_space = CallingSearchSpaceModel
    css_partition_membership = CSSPartitionMembershipModel
    # Vendor-agnostic feature config — referenced by FK from Phone/DN, so
    # MUST load before them in top_level for natural-key resolution.
    device_profile = DeviceProfileModel
    voicemail_profile = VoicemailProfileModel
    directory_number = DirectoryNumberModel
    phone = PhoneModel
    line = LineModel
    speed_dial = SpeedDialModel
    busy_lamp_field = BusyLampFieldModel
    phone_service_url = PhoneServiceUrlModel
    trunk = TrunkModel
    route_list = RouteListModel
    route_group = RouteGroupModel
    route_list_member = RouteListMemberModel
    route_pattern = RoutePatternModel
    translation_pattern = TranslationPatternModel
    analog_gateway = AnalogGatewayModel
    analog_port = AnalogPortModel
    hunt_list = HuntListModel
    line_group = LineGroupModel
    hunt_list_member = HuntListMemberModel
    line_group_member = LineGroupMemberModel
    hunt_pilot = HuntPilotModel
    call_pickup_group = CallPickupGroupModel
    call_pickup_group_member = CallPickupGroupMemberModel

    top_level = (
        "phone_system",
        "partition",
        "calling_search_space",
        "css_partition_membership",
        # Feature config (DeviceProfile / VoicemailProfile) loads before
        # Phone and DN because those reference these via FK.
        "device_profile",
        "voicemail_profile",
        "directory_number",
        "phone",
        "line",
        "speed_dial",
        "busy_lamp_field",
        "phone_service_url",
        "trunk",
        "route_list",
        "route_group",
        # Through-table comes after both parents are loaded.
        "route_list_member",
        "route_pattern",
        "translation_pattern",
        "analog_gateway",
        "analog_port",
        # Hunt subsystem — order: groups first (referenced by lists),
        # lists next (referenced by pilots), members last.
        "line_group",
        "hunt_list",
        "line_group_member",
        "hunt_list_member",
        "hunt_pilot",
        # Pickup group + members (DNs must already exist).
        "call_pickup_group",
        "call_pickup_group_member",
    )

    # Models that only get populated by per-phone getPhone enrichment.
    # Excluded from the diff when enrich is off, so existing records aren't
    # orphan-deleted by a plain sync.
    _BUTTON_MODELS = ("line", "speed_dial", "busy_lamp_field", "phone_service_url")

    def __init__(self, *args, include_lines=True, **kwargs):
        """`include_lines=False` excludes per-phone button models from diff.

        Pair with the source adapter's `enrich_phone_lines=False` to leave
        existing Line / SpeedDial / PhoneServiceUrl records in Nautobot
        alone when the sync isn't doing the slow per-phone getPhone
        enrichment. Both adapters need to agree, otherwise DiffSync sees
        an empty source vs populated dest and tries to delete the orphans.
        """
        super().__init__(*args, **kwargs)
        if not include_lines:
            self.top_level = tuple(t for t in self.top_level if t not in self._BUTTON_MODELS)
