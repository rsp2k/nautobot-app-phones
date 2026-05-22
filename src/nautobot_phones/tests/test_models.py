"""Unit tests for nautobot-app-phones models.

Covers the invariants we care about:
- Uniqueness constraints (name per phone-system, MAC per phone-system, etc.)
- DIDBlock validators (E.164 format, equal length, ordering)
- RoutePattern XOR check constraint at the DB level
- DIDAssignment GenericForeignKey resolution
- CSS-Partition through-table priority ordering

Run via: ``nautobot-server test nautobot_phones`` (or the `make test` target).
"""

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from nautobot_phones import factories, models


class TestPhoneSystem(TestCase):
    """PhoneSystem create + uniqueness."""

    def test_create(self) -> None:
        ps = factories.PhoneSystemFactory()
        self.assertIsNotNone(ps.pk)
        self.assertTrue(ps.name.startswith("System-"))
        self.assertEqual(ps.vendor, "cisco_ucm")

    def test_str(self) -> None:
        ps = factories.PhoneSystemFactory(name="test-cluster-1")
        self.assertEqual(str(ps), "test-cluster-1")

    def test_name_must_be_unique(self) -> None:
        factories.PhoneSystemFactory(name="dupe")
        with self.assertRaises(IntegrityError):
            factories.PhoneSystemFactory(name="dupe")


class TestPartition(TestCase):
    """Partition uniqueness is per-PhoneSystem, not global."""

    def test_str_includes_phone_system(self) -> None:
        ps = factories.PhoneSystemFactory(name="X")
        p = factories.PartitionFactory(name="Internal", phone_system=ps)
        self.assertEqual(str(p), "X/Internal")

    def test_same_name_in_different_systems_ok(self) -> None:
        ps1 = factories.PhoneSystemFactory()
        ps2 = factories.PhoneSystemFactory()
        factories.PartitionFactory(name="Internal", phone_system=ps1)
        # No exception — partition name is unique per phone_system, not globally.
        factories.PartitionFactory(name="Internal", phone_system=ps2)

    def test_same_name_in_same_system_rejected(self) -> None:
        ps = factories.PhoneSystemFactory()
        factories.PartitionFactory(name="Internal", phone_system=ps)
        with self.assertRaises(IntegrityError):
            factories.PartitionFactory(name="Internal", phone_system=ps)


class TestCallingSearchSpaceMembership(TestCase):
    """CSS-Partition through-table preserves priority order."""

    def test_priority_ordering(self) -> None:
        ps = factories.PhoneSystemFactory()
        css = factories.CallingSearchSpaceFactory(phone_system=ps)
        p10 = factories.PartitionFactory(phone_system=ps, name="High")
        p20 = factories.PartitionFactory(phone_system=ps, name="Low")
        models.CSSPartitionMembership.objects.create(css=css, partition=p20, priority=20)
        models.CSSPartitionMembership.objects.create(css=css, partition=p10, priority=10)

        ordered = list(css.memberships.order_by("priority"))
        self.assertEqual([m.partition.name for m in ordered], ["High", "Low"])

    def test_duplicate_priority_per_css_rejected(self) -> None:
        ps = factories.PhoneSystemFactory()
        css = factories.CallingSearchSpaceFactory(phone_system=ps)
        p1 = factories.PartitionFactory(phone_system=ps)
        p2 = factories.PartitionFactory(phone_system=ps)
        models.CSSPartitionMembership.objects.create(css=css, partition=p1, priority=10)
        with self.assertRaises(IntegrityError):
            models.CSSPartitionMembership.objects.create(css=css, partition=p2, priority=10)


