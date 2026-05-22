"""Smoke tests for the DIDAssignment UI views.

Verifies the operator-facing endpoints (list / detail / add) render
without errors and that the GFK-aware form validates correctly.
DIDAssignment is the only model in this app where the create/edit
form has non-trivial custom logic (two optional FK fields, XOR-
validated, translated to ``target_type`` + ``target_id`` on save) —
so it benefits from a focused test that exercises that logic via the
real form, not just the model.
"""

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from nautobot.core.testing import TestCase

from nautobot_phones import models


class DIDAssignmentViewSmokeTests(TestCase):
    """List / detail / add views return 200; the form's XOR rule fires."""

    # Permissions the framework's setUpNautobot() grants to self.user via
    # add_permissions() BEFORE the request lifecycle. Two things care:
    #
    # 1. ObjectPermission-based restrict() on the LIST queryset — needs
    #    ``view_didassignment``.
    # 2. ``restrict_form_fields()`` in the create/edit view filters each
    #    ModelChoiceField's queryset by the user's view permission on
    #    THAT field's model. Without ``view_directorynumber`` and
    #    ``view_trunk``, the target FK querysets resolve to empty
    #    and the form silently drops the chosen target — making our
    #    XOR check fire spuriously.
    user_permissions = (
        "nautobot_phones.view_didassignment",
        "nautobot_phones.add_didassignment",
        "nautobot_phones.change_didassignment",
        "nautobot_phones.delete_didassignment",
        "nautobot_phones.view_did",
        "nautobot_phones.view_directorynumber",
        "nautobot_phones.view_trunk",
    )

    def setUp(self) -> None:
        """Build the minimal object graph DIDAssignment depends on.

        DIDAssignment needs:
        - DID (e164 unique) — the anchor
        - DirectoryNumber OR Trunk — the target

        Both DN and Trunk need a PhoneSystem, and DN additionally
        needs a Partition (with PhoneSystem FK).
        """
        super().setUp()
        # NautobotTestClient defaults SERVER_NAME to "nautobot.example.com"
        # which isn't in our dev container's ALLOWED_HOSTS (= ['phones-
        # dev.example.com', 'nautobot-web', 'localhost', '127.0.0.1']).
        # Use localhost so the test client requests are accepted.
        self.client.defaults["SERVER_NAME"] = "localhost"

        self.ps = models.PhoneSystem.objects.create(
            name="LAB-FREEPBX", vendor="freepbx", version="17.0", hostname="http://freepbx",
        )
        self.partition = models.Partition.objects.create(
            name="Internal-PT", phone_system=self.ps,
        )
        self.dn = models.DirectoryNumber.objects.create(
            extension="1001", partition=self.partition, phone_system=self.ps,
        )
        self.trunk = models.Trunk.objects.create(
            name="ITSP-1", phone_system=self.ps, trunk_type="sip",
        )
        self.did = models.DID.objects.create(e164="+15551234567")

    def test_list_view_returns_200(self) -> None:
        """The list page renders even when no DIDAssignment rows exist."""
        url = reverse("plugins:nautobot_phones:didassignment_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content[:1500])

    def test_add_form_renders_with_both_target_fields(self) -> None:
        """The add form exposes BOTH target_directorynumber and target_trunk
        as optional FK fields — the custom GFK-handling pattern from
        ``DIDAssignmentForm``."""
        url = reverse("plugins:nautobot_phones:didassignment_add")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "target_directorynumber")
        self.assertContains(response, "target_trunk")

    def test_post_creates_assignment_with_dn_target(self) -> None:
        """A POST with a DirectoryNumber target persists with the right GFK."""
        url = reverse("plugins:nautobot_phones:didassignment_add")
        response = self.client.post(url, data={
            "did": str(self.did.pk),
            "target_directorynumber": str(self.dn.pk),
            "target_trunk": "",
        }, follow=True)
        self.assertEqual(response.status_code, 200, response.content[:500])
        assignment = models.DIDAssignment.objects.get(did=self.did)
        self.assertEqual(assignment.target_type,
                         ContentType.objects.get_for_model(models.DirectoryNumber))
        self.assertEqual(assignment.target_id, self.dn.pk)
        self.assertEqual(assignment.target, self.dn)

    def test_post_creates_assignment_with_trunk_target(self) -> None:
        """A POST with a Trunk target persists with the right GFK."""
        url = reverse("plugins:nautobot_phones:didassignment_add")
        response = self.client.post(url, data={
            "did": str(self.did.pk),
            "target_directorynumber": "",
            "target_trunk": str(self.trunk.pk),
        }, follow=True)
        self.assertEqual(response.status_code, 200, response.content[:500])
        assignment = models.DIDAssignment.objects.get(did=self.did)
        self.assertEqual(assignment.target_type,
                         ContentType.objects.get_for_model(models.Trunk))
        self.assertEqual(assignment.target_id, self.trunk.pk)

    def test_post_with_neither_target_is_rejected(self) -> None:
        """The XOR rule: neither target → form error, no record created."""
        url = reverse("plugins:nautobot_phones:didassignment_add")
        response = self.client.post(url, data={
            "did": str(self.did.pk),
            "target_directorynumber": "",
            "target_trunk": "",
        })
        self.assertEqual(response.status_code, 200)  # Form re-rendered, not redirect.
        self.assertContains(response, "Pick exactly one target")
        self.assertEqual(models.DIDAssignment.objects.count(), 0)

    def test_post_with_both_targets_is_rejected(self) -> None:
        """The XOR rule: both targets → form error, no record created."""
        url = reverse("plugins:nautobot_phones:didassignment_add")
        response = self.client.post(url, data={
            "did": str(self.did.pk),
            "target_directorynumber": str(self.dn.pk),
            "target_trunk": str(self.trunk.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pick only one target")
        self.assertEqual(models.DIDAssignment.objects.count(), 0)

    def test_detail_view_renders_assignment(self) -> None:
        """The detail page resolves and renders an existing assignment."""
        assignment = models.DIDAssignment.objects.create(
            did=self.did,
            target_type=ContentType.objects.get_for_model(models.Trunk),
            target_id=self.trunk.pk,
        )
        url = reverse("plugins:nautobot_phones:didassignment", kwargs={"pk": assignment.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_list_view_shows_target_link(self) -> None:
        """The list view's resolved ``target`` column produces a clickable link
        to the underlying target — proves the GFK-aware render path works.

        Nautobot's list view is HTMX-driven: the initial GET returns an
        empty shell, and the row data loads via a follow-up HTMX request
        to the same URL with ``HX-Request: true``. We send that header
        directly so the renderer passes the full queryset to the table.
        See ``nautobot/core/views/renderers.py`` line 102.
        """
        models.DIDAssignment.objects.create(
            did=self.did,
            target_type=ContentType.objects.get_for_model(models.Trunk),
            target_id=self.trunk.pk,
        )
        url = reverse("plugins:nautobot_phones:didassignment_list")
        response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ITSP-1")
