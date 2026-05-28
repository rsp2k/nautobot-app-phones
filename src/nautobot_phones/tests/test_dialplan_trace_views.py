"""Tests for the dial-plan trace form/view/API — the operator-facing
surface on top of the pure ``dialplan.trace()`` engine.

Three things to verify here that the engine tests don't:

* ``DialPlanTraceForm.clean()`` dispatches by ``mode`` correctly —
  endpoint mode derives phone_system + CSS from the composite key,
  manual mode requires both directly.
* ``DialPlanEndpointSearchView`` returns the right Select2-shaped
  results for Phone / DN / Trunk searches and computes the right
  derived CSS for each.
* ``DialPlanTraceView`` POST round-trips end-to-end through both
  modes and ends up with the same trace output.
"""

from django.urls import reverse
from nautobot.core.testing import TestCase

from nautobot_phones import models
from nautobot_phones.forms import DialPlanTraceForm


class _DialPlanFixtureMixin:
    """Same shape as the engine's mixin, but exposes a phone with a
    line on a DN so endpoint-search returns useful results."""

    def setUp(self):
        super().setUp()
        # nautobot.core.testing.TestCase creates self.user but doesn't
        # auto-login — these views (LoginRequiredMixin) need it.
        self.client.force_login(self.user)
        # The dev env's ALLOWED_HOSTS = "phones-dev.example.com nautobot-web
        # localhost 127.0.0.1" — Django's test client defaults to
        # "testserver" which is REJECTED. Point at localhost to match
        # the rest of this project's view tests (see test_views_did_*).
        self.client.defaults["SERVER_NAME"] = "localhost"
        self.ps = models.PhoneSystem.objects.create(
            name="LAB-CCM", vendor="cisco_ucm",
            version="15.0", hostname="ccm.example.com",
        )
        self.partition = models.Partition.objects.create(
            name="Internal-PT", phone_system=self.ps,
        )
        self.css = models.CallingSearchSpace.objects.create(
            name="Internal-CSS", phone_system=self.ps,
        )
        models.CSSPartitionMembership.objects.create(
            css=self.css, partition=self.partition, priority=1,
        )
        self.dn = models.DirectoryNumber.objects.create(
            extension="1001", partition=self.partition, phone_system=self.ps,
            alerting_name="Alice",
        )
        self.phone = models.Phone.objects.create(
            device_name="SEPAAAA1001",
            mac_address="AA:BB:CC:00:10:01",
            device_kind="SEP", phone_system=self.ps,
            description="Alice's desk",
            vendor_extras={"callingSearchSpaceName": "Internal-CSS"},
        )
        models.Line.objects.create(
            phone=self.phone, directory_number=self.dn, button_index=1,
        )
        self.trunk = models.Trunk.objects.create(
            name="SIP-OUT-PRI", phone_system=self.ps, trunk_type="sip",
            destination_address="198.51.100.10",
            inbound_css=self.css,
        )


# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------


class DialPlanTraceFormDispatchTests(_DialPlanFixtureMixin, TestCase):
    """Form's ``clean()`` discriminates by ``mode``."""

    def test_manual_mode_requires_phone_system_and_css(self):
        f = DialPlanTraceForm(data={
            "mode": "manual",
            "dialed_digits": "1001",
        })
        self.assertFalse(f.is_valid())
        self.assertIn("phone_system", f.errors)
        self.assertIn("starting_css", f.errors)

    def test_manual_mode_happy_path(self):
        f = DialPlanTraceForm(data={
            "mode": "manual",
            "phone_system": str(self.ps.pk),
            "starting_css": str(self.css.pk),
            "dialed_digits": "1001",
        })
        self.assertTrue(f.is_valid(), f.errors)
        # cleaned_data carries model instances (DynamicModelChoiceField).
        self.assertEqual(f.cleaned_data["phone_system"], self.ps)
        self.assertEqual(f.cleaned_data["starting_css"], self.css)

    def test_endpoint_mode_requires_endpoint(self):
        f = DialPlanTraceForm(data={
            "mode": "endpoint",
            "dialed_digits": "1001",
        })
        self.assertFalse(f.is_valid())
        # Endpoint-missing error attaches at the form level.
        self.assertTrue(any("endpoint" in str(e).lower()
                            for e in f.non_field_errors()))

    def test_endpoint_mode_phone_resolves_to_css(self):
        f = DialPlanTraceForm(data={
            "mode": "endpoint",
            "endpoint": f"phone:{self.phone.pk}",
            "dialed_digits": "1001",
        })
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data["phone_system"], self.ps)
        self.assertEqual(f.cleaned_data["starting_css"], self.css)

    def test_endpoint_mode_trunk_resolves_to_inbound_css(self):
        f = DialPlanTraceForm(data={
            "mode": "endpoint",
            "endpoint": f"trunk:{self.trunk.pk}",
            "dialed_digits": "1001",
        })
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data["starting_css"], self.css)

    def test_endpoint_mode_phone_with_unknown_css_name_fails_gracefully(self):
        """Phone whose vendor_extras names a CSS that doesn't exist in
        the synced data should produce a form error, not a 500."""
        orphan = models.Phone.objects.create(
            device_name="SEPORPHAN", mac_address="DE:AD:BE:EF:00:01",
            device_kind="SEP", phone_system=self.ps,
            vendor_extras={"callingSearchSpaceName": "Nonexistent-CSS"},
        )
        f = DialPlanTraceForm(data={
            "mode": "endpoint",
            "endpoint": f"phone:{orphan.pk}",
            "dialed_digits": "1001",
        })
        self.assertFalse(f.is_valid())
        self.assertTrue(any("calling search space" in str(e).lower()
                            for e in f.non_field_errors()))

    def test_endpoint_mode_unparseable_key(self):
        f = DialPlanTraceForm(data={
            "mode": "endpoint",
            "endpoint": "garbage-no-colon",
            "dialed_digits": "1001",
        })
        self.assertFalse(f.is_valid())


