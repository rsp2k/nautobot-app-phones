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
    PhoneServiceUrlModel,
    PhoneSystemModel,
    RouteGroupModel,
    RouteListModel,
    RoutePatternModel,
    SpeedDialModel,
    TranslationPatternModel,
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
    "PhoneServiceUrlModel",
    "PhoneSystemModel",
    "RouteGroupModel",
    "RouteListModel",
    "RoutePatternModel",
    "SpeedDialModel",
    "TranslationPatternModel",
    "TrunkModel",
]
