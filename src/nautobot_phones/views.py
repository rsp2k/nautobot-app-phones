"""ViewSets for nautobot-app-phones.

Each PrimaryModel gets a NautobotUIViewSet that bundles list, detail,
create, edit, delete, and bulk-action views together. Wires in the
table, filterset, and form classes from the sibling modules.
"""

from nautobot.apps.views import NautobotUIViewSet

from nautobot_phones import filters, forms, models, tables


class PhoneSystemUIViewSet(NautobotUIViewSet):
    """Full CRUD viewset for PhoneSystem."""

    queryset = models.PhoneSystem.objects.all()
    table_class = tables.PhoneSystemTable
    filterset_class = filters.PhoneSystemFilterSet
    filterset_form_class = forms.PhoneSystemFilterForm
    form_class = forms.PhoneSystemForm
    serializer_class = None  # API serializer lands in Phase 3
    lookup_field = "pk"