class TestDIDBlockValidator(TestCase):
    """DIDBlock.clean() enforces E.164 format and ordering."""

    def setUp(self) -> None:
        self.provider = factories.CircuitsProviderFactory()

    def test_unequal_length_rejected(self) -> None:
        blk = models.DIDBlock(
            start_e164="15551234000",
            end_e164="155512349999",  # one extra digit
            provider=self.provider,
        )
        with self.assertRaises(ValidationError):
            blk.full_clean()

    def test_non_digit_chars_rejected(self) -> None:
        blk = models.DIDBlock(
            start_e164="+15551234000",  # leading plus is not a digit
            end_e164="+15551234999",
            provider=self.provider,
        )
        with self.assertRaises(ValidationError):
            blk.full_clean()

    def test_start_after_end_rejected(self) -> None:
        blk = models.DIDBlock(
            start_e164="15551234999",
            end_e164="15551234000",  # backwards
            provider=self.provider,
        )
        with self.assertRaises(ValidationError):
            blk.full_clean()

    def test_size_property(self) -> None:
        blk = factories.DIDBlockFactory()
        self.assertEqual(blk.size, 1000)


class TestDID(TestCase):
    """DID e164 is globally unique."""

    def test_unique_e164(self) -> None:
        factories.DIDFactory(e164="15551234567")
        with self.assertRaises(IntegrityError):
            factories.DIDFactory(e164="15551234567")


class TestDIDAssignment(TestCase):
    """GenericForeignKey resolves to either DirectoryNumber or Trunk."""

    def test_assignment_to_directory_number(self) -> None:
        ps = factories.PhoneSystemFactory()
        part = factories.PartitionFactory(phone_system=ps)
        dn = factories.DirectoryNumberFactory(partition=part)
        did = factories.DIDFactory()
        models.DIDAssignment.objects.create(did=did, target=dn)

        self.assertEqual(did.assignment.target, dn)
        self.assertEqual(did.assignment.target_type, ContentType.objects.get_for_model(dn))

    def test_assignment_to_trunk(self) -> None:
        ps = factories.PhoneSystemFactory()
        trunk = factories.TrunkFactory(phone_system=ps)
        did = factories.DIDFactory()
        models.DIDAssignment.objects.create(did=did, target=trunk)

        self.assertEqual(did.assignment.target, trunk)


class TestPhone(TestCase):
    """Phones are unique by (phone_system, device_name).

    Pre-softphone: uniqueness was (phone_system, mac_address). Softphones
    have no MAC, so we switched to device_name as the canonical CCM
    identifier shared across SEP/CSF/TCT/BOT/CSK/ATA prefixes.
    """

    def test_create(self) -> None:
        phone = factories.PhoneFactory()
        self.assertIsNotNone(phone.pk)

    def test_same_device_name_in_different_systems_ok(self) -> None:
        ps1 = factories.PhoneSystemFactory()
        ps2 = factories.PhoneSystemFactory()
        factories.PhoneFactory(device_name="SEPCAFEBABE0001", phone_system=ps1)
        # Same device_name OK across clusters (rare in practice but allowed).
        factories.PhoneFactory(device_name="SEPCAFEBABE0001", phone_system=ps2)

    def test_same_device_name_in_same_system_rejected(self) -> None:
        ps = factories.PhoneSystemFactory()
        factories.PhoneFactory(device_name="SEPCAFEBABE0001", phone_system=ps)
        with self.assertRaises(IntegrityError):
            factories.PhoneFactory(device_name="SEPCAFEBABE0001", phone_system=ps)

    def test_softphone_with_no_mac_allowed(self) -> None:
        """CSF/TCT/BOT softphones have no MAC. The optional field allows None."""
        ps = factories.PhoneSystemFactory()
        phone = factories.PhoneFactory(
            device_name="CSFJDOE", mac_address=None, device_kind="csf",
            phone_system=ps,
        )
        self.assertIsNone(phone.mac_address)
        self.assertEqual(phone.device_kind, "csf")

    def test_model_property_reads_from_device(self) -> None:
        """Phone.model is a property — when no Device is linked, falls
        back to vendor_extras['axl_model']."""
        phone = factories.PhoneFactory(vendor_extras={"axl_model": "CP-8851"})
        # No Device linked → property reads from vendor_extras
        self.assertEqual(phone.model, "CP-8851")

    def test_location_property_with_no_device(self) -> None:
        """Phone.location is a property that reads through linked Device.
        When no Device, returns None."""
        phone = factories.PhoneFactory()
        self.assertIsNone(phone.location)


