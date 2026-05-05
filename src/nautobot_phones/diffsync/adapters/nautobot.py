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
    CallingSearchSpaceModel,
    CSSPartitionMembershipModel,
    DirectoryNumberModel,
    LineModel,
    PartitionModel,
    PhoneModel,
    PhoneServiceUrlModel,
    PhoneSystemModel,
    RouteGroupModel,
    RouteListModel,
    RoutePatternModel,
    SpeedDialModel,
    TranslationPatternModel,
    TrunkModel,
)


class PhonesNautobotAdapter(ContribNautobotAdapter):
    """Loads our app's models from Nautobot for DiffSync comparison."""

    phone_system = PhoneSystemModel
    partition = PartitionModel
    calling_search_space = CallingSearchSpaceModel
    css_partition_membership = CSSPartitionMembershipModel
    directory_number = DirectoryNumberModel
    phone = PhoneModel
    line = LineModel
    speed_dial = SpeedDialModel
    phone_service_url = PhoneServiceUrlModel
    trunk = TrunkModel
    route_list = RouteListModel
    route_group = RouteGroupModel
    route_pattern = RoutePatternModel
    translation_pattern = TranslationPatternModel
    analog_gateway = AnalogGatewayModel
    analog_port = AnalogPortModel

    top_level = (
        "phone_system",
        "partition",
        "calling_search_space",
        "css_partition_membership",
        "directory_number",
        "phone",
        "line",
        "speed_dial",
        "phone_service_url",
        "trunk",
        "route_list",
        "route_group",
        "route_pattern",
        "translation_pattern",
        "analog_gateway",
        "analog_port",
    )

    # Models that only get populated by per-phone getPhone enrichment.
    # Excluded from the diff when enrich is off, so existing records aren't
    # orphan-deleted by a plain sync.
    _BUTTON_MODELS = ("line", "speed_dial", "phone_service_url")

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
