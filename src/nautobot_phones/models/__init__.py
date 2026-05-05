"""Data models for nautobot-app-phones.

Models are split across topical files (system, dialplan, numbers, endpoints,
gateways, routing) and re-exported here so Django's app loading discovers
them all and so callers can `from nautobot_phones.models import X`.
"""

from nautobot_phones.models.dialplan import (
    CallingSearchSpace,
    CSSPartitionMembership,
    Partition,
)
from nautobot_phones.models.endpoints import BusyLampField, Line, Phone, PhoneServiceUrl, SpeedDial
from nautobot_phones.models.gateways import AnalogGateway, AnalogPort
from nautobot_phones.models.numbers import (
    DID,
    Carrier,
    DIDAssignment,
    DIDBlock,
    DirectoryNumber,
)
from nautobot_phones.models.routing import (
    RouteGroup,
    RouteGroupMember,
    RouteList,
    RouteListMember,
    RoutePattern,
    TranslationPattern,
    Trunk,
)
from nautobot_phones.models.system import PhoneSystem

__all__ = [
    "AnalogGateway",
    "AnalogPort",
    "BusyLampField",
    "CSSPartitionMembership",
    "CallingSearchSpace",
    "Carrier",
    "DID",
    "DIDAssignment",
    "DIDBlock",
    "DirectoryNumber",
    "Line",
    "Partition",
    "Phone",
    "PhoneServiceUrl",
    "PhoneSystem",
    "SpeedDial",
    "RouteGroup",
    "RouteGroupMember",
    "RouteList",
    "RouteListMember",
    "RoutePattern",
    "TranslationPattern",
    "Trunk",
]