class TestLine(TestCase):
    """Each phone button index is unique within a phone."""

    def test_unique_button_index_per_phone(self) -> None:
        phone = factories.PhoneFactory()
        dn1 = factories.DirectoryNumberFactory()
        dn2 = factories.DirectoryNumberFactory()
        factories.LineFactory(phone=phone, directory_number=dn1, button_index=1)
        with self.assertRaises(IntegrityError):
            factories.LineFactory(phone=phone, directory_number=dn2, button_index=1)


class TestAnalogPort(TestCase):
    """AnalogPort port_index is unique within a gateway."""

    def test_unique_port_index_per_gateway(self) -> None:
        gw = factories.AnalogGatewayFactory()
        factories.AnalogPortFactory(gateway=gw, port_index=1)
        with self.assertRaises(IntegrityError):
            factories.AnalogPortFactory(gateway=gw, port_index=1)


class TestRoutePatternXOR(TestCase):
    """The DB CHECK constraint enforces exactly one target on RoutePattern."""

    def setUp(self) -> None:
        self.ps = factories.PhoneSystemFactory()
        self.part = factories.PartitionFactory(phone_system=self.ps)
        self.trunk = factories.TrunkFactory(phone_system=self.ps)
        self.dn = factories.DirectoryNumberFactory(partition=self.part)

    def test_only_target_trunk_ok(self) -> None:
        rp = models.RoutePattern.objects.create(
            pattern="9.X", partition=self.part, target_trunk=self.trunk,
        )
        self.assertIsNotNone(rp.pk)

    def test_only_target_dn_ok(self) -> None:
        rp = models.RoutePattern.objects.create(
            pattern="2X", partition=self.part, target_dn=self.dn,
        )
        self.assertIsNotNone(rp.pk)

    def test_neither_target_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            models.RoutePattern.objects.create(pattern="3X", partition=self.part)

    def test_both_targets_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            models.RoutePattern.objects.create(
                pattern="4X",
                partition=self.part,
                target_trunk=self.trunk,
                target_dn=self.dn,
            )


class TestSipCircuitProfile(TestCase):
    """SipCircuitProfile is a OneToOne extension of circuits.Circuit."""

    def test_create_minimal(self) -> None:
        profile = factories.SipCircuitProfileFactory()
        self.assertIsNotNone(profile.pk)
        self.assertEqual(profile.sip_sessions, 23)
        # OneToOne ↔ Circuit
        self.assertEqual(profile.circuit.sip_profile, profile)

    def test_only_one_profile_per_circuit(self) -> None:
        circuit = factories.CircuitsCircuitFactory()
        factories.SipCircuitProfileFactory(circuit=circuit)
        with self.assertRaises(IntegrityError):
            factories.SipCircuitProfileFactory(circuit=circuit)

    def test_sparklight_bingham_shape(self) -> None:
        """The actual SparkLight Bingham cut-sheet values land cleanly."""
        profile = factories.SipCircuitProfileFactory(
            sip_sessions=36,
            pilot_e164="2082396520",
            oli_clid_policy="Public, set to Pilot",
            tech_support="1-877-469-2251 option 2",
            source_doc="SIP Cut Sheet Bingham 1.xlsx",
            sensitivity="internal",
        )
        self.assertEqual(profile.sip_sessions, 36)
        self.assertEqual(profile.pilot_e164, "2082396520")
        self.assertIn("877-469-2251", profile.tech_support)


class TestTrunk(TestCase):
    """Trunk name is unique per phone_system."""

    def test_create(self) -> None:
        t = factories.TrunkFactory()
        self.assertIsNotNone(t.pk)

    def test_same_name_different_systems_ok(self) -> None:
        ps1 = factories.PhoneSystemFactory()
        ps2 = factories.PhoneSystemFactory()
        factories.TrunkFactory(name="SBC1", phone_system=ps1)
        factories.TrunkFactory(name="SBC1", phone_system=ps2)
