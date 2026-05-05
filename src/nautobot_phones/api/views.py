"""DRF viewsets for nautobot-app-phones REST API.

NautobotModelViewSet bundles list/retrieve/create/update/destroy actions
plus filterset support, pagination, and tags/notes/changelog endpoints.
"""

from nautobot.apps.api import NautobotModelViewSet

from nautobot_phones import filters, models
from nautobot_phones.api import serializers


class PhoneSystemAPIViewSet(NautobotModelViewSet):
    queryset = models.PhoneSystem.objects.all()
    serializer_class = serializers.PhoneSystemSerializer
    filterset_class = filters.PhoneSystemFilterSet


class CarrierAPIViewSet(NautobotModelViewSet):
    queryset = models.Carrier.objects.all()
    serializer_class = serializers.CarrierSerializer
    filterset_class = filters.CarrierFilterSet


class PartitionAPIViewSet(NautobotModelViewSet):
    queryset = models.Partition.objects.all()
    serializer_class = serializers.PartitionSerializer
    filterset_class = filters.PartitionFilterSet


class CallingSearchSpaceAPIViewSet(NautobotModelViewSet):
    queryset = models.CallingSearchSpace.objects.all()
    serializer_class = serializers.CallingSearchSpaceSerializer
    filterset_class = filters.CallingSearchSpaceFilterSet


class CSSPartitionMembershipAPIViewSet(NautobotModelViewSet):
    queryset = models.CSSPartitionMembership.objects.all()
    serializer_class = serializers.CSSPartitionMembershipSerializer
    filterset_class = None


class DirectoryNumberAPIViewSet(NautobotModelViewSet):
    queryset = models.DirectoryNumber.objects.all()
    serializer_class = serializers.DirectoryNumberSerializer
    filterset_class = filters.DirectoryNumberFilterSet


class DIDBlockAPIViewSet(NautobotModelViewSet):
    queryset = models.DIDBlock.objects.all()
    serializer_class = serializers.DIDBlockSerializer
    filterset_class = filters.DIDBlockFilterSet


class DIDAPIViewSet(NautobotModelViewSet):
    queryset = models.DID.objects.all()
    serializer_class = serializers.DIDSerializer
    filterset_class = filters.DIDFilterSet


class DIDAssignmentAPIViewSet(NautobotModelViewSet):
    queryset = models.DIDAssignment.objects.all()
    serializer_class = serializers.DIDAssignmentSerializer
    filterset_class = None


class PhoneAPIViewSet(NautobotModelViewSet):
    queryset = models.Phone.objects.all()
    serializer_class = serializers.PhoneSerializer
    filterset_class = filters.PhoneFilterSet


class LineAPIViewSet(NautobotModelViewSet):
    queryset = models.Line.objects.all()
    serializer_class = serializers.LineSerializer
    filterset_class = None


class BusyLampFieldAPIViewSet(NautobotModelViewSet):
    queryset = models.BusyLampField.objects.all()
    serializer_class = serializers.BusyLampFieldSerializer
    filterset_class = None


class TrunkAPIViewSet(NautobotModelViewSet):
    queryset = models.Trunk.objects.all()
    serializer_class = serializers.TrunkSerializer
    filterset_class = filters.TrunkFilterSet


class RouteListAPIViewSet(NautobotModelViewSet):
    queryset = models.RouteList.objects.all()
    serializer_class = serializers.RouteListSerializer
    filterset_class = filters.RouteListFilterSet


class RouteListMemberAPIViewSet(NautobotModelViewSet):
    queryset = models.RouteListMember.objects.all()
    serializer_class = serializers.RouteListMemberSerializer
    filterset_class = None


class RouteGroupAPIViewSet(NautobotModelViewSet):
    queryset = models.RouteGroup.objects.all()
    serializer_class = serializers.RouteGroupSerializer
    filterset_class = filters.RouteGroupFilterSet


class RouteGroupMemberAPIViewSet(NautobotModelViewSet):
    queryset = models.RouteGroupMember.objects.all()
    serializer_class = serializers.RouteGroupMemberSerializer
    filterset_class = None


class RoutePatternAPIViewSet(NautobotModelViewSet):
    queryset = models.RoutePattern.objects.all()
    serializer_class = serializers.RoutePatternSerializer
    filterset_class = filters.RoutePatternFilterSet


class TranslationPatternAPIViewSet(NautobotModelViewSet):
    queryset = models.TranslationPattern.objects.all()
    serializer_class = serializers.TranslationPatternSerializer
    filterset_class = filters.TranslationPatternFilterSet


class AnalogGatewayAPIViewSet(NautobotModelViewSet):
    queryset = models.AnalogGateway.objects.all()
    serializer_class = serializers.AnalogGatewaySerializer
    filterset_class = filters.AnalogGatewayFilterSet


class AnalogPortAPIViewSet(NautobotModelViewSet):
    queryset = models.AnalogPort.objects.all()
    serializer_class = serializers.AnalogPortSerializer
    filterset_class = None
