"""django-filter FilterSet classes for nautobot-app-phones list views.

Each FilterSet declares which model fields are URL-queryable
(e.g. ?vendor=cisco_ucm&name__icontains=lab). Backed by NautobotFilterSet
which auto-adds tags, custom-field, and search-token (q) support.
"""

from nautobot.apps.filters import NautobotFilterSet

from nautobot_phones import models


class PhoneSystemFilterSet(NautobotFilterSet):
    """Filter set for PhoneSystem list view."""

    class Meta:
        model = models.PhoneSystem
        fields = ["name", "vendor", "version", "hostname", "location"]


class CarrierFilterSet(NautobotFilterSet):
    """Filter set for Carrier list view."""

    class Meta:
        model = models.Carrier
        fields = ["name", "account_number"]


class PartitionFilterSet(NautobotFilterSet):
    """Filter set for Partition list view."""

    class Meta:
        model = models.Partition
        fields = ["name", "phone_system"]


class CallingSearchSpaceFilterSet(NautobotFilterSet):
    """Filter set for CallingSearchSpace list view."""

    class Meta:
        model = models.CallingSearchSpace
        fields = ["name", "phone_system"]


class DirectoryNumberFilterSet(NautobotFilterSet):
    """Filter set for DirectoryNumber list view."""

    class Meta:
        model = models.DirectoryNumber
        fields = ["extension", "partition", "phone_system", "alerting_name"]


class DIDBlockFilterSet(NautobotFilterSet):
    """Filter set for DIDBlock list view."""

    class Meta:
        model = models.DIDBlock
        fields = ["start_e164", "end_e164", "carrier", "location", "phone_system"]


class DIDFilterSet(NautobotFilterSet):
    """Filter set for DID list view."""

    class Meta:
        model = models.DID
        fields = ["e164", "block", "is_special"]


class PhoneFilterSet(NautobotFilterSet):
    """Filter set for Phone list view."""

    class Meta:
        model = models.Phone
        fields = ["device_name", "mac_address", "device_kind", "phone_system", "registration_status", "device_pool", "owner_user_id", "ccm_location"]


class TrunkFilterSet(NautobotFilterSet):
    """Filter set for Trunk list view."""

    class Meta:
        model = models.Trunk
        fields = ["name", "phone_system", "trunk_type", "destination_address", "css"]


class RoutePatternFilterSet(NautobotFilterSet):
    """Filter set for RoutePattern list view."""

    class Meta:
        model = models.RoutePattern
        fields = ["pattern", "partition", "css", "target_trunk", "target_route_list", "target_dn", "urgent"]


class RouteListFilterSet(NautobotFilterSet):
    """Filter set for RouteList list view."""

    class Meta:
        model = models.RouteList
        fields = ["name", "phone_system"]


class RouteGroupFilterSet(NautobotFilterSet):
    """Filter set for RouteGroup list view."""

    class Meta:
        model = models.RouteGroup
        fields = ["name", "phone_system", "distribution_algorithm"]


class TranslationPatternFilterSet(NautobotFilterSet):
    """Filter set for TranslationPattern list view."""

    class Meta:
        model = models.TranslationPattern
        fields = ["pattern", "partition", "css", "description"]


class AnalogGatewayFilterSet(NautobotFilterSet):
    """Filter set for AnalogGateway list view."""

    class Meta:
        model = models.AnalogGateway
        fields = ["name", "phone_system", "location", "model", "protocol"]


class HuntPilotFilterSet(NautobotFilterSet):
    """Filter set for HuntPilot list view."""

    class Meta:
        model = models.HuntPilot
        fields = ["pattern", "partition", "hunt_list", "alerting_name"]


class HuntListFilterSet(NautobotFilterSet):
    """Filter set for HuntList list view."""

    class Meta:
        model = models.HuntList
        fields = ["name", "phone_system", "call_manager_group", "route_list_enabled", "voice_mail_usage"]


class LineGroupFilterSet(NautobotFilterSet):
    """Filter set for LineGroup list view."""

    class Meta:
        model = models.LineGroup
        fields = ["name", "phone_system", "distribution_algorithm", "auto_log_off_hunt"]
