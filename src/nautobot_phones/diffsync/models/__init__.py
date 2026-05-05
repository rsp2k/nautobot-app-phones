"""DiffSync model definitions for nautobot-app-phones."""

from nautobot_phones.diffsync.models.base import (
    AnalogGatewayModel,
    AnalogPortModel,
    CallingSearchSpaceModel,
    CSSPartitionMembershipModel,
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

__all__ = [
    "AnalogGatewayModel",
    "AnalogPortModel",
    "CSSPartitionMembershipModel",
    "CallingSearchSpaceModel",
    "DirectoryNumberModel",
    "LineModel",
    "PartitionModel",
    "PhoneModel",
    "PhoneSystemModel",
    "RouteGroupModel",
    "RouteListModel",
    "RoutePatternModel",
    "TrunkModel",
]
