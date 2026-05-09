"""GraphQL types for nautobot-app-phones.

Discovered by Nautobot via the module-level `graphql_types` list at
`nautobot_phones.graphql.types.graphql_types`. Each ObjectType wraps a
model so it appears as a queryable field on the GraphQL root.
"""

from nautobot.apps.graphql import OptimizedNautobotObjectType

from nautobot_phones import filters, models


class PhoneSystemType(OptimizedNautobotObjectType):
    class Meta:
        model = models.PhoneSystem
        filterset_class = filters.PhoneSystemFilterSet


class CarrierType(OptimizedNautobotObjectType):
    class Meta:
        model = models.Carrier
        filterset_class = filters.CarrierFilterSet


class PartitionType(OptimizedNautobotObjectType):
    class Meta:
        model = models.Partition
        filterset_class = filters.PartitionFilterSet


class CallingSearchSpaceType(OptimizedNautobotObjectType):
    class Meta:
        model = models.CallingSearchSpace
        filterset_class = filters.CallingSearchSpaceFilterSet


class CSSPartitionMembershipType(OptimizedNautobotObjectType):
    class Meta:
        model = models.CSSPartitionMembership


class DirectoryNumberType(OptimizedNautobotObjectType):
    class Meta:
        model = models.DirectoryNumber
        filterset_class = filters.DirectoryNumberFilterSet


class DIDBlockType(OptimizedNautobotObjectType):
    class Meta:
        model = models.DIDBlock
        filterset_class = filters.DIDBlockFilterSet


class DIDType(OptimizedNautobotObjectType):
    class Meta:
        model = models.DID
        filterset_class = filters.DIDFilterSet


class DIDAssignmentType(OptimizedNautobotObjectType):
    class Meta:
        model = models.DIDAssignment


class PhoneType(OptimizedNautobotObjectType):
    class Meta:
        model = models.Phone
        filterset_class = filters.PhoneFilterSet


class LineType(OptimizedNautobotObjectType):
    class Meta:
        model = models.Line


class BusyLampFieldType(OptimizedNautobotObjectType):
    class Meta:
        model = models.BusyLampField


class TrunkType(OptimizedNautobotObjectType):
    class Meta:
        model = models.Trunk
        filterset_class = filters.TrunkFilterSet


class RouteListType(OptimizedNautobotObjectType):
    class Meta:
        model = models.RouteList
        filterset_class = filters.RouteListFilterSet


class RouteListMemberType(OptimizedNautobotObjectType):
    class Meta:
        model = models.RouteListMember


class RouteGroupType(OptimizedNautobotObjectType):
    class Meta:
        model = models.RouteGroup
        filterset_class = filters.RouteGroupFilterSet


class RouteGroupMemberType(OptimizedNautobotObjectType):
    class Meta:
        model = models.RouteGroupMember


class RoutePatternType(OptimizedNautobotObjectType):
    class Meta:
        model = models.RoutePattern
        filterset_class = filters.RoutePatternFilterSet


class TranslationPatternType(OptimizedNautobotObjectType):
    class Meta:
        model = models.TranslationPattern
        filterset_class = filters.TranslationPatternFilterSet


class AnalogGatewayType(OptimizedNautobotObjectType):
    class Meta:
        model = models.AnalogGateway
        filterset_class = filters.AnalogGatewayFilterSet


class AnalogPortType(OptimizedNautobotObjectType):
    class Meta:
        model = models.AnalogPort


class HuntPilotType(OptimizedNautobotObjectType):
    class Meta:
        model = models.HuntPilot
        filterset_class = filters.HuntPilotFilterSet


class HuntListType(OptimizedNautobotObjectType):
    class Meta:
        model = models.HuntList
        filterset_class = filters.HuntListFilterSet


class HuntListMemberType(OptimizedNautobotObjectType):
    class Meta:
        model = models.HuntListMember


class LineGroupType(OptimizedNautobotObjectType):
    class Meta:
        model = models.LineGroup
        filterset_class = filters.LineGroupFilterSet


class LineGroupMemberType(OptimizedNautobotObjectType):
    class Meta:
        model = models.LineGroupMember


class DeviceProfileType(OptimizedNautobotObjectType):
    class Meta:
        model = models.DeviceProfile
        filterset_class = filters.DeviceProfileFilterSet


class VoicemailProfileType(OptimizedNautobotObjectType):
    class Meta:
        model = models.VoicemailProfile
        filterset_class = filters.VoicemailProfileFilterSet


class CallPickupGroupType(OptimizedNautobotObjectType):
    class Meta:
        model = models.CallPickupGroup
        filterset_class = filters.CallPickupGroupFilterSet


class CallPickupGroupMemberType(OptimizedNautobotObjectType):
    class Meta:
        model = models.CallPickupGroupMember


graphql_types = [
    PhoneSystemType,
    CarrierType,
    PartitionType,
    CallingSearchSpaceType,
    CSSPartitionMembershipType,
    DirectoryNumberType,
    DIDBlockType,
    DIDType,
    DIDAssignmentType,
    PhoneType,
    LineType,
    BusyLampFieldType,
    TrunkType,
    RouteListType,
    RouteListMemberType,
    RouteGroupType,
    RouteGroupMemberType,
    RoutePatternType,
    TranslationPatternType,
    AnalogGatewayType,
    AnalogPortType,
    HuntPilotType,
    HuntListType,
    HuntListMemberType,
    LineGroupType,
    LineGroupMemberType,
    DeviceProfileType,
    VoicemailProfileType,
    CallPickupGroupType,
    CallPickupGroupMemberType,
]
