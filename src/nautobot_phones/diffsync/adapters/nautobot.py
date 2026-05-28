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

from nautobot_phones.diffsync.models.gfk import GFKNautobotModel

from nautobot_phones.diffsync.models import (
    AnalogGatewayModel,
    AnalogPortModel,
    BusyLampFieldModel,
    CallPickupGroupMemberModel,
    CallPickupGroupModel,
    CallingSearchSpaceModel,
    CSSPartitionMembershipModel,
    DeviceProfileModel,
    DIDAssignmentModel,
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
    RouteGroupMemberModel,
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
    route_group_member = RouteGroupMemberModel
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
    # DIDAssignment uses a GFK that can point at DirectoryNumber OR Trunk;
    # both must be loaded before this entry so the read-path GFK extractor
    # can dereference target.partition.phone_system / target.phone_system.
    did_assignment = DIDAssignmentModel

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
        # Through-tables come after both parents are loaded.
        "route_list_member",
        "route_pattern",
        "translation_pattern",
        "analog_gateway",
        "analog_port",
        # GFK through-table — must follow both target kinds (trunk +
        # analog_gateway) so create-time natural-key resolution succeeds.
        "route_group_member",
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
        # DIDAssignment last — its GFK target can be a DN or Trunk, both
        # already loaded above. The model is operator-driven (no source
        # adapter emits these), so on a fresh sync this load just snapshots
        # whatever the operator created.
        "did_assignment",
    )

    # Models that only get populated by per-phone getPhone enrichment.
    # Excluded from the diff when enrich is off, so existing records aren't
    # orphan-deleted by a plain sync.
    _BUTTON_MODELS = ("line", "speed_dial", "busy_lamp_field", "phone_service_url")

    def __init__(self, *args, include_lines=True, delete_policy=None, **kwargs):
        """`include_lines=False` excludes per-phone button models from diff.

        Pair with the source adapter's `enrich_phone_lines=False` to leave
        existing Line / SpeedDial / PhoneServiceUrl records in Nautobot
        alone when the sync isn't doing the slow per-phone getPhone
        enrichment. Both adapters need to agree, otherwise DiffSync sees
        an empty source vs populated dest and tries to delete the orphans.

        ``delete_policy`` (default ``{}``) is the per-model action map
        sourced from ``PhoneSystem.delete_policy``. Each
        ``PolicyAwareNautobotModel`` subclass consults this dict during
        its ``delete()`` to decide between delete / ignore / flag.
        Empty dict → vanilla delete behavior on every model.
        """
        super().__init__(*args, **kwargs)
        if not include_lines:
            self.top_level = tuple(t for t in self.top_level if t not in self._BUTTON_MODELS)
        # Per-model delete-policy dispatch (Phase 6).
        # Read by ``PolicyAwareNautobotModel.delete()`` on each model.
        self.delete_policy = delete_policy or {}

    def _handle_single_parameter(self, parameters, parameter_name, database_object, diffsync_model):
        """Special-case virtual GFK identifier fields before the framework
        tries ``_meta.get_field()`` on them.

        Virtual GFK fields (``target_kind``, ``target_name``, and for
        DIDAssignment-style models also ``target_partition__name`` and
        ``target_phone_system__name``) aren't real ORM fields — they're
        derived from the GFK pair (``target_type`` ContentType +
        ``target`` GenericForeignKey instance). Without this short-circuit
        the framework's default path raises ``FieldDoesNotExist``.

        Dispatch delegates to ``GFKNautobotModel._extract_gfk_virtual_field``,
        which knows how to pull the right attribute off the target ORM
        object based on the per-kind ``_gfk_reads`` extractor.
        """
        if parameter_name.startswith("target_") and (
            isinstance(diffsync_model, type)
            and issubclass(diffsync_model, GFKNautobotModel)
        ):
            parameters[parameter_name] = diffsync_model._extract_gfk_virtual_field(
                database_object, parameter_name,
            )
            return
        return super()._handle_single_parameter(
            parameters, parameter_name, database_object, diffsync_model,
        )
