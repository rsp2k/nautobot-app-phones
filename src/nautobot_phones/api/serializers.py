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


class SipCircuitProfileSerializer(NautobotModelSerializer):
    class Meta:
        model = models.SipCircuitProfile
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
        fields = "__all__"  # picks up last_registered_ip automatically


class LineSerializer(NautobotModelSerializer):
    class Meta:
        model = models.Line
        fields = "__all__"


class BusyLampFieldSerializer(NautobotModelSerializer):
    class Meta:
        model = models.BusyLampField
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


class TranslationPatternSerializer(NautobotModelSerializer):
    class Meta:
        model = models.TranslationPattern
        fields = "__all__"


class AnalogGatewaySerializer(NautobotModelSerializer):
    class Meta:
        model = models.AnalogGateway
        fields = "__all__"


class AnalogPortSerializer(NautobotModelSerializer):
    class Meta:
        model = models.AnalogPort
        fields = "__all__"


class HuntPilotSerializer(NautobotModelSerializer):
    class Meta:
        model = models.HuntPilot
        fields = "__all__"


class HuntListSerializer(NautobotModelSerializer):
    class Meta:
        model = models.HuntList
        fields = "__all__"


class HuntListMemberSerializer(NautobotModelSerializer):
    class Meta:
        model = models.HuntListMember
        fields = "__all__"


class LineGroupSerializer(NautobotModelSerializer):
    class Meta:
        model = models.LineGroup
        fields = "__all__"


class LineGroupMemberSerializer(NautobotModelSerializer):
    class Meta:
        model = models.LineGroupMember
        fields = "__all__"


class DeviceProfileSerializer(NautobotModelSerializer):
    class Meta:
        model = models.DeviceProfile
        fields = "__all__"


class VoicemailProfileSerializer(NautobotModelSerializer):
    class Meta:
        model = models.VoicemailProfile
        fields = "__all__"


class CallPickupGroupSerializer(NautobotModelSerializer):
    class Meta:
        model = models.CallPickupGroup
        fields = "__all__"


class CallPickupGroupMemberSerializer(NautobotModelSerializer):
    class Meta:
        model = models.CallPickupGroupMember
        fields = "__all__"
