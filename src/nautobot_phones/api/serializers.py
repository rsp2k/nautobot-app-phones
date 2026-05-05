"""DRF serializers for nautobot-app-phones REST API.

One NautobotModelSerializer per PrimaryModel/OrganizationalModel; junction
models (Line, AnalogPort, CSSPartitionMembership, DIDAssignment) get
serializers too so they can be returned nested in their parent's payload.

Convention: `fields = "__all__"` exposes every column. Override per-model
if certain fields should be hidden from the API.
"""

from nautobot.apps.api import NautobotModelSerializer

from nautobot_phones import models


class PhoneSystemSerializer(NautobotModelSerializer):
    class Meta:
        model = models.PhoneSystem
        fields = "__all__"


class CarrierSerializer(NautobotModelSerializer):
    class Meta:
        model = models.Carrier
        fields = "__all__"


class PartitionSerializer(NautobotModelSerializer):
    class Meta:
        model = models.Partition
        fields = "__all__"


class CallingSearchSpaceSerializer(NautobotModelSerializer):
    class Meta:
        model = models.CallingSearchSpace
        fields = "__all__"


class CSSPartitionMembershipSerializer(NautobotModelSerializer):
    class Meta:
        model = models.CSSPartitionMembership
        fields = "__all__"


class DirectoryNumberSerializer(NautobotModelSerializer):
    class Meta:
        model = models.DirectoryNumber
        fields = "__all__"


class DIDBlockSerializer(NautobotModelSerializer):
    class Meta:
        model = models.DIDBlock
        fields = "__all__"


class DIDSerializer(NautobotModelSerializer):
    class Meta:
        model = models.DID
        fields = "__all__"


class DIDAssignmentSerializer(NautobotModelSerializer):
    class Meta:
        model = models.DIDAssignment
        fields = "__all__"


class PhoneSerializer(NautobotModelSerializer):
    class Meta:
        model = models.Phone
        fields = "__all__"


class LineSerializer(NautobotModelSerializer):
    class Meta:
        model = models.Line
        fields = "__all__"


class TrunkSerializer(NautobotModelSerializer):
    class Meta:
        model = models.Trunk
        fields = "__all__"


class RouteListSerializer(NautobotModelSerializer):
    class Meta:
        model = models.RouteList
        fields = "__all__"


class RouteListMemberSerializer(NautobotModelSerializer):
    class Meta:
        model = models.RouteListMember
        fields = "__all__"


class RouteGroupSerializer(NautobotModelSerializer):
    class Meta:
        model = models.RouteGroup
        fields = "__all__"


class RouteGroupMemberSerializer(NautobotModelSerializer):
    class Meta:
        model = models.RouteGroupMember
        fields = "__all__"


class RoutePatternSerializer(NautobotModelSerializer):
    class Meta:
        model = models.RoutePattern
        fields = "__all__"


class AnalogGatewaySerializer(NautobotModelSerializer):
    class Meta:
        model = models.AnalogGateway
        fields = "__all__"


class AnalogPortSerializer(NautobotModelSerializer):
    class Meta:
        model = models.AnalogPort
        fields = "__all__"
