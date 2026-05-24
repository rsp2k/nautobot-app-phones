"""Tests for the DCIM materialization layer (``devices.py``).

Two halves:

* **Pure helpers** — ``has_pc_port``, ``_decode_voice_port_name``,
  ``_voice_port_metadata``, ``_extract_chassis_mac_base``. No DB needed;
  ``SimpleTestCase``.

* **Enrichment flows** — ``enrich_phone_devices``,
  ``enrich_analog_gateway_devices``, ``enrich_analog_gateway_interfaces``.
  Touch the ORM (create Device/Interface/IPAddress records); ``TestCase``
  with transaction rollback.

Together these cover the post-sync DCIM step that turns Phone +
AnalogGateway records into queryable Nautobot DCIM Devices with proper
interface topology — the layer that makes cabling and patch-panel
relationships work through Nautobot core models.
"""

from typing import Any
from unittest.mock import MagicMock

from django.test import SimpleTestCase, TestCase

from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType
from nautobot.extras.models import Status

from nautobot_phones import models as ph_models
from nautobot_phones.integrations.cisco_ucm.devices import (
    _decode_voice_port_name,
    _extract_chassis_mac_base,
    _voice_port_metadata,
    enrich_analog_gateway_devices,
    enrich_analog_gateway_interfaces,
    enrich_phone_devices,
    has_pc_port,
)


# ---------------------------------------------------------------------------
# Pure helpers — no DB needed
# ---------------------------------------------------------------------------


class TestHasPcPort(SimpleTestCase):
    """``has_pc_port`` discriminates which models have a PC pass-through port."""

    def test_modern_ip_phone_has_pc_port(self) -> None:
        """Default: anything NOT in the single-port set has PC + voice VLAN."""
        self.assertTrue(has_pc_port("Cisco 8845"))
        self.assertTrue(has_pc_port("Cisco 7841"))
        self.assertTrue(has_pc_port("Cisco DX80"))

    def test_ata_has_no_pc_port(self) -> None:
        """ATAs are analog-to-IP bridges — no upstream switch port topology."""
        for ata in ("ATA-186", "ATA-187", "ATA-188",
                    "Cisco ATA 191", "Cisco ATA 192"):
            self.assertFalse(has_pc_port(ata), f"{ata} should NOT have PC port")

    def test_wireless_phone_has_no_pc_port(self) -> None:
        """7925/8821 are wireless — no wired PC pass-through."""
        for wireless in ("Cisco 7925", "Cisco 7925G", "Cisco 8821", "Cisco 8821-EX"):
            self.assertFalse(has_pc_port(wireless))

    def test_conference_phone_has_no_pc_port(self) -> None:
        """7937/8831/8832 are conference phones — only a network port."""
        for conf in ("Cisco 7937", "Cisco 8831", "Cisco 8832"):
            self.assertFalse(has_pc_port(conf))

    def test_unknown_model_defaults_to_true(self) -> None:
        """Empty / unknown model defaults to has-pc-port — most modern
        Cisco IP phones do, so this is the safer default."""
        self.assertTrue(has_pc_port(""))
        self.assertTrue(has_pc_port("Brand New Phone X9000"))


class TestDecodeVoicePortName(SimpleTestCase):
    """``_decode_voice_port_name`` reverses CCM's bit-packed port index.

    Documented mapping (verified against multiple VG450 chassis):
        bits 9-11 → slot, bit 8 → sub-slot, bits 0-7 → port (1-based)
    """

    def test_documented_examples(self) -> None:
        """Three examples from the module docstring — audit-verified
        against real chassis configs."""
        self.assertEqual(_decode_voice_port_name(0x20A), "voice-port 1/0/9")
        self.assertEqual(_decode_voice_port_name(0x638), "voice-port 3/0/55")
        self.assertEqual(_decode_voice_port_name(0x201), "voice-port 1/0/0")

    def test_slot_0_sub_slot_0_port_0(self) -> None:
        """Lowest valid encoded port: slot=0, sub_slot=0, port-1=1 → port=0."""
        # 0x001 = port_1based=1 → port=0
        self.assertEqual(_decode_voice_port_name(0x001), "voice-port 0/0/0")

    def test_sub_slot_bit_8(self) -> None:
        """Bit 8 is the sub-slot — toggles between subslot 0 and 1."""
        # 0x101 = sub_slot=1, port_1based=1 → port=0, slot=0
        self.assertEqual(_decode_voice_port_name(0x101), "voice-port 0/1/0")

    def test_slot_max_value(self) -> None:
        """Bits 9-11 hold slot — max value is 0b111 = 7."""
        # 0xE01 = slot=7, sub_slot=0, port=0
        self.assertEqual(_decode_voice_port_name(0xE01), "voice-port 7/0/0")

    def test_port_zero_falls_back_to_raw_hex(self) -> None:
        """port_1based=0 (which would yield port=-1) is treated as the
        encoding-boundary case and emits a stable raw-hex name."""
        self.assertEqual(_decode_voice_port_name(0x200), "FXS-0x200")
        self.assertEqual(_decode_voice_port_name(0x000), "FXS-0x0")


