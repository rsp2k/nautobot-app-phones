"""ViewSets for nautobot-app-phones.

Each PrimaryModel/OrganizationalModel gets a NautobotUIViewSet that bundles
list, detail, create, edit, delete, and bulk-action views together. Each
viewset wires in its model's table, filterset, and form classes.

Junction-style records (Line, AnalogPort, CSSPartitionMembership,
DIDAssignment) don't have viewsets — they render nested in their parent's
detail view (Phase 2c).
"""

from nautobot.apps.views import NautobotUIViewSet

from nautobot_phones import filters, forms, models, tables


class PhoneSystemUIViewSet(NautobotUIViewSet):
    """CRUD viewset for PhoneSystem."""

    queryset = models.PhoneSystem.objects.all()
    table_class = tables.PhoneSystemTable
    filterset_class = filters.PhoneSystemFilterSet
    filterset_form_class = forms.PhoneSystemFilterForm
    form_class = forms.PhoneSystemForm
    serializer_class = None
    lookup_field = "pk"


class CarrierUIViewSet(NautobotUIViewSet):
    """CRUD viewset for Carrier."""

    queryset = models.Carrier.objects.all()
    table_class = tables.CarrierTable
    filterset_class = filters.CarrierFilterSet
    filterset_form_class = forms.CarrierFilterForm
    form_class = forms.CarrierForm
    serializer_class = None
    lookup_field = "pk"


class PartitionUIViewSet(NautobotUIViewSet):
    """CRUD viewset for Partition."""

    queryset = models.Partition.objects.all()
    table_class = tables.PartitionTable
    filterset_class = filters.PartitionFilterSet
    filterset_form_class = forms.PartitionFilterForm
    form_class = forms.PartitionForm
    serializer_class = None
    lookup_field = "pk"


class CallingSearchSpaceUIViewSet(NautobotUIViewSet):
    """CRUD viewset for CallingSearchSpace."""

    queryset = models.CallingSearchSpace.objects.all()
    table_class = tables.CallingSearchSpaceTable
    filterset_class = filters.CallingSearchSpaceFilterSet
    filterset_form_class = forms.CallingSearchSpaceFilterForm
    form_class = forms.CallingSearchSpaceForm
    serializer_class = None
    lookup_field = "pk"


class DirectoryNumberUIViewSet(NautobotUIViewSet):
    """CRUD viewset for DirectoryNumber."""

    queryset = models.DirectoryNumber.objects.all()
    table_class = tables.DirectoryNumberTable
    filterset_class = filters.DirectoryNumberFilterSet
    filterset_form_class = forms.DirectoryNumberFilterForm
    form_class = forms.DirectoryNumberForm
    serializer_class = None
    lookup_field = "pk"


class DIDBlockUIViewSet(NautobotUIViewSet):
    """CRUD viewset for DIDBlock."""

    queryset = models.DIDBlock.objects.all()
    table_class = tables.DIDBlockTable
    filterset_class = filters.DIDBlockFilterSet
    filterset_form_class = forms.DIDBlockFilterForm
    form_class = forms.DIDBlockForm
    serializer_class = None
    lookup_field = "pk"


class DIDUIViewSet(NautobotUIViewSet):
    """CRUD viewset for DID."""

    queryset = models.DID.objects.all()
    table_class = tables.DIDTable
    filterset_class = filters.DIDFilterSet
    filterset_form_class = forms.DIDFilterForm
    form_class = forms.DIDForm
    serializer_class = None
    lookup_field = "pk"


class PhoneUIViewSet(NautobotUIViewSet):
    """CRUD viewset for Phone."""

    queryset = models.Phone.objects.all()
    table_class = tables.PhoneTable
    filterset_class = filters.PhoneFilterSet
    filterset_form_class = forms.PhoneFilterForm
    form_class = forms.PhoneForm
    serializer_class = None
    lookup_field = "pk"


class TrunkUIViewSet(NautobotUIViewSet):
    """CRUD viewset for Trunk."""

    queryset = models.Trunk.objects.all()
    table_class = tables.TrunkTable
    filterset_class = filters.TrunkFilterSet
    filterset_form_class = forms.TrunkFilterForm
    form_class = forms.TrunkForm
    serializer_class = None
    lookup_field = "pk"


class RoutePatternUIViewSet(NautobotUIViewSet):
    """CRUD viewset for RoutePattern."""

    queryset = models.RoutePattern.objects.all()
    table_class = tables.RoutePatternTable
    filterset_class = filters.RoutePatternFilterSet
    filterset_form_class = forms.RoutePatternFilterForm
    form_class = forms.RoutePatternForm
    serializer_class = None
    lookup_field = "pk"


class AnalogGatewayUIViewSet(NautobotUIViewSet):
    """CRUD viewset for AnalogGateway."""

    queryset = models.AnalogGateway.objects.all()
    table_class = tables.AnalogGatewayTable
    filterset_class = filters.AnalogGatewayFilterSet
    filterset_form_class = forms.AnalogGatewayFilterForm
    form_class = forms.AnalogGatewayForm
    serializer_class = None
    lookup_field = "pk"
