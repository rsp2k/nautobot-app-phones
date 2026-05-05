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


class TrunkType(OptimizedNautobotObjectType):
    class Meta:
        model = models.Trunk
        filterset_class = filters.TrunkFilterSet


class RoutePatternType(OptimizedNautobotObjectType):
    class Meta:
        model = models.RoutePattern
        filterset_class = filters.RoutePatternFilterSet


class AnalogGatewayType(OptimizedNautobotObjectType):
    class Meta:
        model = models.AnalogGateway
        filterset_class = filters.AnalogGatewayFilterSet


class AnalogPortType(OptimizedNautobotObjectType):
    class Meta:
        model = models.AnalogPort


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
    TrunkType,
    RoutePatternType,
    AnalogGatewayType,
    AnalogPortType,
]