class TestVoicePortMetadata(SimpleTestCase):
    """``_voice_port_metadata`` extracts (function, connector) from product strings."""

    def test_fxs_only(self) -> None:
        fn, conn = _voice_port_metadata("SM-X-72FXS-SCCP")
        self.assertEqual(fn, "fxs")
        self.assertEqual(conn, "rj-21")

    def test_fxo_only(self) -> None:
        """FXO-only module: function is fxo."""
        fn, _ = _voice_port_metadata("SM-X-24FXO")
        self.assertEqual(fn, "fxo")

    def test_mixed_fxs_fxo_defaults_to_fxs(self) -> None:
        """A mixed-port module defaults to fxs (most common) — per-port
        override is the operator's responsibility."""
        fn, _ = _voice_port_metadata("Custom FXS/FXO Combo Card")
        self.assertEqual(fn, "fxs")

    def test_unknown_defaults_to_fxs_rj21(self) -> None:
        """Empty / unrecognized product strings get the most-common
        defaults so the Interface still gets a usable label."""
        self.assertEqual(_voice_port_metadata(""), ("fxs", "rj-21"))
        self.assertEqual(_voice_port_metadata(None), ("fxs", "rj-21"))

    def test_high_density_module_implies_rj21(self) -> None:
        """24/48/72-port density implies 50-pin Amphenol (RJ-21)."""
        for prod in ("SM-X-48FXS", "SM-X-72FXS-SCCP", "SM-X-24FXO"):
            _, conn = _voice_port_metadata(prod)
            self.assertEqual(conn, "rj-21", f"{prod} should imply rj-21")

    def test_nim_module_implies_rj11(self) -> None:
        """NIM-series cards have individual RJ-11 jacks."""
        _, conn = _voice_port_metadata("NIM-2FXS")
        self.assertEqual(conn, "rj-11")


class TestExtractChassisMacBase(SimpleTestCase):
    """``_extract_chassis_mac_base`` parses the CCM gateway-name MAC convention."""

    def test_standard_convention(self) -> None:
        """``<SITE>GW<8-hex><01>`` → returns the 8-hex MAC base."""
        self.assertEqual(_extract_chassis_mac_base("HQGW4ABC0DEF01"), "4ABC0DEF")
        self.assertEqual(_extract_chassis_mac_base("DCGWCAFEBABE01"), "CAFEBABE")

    def test_uppercase_normalized(self) -> None:
        """Mixed-case CCM names normalize to uppercase MAC base."""
        self.assertEqual(_extract_chassis_mac_base("hqgw4abc0def01"), "4ABC0DEF")

    def test_no_01_suffix_returns_empty(self) -> None:
        """Names not ending in '01' don't match — different convention."""
        self.assertEqual(_extract_chassis_mac_base("HQGW4ABC0DEF02"), "")
        self.assertEqual(_extract_chassis_mac_base("HQGW4ABC0DEFXX"), "")

    def test_non_hex_chars_return_empty(self) -> None:
        """Suffix isn't valid hex → not a MAC base."""
        self.assertEqual(_extract_chassis_mac_base("HQGWZZZZZZZZ01"), "")

    def test_too_short_returns_empty(self) -> None:
        """Names with < 10 chars can't carry the encoding."""
        self.assertEqual(_extract_chassis_mac_base("HQGW01"), "")
        self.assertEqual(_extract_chassis_mac_base(""), "")


# ---------------------------------------------------------------------------
# Enrichment flows — DB-touching
# ---------------------------------------------------------------------------


def _make_logger() -> Any:
    """A logger stand-in that records ``.info`` calls for assertion."""
    log = MagicMock()
    log.info = MagicMock()
    return log


