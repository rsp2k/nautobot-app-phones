"""Dial-plan structure: Partition, CallingSearchSpace, and the membership through-table.

Cisco CCM concepts; FreePBX maps `Partition` to dialplan context and
`CallingSearchSpace` to outbound-route group.
"""

from django.db import models
from nautobot.apps.models import BaseModel, OrganizationalModel


class Partition(OrganizationalModel):
    """A dial-plan partition.

    In CCM, a partition is a label that scopes which DNs/route patterns are
    reachable from a given CallingSearchSpace. In FreePBX, it maps to a
    dialplan context (e.g. `from-internal`, custom contexts).
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="partitions",
        help_text="Owning phone system (CCM cluster or FreePBX server).",
    )
    description = models.TextField(blank=True)

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for Partition."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone_system.name}/{self.name}"


class CallingSearchSpace(OrganizationalModel):
    """A Calling Search Space (CCM) or outbound-route group (FreePBX).

    An ordered collection of Partitions. When a call is placed, the call
    agent walks the CSS in order, evaluating reachable route patterns from
    each partition. Order matters for first-match semantics.
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="calling_search_spaces",
    )
    description = models.TextField(blank=True)
    partitions = models.ManyToManyField(
        to="nautobot_phones.Partition",
        through="nautobot_phones.CSSPartitionMembership",
        related_name="calling_search_spaces",
        blank=True,
    )

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for CallingSearchSpace."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)
        verbose_name = "calling search space"
        verbose_name_plural = "calling search spaces"

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone_system.name}/{self.name}"


class CSSPartitionMembership(BaseModel):
    """Through-table preserving partition order within a CallingSearchSpace.

    Order matters semantically — CCM evaluates partitions in CSS order and
    short-circuits on the first match. Default M2M is set-based; this
    through-table carries the priority field.
    """

    css = models.ForeignKey(
        to="nautobot_phones.CallingSearchSpace",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    partition = models.ForeignKey(
        to="nautobot_phones.Partition",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    priority = models.PositiveIntegerField(
        help_text="Lower number = evaluated first.",
    )

    class Meta:
        """Meta options for CSSPartitionMembership."""

        ordering = ("css", "priority")
        unique_together = (
            ("css", "partition"),
            ("css", "priority"),
        )
        verbose_name = "CSS partition membership"
        verbose_name_plural = "CSS partition memberships"

    def __str__(self) -> str:
        """Display string."""
        return f"{self.css.name}[{self.priority}] -> {self.partition.name}"
