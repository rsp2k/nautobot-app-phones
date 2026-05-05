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
    DirectoryNumberModel,
    LineModel,
    PartitionModel,
    PhoneModel,
    PhoneSystemModel,
    RouteGroupModel,
    RouteListModel,
    RoutePatternModel,
    TrunkModel,
)


class PhonesNautobotAdapter(ContribNautobotAdapter):
    """Loads our app's models from Nautobot for DiffSync comparison."""

    phone_system = PhoneSystemModel
    partition = PartitionModel
    calling_search_space = CallingSearchSpaceModel
    directory_number = DirectoryNumberModel
    phone = PhoneModel
    line = LineModel
    trunk = TrunkModel
    route_list = RouteListModel
    route_group = RouteGroupModel
    route_pattern = RoutePatternModel
    analog_gateway = AnalogGatewayModel
    analog_port = AnalogPortModel

    top_level = (
        "phone_system",
        "partition",
        "calling_search_space",
        "directory_number",
        "phone",
        "line",
        "trunk",
        "route_list",
        "route_group",
        "route_pattern",
        "analog_gateway",
        "analog_port",
    )