class EnrichBaseMixin:
    """Shared setUp for tests that need Phones / AnalogGateways."""

    def _make_location(self) -> Location:
        """Find or create a usable Location for Device records.

        Uses the first existing root LocationType allowed for Device
        content — every Nautobot install seeds at least one ("Site"
        or "Region") that satisfies the constraint.
        """
        from django.contrib.contenttypes.models import ContentType
        device_ct = ContentType.objects.get_for_model(Device)
        loc_type = LocationType.objects.filter(content_types=device_ct).first()
        if loc_type is None:
            # Defensive fallback: seed one ourselves.
            loc_type = LocationType.objects.create(name="Test Site", nestable=True)
            loc_type.content_types.add(device_ct)
        active = Status.objects.get_for_model(Location).get(name="Active")
        return Location.objects.create(
            name="enrich-test-loc", location_type=loc_type, status=active,
        )

    def _make_phone_system(self, location: Location | None = None) -> ph_models.PhoneSystem:
        return ph_models.PhoneSystem.objects.create(
            name="LAB-CCM", vendor="cisco_ucm", version="15.0",
            hostname="ccm.example.com", location=location,
        )


class TestEnrichPhoneDevices(EnrichBaseMixin, TestCase):
    """``enrich_phone_devices`` materializes DCIM Device + Interfaces per Phone."""

    def test_creates_device_and_interfaces_for_sep_phone(self) -> None:
        """Happy path: SEP phone → Device + Network/PC/Voice interfaces.

        Asserts the three-interface topology: Network (cabled to switch),
        PC (cabled to user PC), Voice (virtual, parented to Network).
        """
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        ph_models.Phone.objects.create(
            phone_system=ps, device_name="SEPCAFEBABE0001",
            device_kind="sep",
            mac_address="ca:fe:ba:be:00:01",
            vendor_extras={"axl_model": "Cisco 8845"},
        )

        result = enrich_phone_devices(logger=_make_logger())

        self.assertEqual(result["created"], 1)
        device = Device.objects.get(name="SEPCAFEBABE0001")
        self.assertEqual(device.location, loc)
        # Three interfaces: Network, PC, Voice (since 8845 has PC port).
        iface_names = sorted(i.name for i in device.interfaces.all())
        self.assertEqual(iface_names, ["Network", "PC", "Voice"])
        # Voice is virtual + parented to Network.
        voice = device.interfaces.get(name="Voice")
        network = device.interfaces.get(name="Network")
        self.assertEqual(voice.parent_interface, network)

    def test_skips_already_linked_phone(self) -> None:
        """A Phone with Phone.device already set is left untouched."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        cisco_dt = DeviceType.objects.create(
            manufacturer__name="Cisco",  # implicit-via-FK won't work, but Cisco may exist
            model="Cisco 8845",
        ) if False else None  # noqa: F841 — placeholder; we just need ANY device
        from nautobot.dcim.models import Manufacturer
        from nautobot.extras.models import Role
        cisco, _ = Manufacturer.objects.get_or_create(name="Cisco")
        dt, _ = DeviceType.objects.get_or_create(manufacturer=cisco, model="Cisco 8845",
                                                  defaults={"u_height": 0, "is_full_depth": False})
        role, _ = Role.objects.get_or_create(name="VoIP Phone")
        from django.contrib.contenttypes.models import ContentType
        role.content_types.add(ContentType.objects.get_for_model(Device))
        existing_device = Device.objects.create(
            name="SEPALREADYLINKED", device_type=dt, role=role,
            status=Status.objects.get_for_model(Device).get(name="Active"),
            location=loc,
        )
        ph_models.Phone.objects.create(
            phone_system=ps, device_name="SEPALREADYLINKED",
            device_kind="sep", device=existing_device,
        )
        result = enrich_phone_devices(logger=_make_logger())
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["skipped_already_linked"], 1)

    def test_skips_softphone(self) -> None:
        """CSF/TCT/BOT softphones don't get DCIM Devices — they're software."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        for kind in ("csf", "tct", "bot"):
            ph_models.Phone.objects.create(
                phone_system=ps,
                device_name=f"{kind.upper()}jdoe-{kind}",
                device_kind=kind,
            )
        result = enrich_phone_devices(logger=_make_logger())
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["skipped_softphone"], 3)
        self.assertEqual(Device.objects.filter(name__startswith="CSF").count(), 0)

    def test_skips_phone_with_no_resolvable_location(self) -> None:
        """A Phone whose PhoneSystem has no Location, with no default, is skipped."""
        ps = self._make_phone_system(location=None)
        ph_models.Phone.objects.create(
            phone_system=ps, device_name="SEPNOLOC",
            device_kind="sep", mac_address="ca:fe:ba:be:00:02",
        )
        result = enrich_phone_devices(logger=_make_logger())
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["skipped_no_location"], 1)

    def test_default_location_used_when_phone_system_has_none(self) -> None:
        """``default_location=...`` is the fallback for PhoneSystems that
        haven't been linked to a site."""
        loc = self._make_location()
        ps = self._make_phone_system(location=None)
        ph_models.Phone.objects.create(
            phone_system=ps, device_name="SEPDEFAULT",
            device_kind="sep", mac_address="ca:fe:ba:be:00:03",
            vendor_extras={"axl_model": "Cisco 8845"},
        )
        result = enrich_phone_devices(default_location=loc, logger=_make_logger())
        self.assertEqual(result["created"], 1)
        self.assertEqual(Device.objects.get(name="SEPDEFAULT").location, loc)

    def test_ata_gets_only_network_interface(self) -> None:
        """ATAs are single-port (no PC pass-through) — only Network is created."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        ph_models.Phone.objects.create(
            phone_system=ps, device_name="ATAFOO",  # 'ata' device_kind
            device_kind="ata",
            mac_address="ca:fe:ba:be:00:04",
            vendor_extras={"axl_model": "Cisco ATA 192"},
        )
        enrich_phone_devices(logger=_make_logger())
        device = Device.objects.get(name="ATAFOO")
        iface_names = sorted(i.name for i in device.interfaces.all())
        self.assertEqual(iface_names, ["Network"])  # No PC, no Voice.


class TestEnrichAnalogGatewayDevices(EnrichBaseMixin, TestCase):
    """``enrich_analog_gateway_devices`` matches gateways via three strategies."""

    def _seed_device(self, name: str, model: str, location: Location,
                     serial: str = "", comments: str = "") -> Device:
        from nautobot.dcim.models import Manufacturer
        from nautobot.extras.models import Role
        cisco, _ = Manufacturer.objects.get_or_create(name="Cisco")
        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=cisco, model=model,
            defaults={"u_height": 1, "is_full_depth": False},
        )
        role, _ = Role.objects.get_or_create(name="VoIP Gateway")
        from django.contrib.contenttypes.models import ContentType
        role.content_types.add(ContentType.objects.get_for_model(Device))
        return Device.objects.create(
            name=name, device_type=dt, role=role,
            status=Status.objects.get_for_model(Device).get(name="Active"),
            location=location, serial=serial, comments=comments,
        )

    def test_strategy_1_exact_name_match(self) -> None:
        """When CCM-name matches DCIM-name 1:1, link via exact match."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        existing = self._seed_device("VG450-001", "VG450", loc)
        gw = ph_models.AnalogGateway.objects.create(
            phone_system=ps, name="VG450-001", model="VG450", protocol="mgcp",
        )
        result = enrich_analog_gateway_devices(logger=_make_logger())
        self.assertEqual(result["matched_exact"], 1)
        gw.refresh_from_db()
        self.assertEqual(gw.device, existing)

    def test_strategy_2_mac_base_in_serial(self) -> None:
        """MAC-base extracted from CCM name matches DCIM Device.serial."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        # CCM name HQGW4ABC0DEF01 → mac_base 4ABC0DEF
        device = self._seed_device(
            "RACK-R00-VG450", "VG450", loc, serial="MAC4ABC0DEF",
        )
        gw = ph_models.AnalogGateway.objects.create(
            phone_system=ps, name="HQGW4ABC0DEF01", model="VG450", protocol="mgcp",
        )
        result = enrich_analog_gateway_devices(logger=_make_logger())
        self.assertEqual(result["matched_mac_base"], 1)
        gw.refresh_from_db()
        self.assertEqual(gw.device, device)

    def test_strategy_3_unique_devicetype_in_location(self) -> None:
        """Single VG450 at the PhoneSystem's location → link by uniqueness."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        device = self._seed_device("RACK-R02-OTHER-NAME", "VG450", loc)
        gw = ph_models.AnalogGateway.objects.create(
            phone_system=ps, name="ANOTHER-CCM-NAME", model="VG450", protocol="mgcp",
        )
        result = enrich_analog_gateway_devices(logger=_make_logger())
        self.assertEqual(result["matched_unique_dt"], 1)
        gw.refresh_from_db()
        self.assertEqual(gw.device, device)

    def test_ambiguous_unique_devicetype_unmatched(self) -> None:
        """Two VG450s in the same location → ambiguous, leave unmatched."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        self._seed_device("VG450-A", "VG450", loc)
        self._seed_device("VG450-B", "VG450", loc)
        gw = ph_models.AnalogGateway.objects.create(
            phone_system=ps, name="CCM-NAME", model="VG450", protocol="mgcp",
        )
        result = enrich_analog_gateway_devices(logger=_make_logger())
        self.assertEqual(result["unmatched"], 1)
        gw.refresh_from_db()
        self.assertIsNone(gw.device)

    def test_already_linked_skipped(self) -> None:
        """Gateways already linked aren't re-processed."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        device = self._seed_device("VG450-LINKED", "VG450", loc)
        ph_models.AnalogGateway.objects.create(
            phone_system=ps, name="HQGW1234567801", model="VG450",
            protocol="mgcp", device=device,
        )
        result = enrich_analog_gateway_devices(logger=_make_logger())
        self.assertEqual(result["skipped_already_linked"], 1)
        self.assertEqual(result["matched_exact"], 0)


