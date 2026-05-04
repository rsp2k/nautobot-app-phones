"""django-filter FilterSet classes for nautobot-app-phones list views.

Each PrimaryModel gets a FilterSet that defines URL-queryable filter
fields (e.g. ?vendor=cisco_ucm&name__icontains=lab). Backed by Nautobot's
NautobotFilterSet which adds tags, custom-field, and search-token (q)
support automatically.
"""

from nautobot.apps.filters import NautobotFilterSet

from nautobot_phones import models


class PhoneSystemFilterSet(NautobotFilterSet):
    """Filter set for PhoneSystem list view."""

    class Meta:
        """Filterset meta."""

        model = models.PhoneSystem
        fields = ["name", "vendor", "version", "hostname", "location"]