# ---------------------------------------------------------------------------
# Search API
# ---------------------------------------------------------------------------


class DialPlanEndpointSearchTests(_DialPlanFixtureMixin, TestCase):
    """The JSON autocomplete returns the right shape per kind."""

    def setUp(self):
        super().setUp()
        self.url = reverse("plugins:nautobot_phones:dialplan_endpoint_search")

    def _search(self, q):
        resp = self.client.get(self.url, {"q": q})
        self.assertEqual(resp.status_code, 200,
                         f"non-200: {resp.status_code} body={resp.content[:300]!r}")
        return resp.json()["results"]

    def test_min_query_length_returns_empty(self):
        """Avoid scanning the whole table on 0-1 char inputs."""
        self.assertEqual(self._search(""), [])
        self.assertEqual(self._search("S"), [])

    def test_phone_by_device_name(self):
        results = self._search("SEPAAAA")
        # Phone hit + DN-extension hit are independent — but SEPAAAA only
        # matches the phone, not "1001".
        phone_hits = [r for r in results if r["kind"] == "phone"]
        self.assertEqual(len(phone_hits), 1)
        hit = phone_hits[0]
        self.assertEqual(hit["id"], f"phone:{self.phone.pk}")
        self.assertEqual(hit["phone_system_id"], str(self.ps.pk))
        self.assertEqual(hit["starting_css_id"], str(self.css.pk))

    def test_phone_by_mac(self):
        results = self._search("AA:BB:CC")
        self.assertTrue(any(r["kind"] == "phone" for r in results))

    def test_phone_by_description(self):
        results = self._search("Alice")
        # 'Alice' matches the DN's alerting_name? No — DN search is by
        # extension only. So this is a phone-only match via description.
        self.assertTrue(any(r["kind"] == "phone" and r["id"] ==
                            f"phone:{self.phone.pk}" for r in results))

    def test_dn_extension_returns_holder_phone(self):
        """Extension '1001' is held by self.phone — DN search emits a
        result pointed at the holder phone, not the DN itself."""
        results = self._search("1001")
        dn_hits = [r for r in results if r["kind"] == "dn_via_phone"]
        self.assertEqual(len(dn_hits), 1)
        hit = dn_hits[0]
        self.assertEqual(hit["id"], f"phone:{self.phone.pk}")
        # Label has the DN-target icon + extension + holder.
        self.assertIn("1001", hit["text"])
        self.assertIn("SEPAAAA1001", hit["text"])

    def test_dn_orphan_marked_disabled(self):
        """A DN with no holder phone is included with disabled=True so
        operators see it but can't try to trace from it."""
        orphan_dn = models.DirectoryNumber.objects.create(
            extension="9999", partition=self.partition, phone_system=self.ps,
        )
        results = self._search("9999")
        orphans = [r for r in results if r["kind"] == "dn_orphan"]
        self.assertEqual(len(orphans), 1)
        self.assertTrue(orphans[0]["disabled"])
        self.assertEqual(orphans[0]["id"], f"dn:{orphan_dn.pk}")

    def test_trunk_by_name(self):
        results = self._search("SIP-OUT")
        trunk_hits = [r for r in results if r["kind"] == "trunk"]
        self.assertEqual(len(trunk_hits), 1)
        self.assertEqual(trunk_hits[0]["id"], f"trunk:{self.trunk.pk}")
        # Trunk's inbound_css is set in fixture, so it's derivable.
        self.assertEqual(trunk_hits[0]["starting_css_id"], str(self.css.pk))


# ---------------------------------------------------------------------------
# View dispatch
# ---------------------------------------------------------------------------


class DialPlanTraceViewDispatchTests(_DialPlanFixtureMixin, TestCase):
    """Endpoint mode and manual mode both produce equivalent trace
    output for the same effective inputs."""

    def setUp(self):
        super().setUp()
        self.url = reverse("plugins:nautobot_phones:dialplan_trace")

    def test_get_renders_empty_form(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "By Endpoint")
        self.assertContains(resp, "Manual")

    def test_post_manual_mode_renders_trace(self):
        resp = self.client.post(self.url, {
            "mode": "manual",
            "phone_system": str(self.ps.pk),
            "starting_css": str(self.css.pk),
            "dialed_digits": "1001",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Trace result")
        self.assertContains(resp, "1001")

    def test_post_endpoint_mode_renders_trace_with_banner(self):
        resp = self.client.post(self.url, {
            "mode": "endpoint",
            "endpoint": f"phone:{self.phone.pk}",
            "endpoint_label": "📞 SEPAAAA1001",
            "dialed_digits": "1001",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Trace result")
        # Endpoint provenance banner renders.
        self.assertContains(resp, "Endpoint:")
        self.assertContains(resp, "SEPAAAA1001")