class TestEnrichAnalogGatewayInterfaces(EnrichBaseMixin, TestCase):
    """``enrich_analog_gateway_interfaces`` materializes FXS port Interfaces."""

    def _link_gateway_to_device(self, ps: ph_models.PhoneSystem,
                                 loc: Location) -> ph_models.AnalogGateway:
        from nautobot.dcim.models import Manufacturer
        from nautobot.extras.models import Role
        cisco, _ = Manufacturer.objects.get_or_create(name="Cisco")
        dt, _ = DeviceType.objects.get_or_create(
            manufacturer=cisco, model="VG450",
            defaults={"u_height": 1, "is_full_depth": False},
        )
        role, _ = Role.objects.get_or_create(name="VoIP Gateway")
        from django.contrib.contenttypes.models import ContentType
        role.content_types.add(ContentType.objects.get_for_model(Device))
        device = Device.objects.create(
            name="VG450-001", device_type=dt, role=role,
            status=Status.objects.get_for_model(Device).get(name="Active"),
            location=loc,
        )
        return ph_models.AnalogGateway.objects.create(
            phone_system=ps, name="VG450-001", model="VG450",
            protocol="mgcp", device=device,
            vendor_extras={"module_units": [
                {"unit_index": 1, "subunit_index": 0, "subunit_product": "SM-X-72FXS-SCCP"},
            ]},
        )

    def test_skips_unlinked_gateway(self) -> None:
        """Gateways without a linked Device can't get interfaces — skipped."""
        ps = self._make_phone_system(location=self._make_location())
        ph_models.AnalogGateway.objects.create(
            phone_system=ps, name="UNLINKED-GW", model="VG450",
            protocol="mgcp", device=None,
        )
        result = enrich_analog_gateway_interfaces(logger=_make_logger())
        self.assertEqual(result["skipped_no_device"], 1)
        self.assertEqual(result["created"], 0)

    def test_creates_interfaces_per_port(self) -> None:
        """Each AnalogPort → one Interface on the linked Device, named in
        Cisco IOS voice-port convention."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        gw = self._link_gateway_to_device(ps, loc)
        ph_models.AnalogPort.objects.create(
            gateway=gw, port_index=0x20A, port_type="fxs",  # → voice-port 1/0/9
        )
        ph_models.AnalogPort.objects.create(
            gateway=gw, port_index=0x201, port_type="fxs",  # → voice-port 1/0/0
        )
        result = enrich_analog_gateway_interfaces(logger=_make_logger())
        self.assertEqual(result["created"], 2)
        iface_names = sorted(i.name for i in gw.device.interfaces.all())
        self.assertIn("voice-port 1/0/0", iface_names)
        self.assertIn("voice-port 1/0/9", iface_names)

    def test_idempotent_second_run(self) -> None:
        """Re-running creates nothing (get_or_create on Interface.name)."""
        loc = self._make_location()
        ps = self._make_phone_system(location=loc)
        gw = self._link_gateway_to_device(ps, loc)
        ph_models.AnalogPort.objects.create(
            gateway=gw, port_index=0x201, port_type="fxs",
        )
        enrich_analog_gateway_interfaces(logger=_make_logger())
        # Re-run: should be no-op on creates.
        result = enrich_analog_gateway_interfaces(logger=_make_logger())
        self.assertEqual(result["created"], 0)
        self.assertEqual(gw.device.interfaces.count(), 1)
