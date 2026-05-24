"""Tests for the CCM adapter's heaviest loader cluster: phones + lines +
RIS enrichment + per-phone getPhone enrichment.

``_load_phones_and_lines`` is the biggest single loader in the CCM
adapter — ~160 lines covering prefix-based dispatch (SEP/CSF/TCT/BOT/
CSK/ATA/CCX/CER/CTI), MAC extraction, RIS live-status merge, FK name
resolution, and inline Line emission. ``_fetch_ris_data`` is the
optional bulk RIS fetch. ``_enrich_lines`` is the optional per-phone
deep enrichment that pulls Speed Dials, BLFs, Service URLs, and the
per-line config fields (max_num_calls, busy_trigger, etc.).

Mock pattern mirrors the sibling files: minimal AXL client; per-test
overrides for the surface under assertion.
"""

from typing import Any
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from nautobot_phones.integrations.cisco_ucm.adapter import CUCMSourceAdapter


def _make_phone_system_stub(name: str = "LAB-CCM") -> Any:
    ps = MagicMock()
    ps.name = name
    ps.vendor = "cisco_ucm"
    ps.version = "15.0"
    ps.hostname = "ccm-pub.example.com"
    return ps


def _make_client() -> Any:
    """Empty-by-default AXL client mock — same shape as other test files."""
    client = MagicMock()
    for name in (
        "list_route_lists", "list_route_groups", "list_route_partitions",
        "list_css", "list_lines", "list_phones", "list_sip_trunks",
        "list_route_patterns", "list_translation_patterns", "list_gateways",
    ):
        setattr(client, name, MagicMock(return_value=[]))
    client._list = MagicMock(return_value=[])
    client._service = MagicMock()
    for name in (
        "getRouteList", "getRouteGroup", "getHuntList", "getLineGroup",
        "getGateway", "getDevicePool", "getVoiceMailProfile",
        "getCallPickupGroup", "getRoutePattern", "getCss",
    ):
        setattr(client._service, name, MagicMock(return_value={"return": {}}))
    for name in ("listDevicePool", "listVoiceMailProfile",
                 "listCallPickupGroup", "listLine", "listHuntPilot",
                 "listHuntList", "listLineGroup"):
        setattr(client._service, name, MagicMock(return_value={"return": {}}))
    return client


def _run(
    client: Any,
    *,
    enrich_phone_lines: bool = False,
    enrich_phone_ip: bool = False,
    ris_client: Any = None,
) -> CUCMSourceAdapter:
    adapter = CUCMSourceAdapter(
        client=client,
        phone_system_record=_make_phone_system_stub(),
        ris_client=ris_client,
        enrich_phone_lines=enrich_phone_lines,
        enrich_phone_ip=enrich_phone_ip,
    )
    adapter.load()
    return adapter


# ---------------------------------------------------------------------------
# Phone prefix dispatch (_PHONE_KINDS_BY_PREFIX)
# ---------------------------------------------------------------------------


class TestPhonePrefixDispatch(SimpleTestCase):
    """The 3-letter device-name prefix selects the ``device_kind`` value.

    AN4 is intentionally NOT in the table — analog phones attached to
    a gateway become AnalogPort records on the gateway side, not Phone
    records. Unrecognized prefixes are silently skipped (logged via the
    job when present).
    """

    def _client_with_phone(self, name: str) -> Any:
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{"name": name}])
        return client

    def test_sep_prefix(self) -> None:
        adapter = _run(self._client_with_phone("SEPCAFEBABE0001"))
        p = next(iter(adapter.get_all("phone")))
        self.assertEqual(p.device_kind, "sep")

    def test_csf_prefix(self) -> None:
        adapter = _run(self._client_with_phone("CSFjdoe"))
        p = next(iter(adapter.get_all("phone")))
        self.assertEqual(p.device_kind, "csf")

    def test_tct_bot_csk_prefixes(self) -> None:
        for prefix, kind in (("TCT", "tct"), ("BOT", "bot"), ("CSK", "csk")):
            adapter = _run(self._client_with_phone(f"{prefix}testuser"))
            p = next(iter(adapter.get_all("phone")))
            self.assertEqual(p.device_kind, kind)

    def test_ata_prefix(self) -> None:
        adapter = _run(self._client_with_phone("ATA001122334455"))
        p = next(iter(adapter.get_all("phone")))
        self.assertEqual(p.device_kind, "ata")

    def test_cti_route_point_prefixes(self) -> None:
        """CCX/CER/CTI are virtual call-routing endpoints — they get Phone
        records but with their own kinds for downstream filtering."""
        for prefix, kind in (("CCX", "ccx"), ("CER", "cer"), ("CTI", "cti")):
            adapter = _run(self._client_with_phone(f"{prefix}-LAB-{prefix}"))
            p = next(iter(adapter.get_all("phone")))
            self.assertEqual(p.device_kind, kind)

    def test_unknown_prefix_skipped(self) -> None:
        """Unrecognized prefix → no Phone record (gateway-attached phones,
        retired hardware kinds, etc.)."""
        adapter = _run(self._client_with_phone("XYZWHATEVER"))
        self.assertEqual(len(list(adapter.get_all("phone"))), 0)

    def test_short_device_name_skipped(self) -> None:
        """Device name < 3 chars can't have a prefix — skipped."""
        adapter = _run(self._client_with_phone("AB"))
        self.assertEqual(len(list(adapter.get_all("phone"))), 0)

    def test_an4_skipped(self) -> None:
        """AN4 prefix is INTENTIONALLY absent — those phones become
        AnalogPort records via _load_gateways_and_ports instead."""
        adapter = _run(self._client_with_phone("AN4001122334455"))
        self.assertEqual(len(list(adapter.get_all("phone"))), 0)


# ---------------------------------------------------------------------------
# MAC extraction from device-name (hardware-prefix endpoints only)
# ---------------------------------------------------------------------------


class TestMacExtraction(SimpleTestCase):
    """SEP/ATA names encode the chassis MAC in the trailing 12 hex chars."""

    def test_sep_extracts_canonical_mac(self) -> None:
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{"name": "SEPCAFEBABE0001"}])
        adapter = _run(client)
        p = next(iter(adapter.get_all("phone")))
        # Lower-case + colon-separated canonical form for storage.
        self.assertEqual(str(p.mac_address), "ca:fe:ba:be:00:01")

    def test_ata_extracts_canonical_mac(self) -> None:
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{"name": "ATA001122334455"}])
        adapter = _run(client)
        p = next(iter(adapter.get_all("phone")))
        self.assertEqual(str(p.mac_address), "00:11:22:33:44:55")

    def test_softphone_has_no_mac(self) -> None:
        """CSF/TCT/BOT/CSK encode a username, not a MAC — mac_address stays None."""
        for name in ("CSFjdoe", "TCTalice", "BOTbob", "CSKtest"):
            client = _make_client()
            client.list_phones = MagicMock(return_value=[{"name": name}])
            adapter = _run(client)
            p = next(iter(adapter.get_all("phone")))
            self.assertIsNone(p.mac_address, f"{name} should have no MAC")

    def test_sep_with_short_name_has_no_mac(self) -> None:
        """SEP prefix but name isn't 15 chars total → can't extract MAC."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{"name": "SEPSHORT"}])
        adapter = _run(client)
        p = next(iter(adapter.get_all("phone")))
        self.assertIsNone(p.mac_address)


# ---------------------------------------------------------------------------
# RIS map integration (enrich_phone_ip + RIS data)
# ---------------------------------------------------------------------------


class TestRisMapIntegration(SimpleTestCase):
    """RIS data populates last_registered_ip + live-status fields."""

    def _client_with_phone(self) -> Any:
        client = _make_client()
        client.list_phones = MagicMock(return_value=[
            {"name": "SEPCAFEBABE0001",
             "currentRegistrationStatus": "unknown"},
        ])
        return client

    def test_no_ris_leaves_live_fields_blank(self) -> None:
        """Without enrich_phone_ip, RIS map is empty and live fields are blank."""
        adapter = _run(self._client_with_phone())
        p = next(iter(adapter.get_all("phone")))
        self.assertIsNone(p.last_registered_ip)
        self.assertEqual(p.active_load, "")
        self.assertEqual(p.live_login_user, "")

    def test_ris_data_populates_live_fields(self) -> None:
        """A matching RIS record fills IP, status, loads, and login user."""
        ris_client = MagicMock()
        ris_client.select_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "ip_address": "10.20.30.40",
            "status": "Registered",
            "active_load": "sip88xx.14-1-1-0001-410",
            "inactive_load": "sip88xx.14-0-1-12001-1",
            "login_user_id": "jdoe",
            "status_reason": "0",
        }])
        adapter = _run(
            self._client_with_phone(),
            enrich_phone_ip=True, ris_client=ris_client,
        )
        p = next(iter(adapter.get_all("phone")))
        self.assertEqual(p.last_registered_ip, "10.20.30.40")
        self.assertEqual(p.registration_status, "registered")
        self.assertEqual(p.active_load, "sip88xx.14-1-1-0001-410")
        self.assertEqual(p.live_login_user, "jdoe")
        self.assertEqual(p.status_reason, "0")

    def test_ris_status_string_normalization(self) -> None:
        """RisPort emits 'UnRegistered' / 'PartiallyRegistered' (mixed
        case, space variants); the adapter normalizes to our snake_case
        enum values."""
        for ris_status, expected in (
            ("UnRegistered", "unregistered"),
            ("PartiallyRegistered", "partially_registered"),
        ):
            ris_client = MagicMock()
            ris_client.select_phones = MagicMock(return_value=[{
                "name": "SEPCAFEBABE0001",
                "status": ris_status,
            }])
            adapter = _run(
                self._client_with_phone(),
                enrich_phone_ip=True, ris_client=ris_client,
            )
            p = next(iter(adapter.get_all("phone")))
            self.assertEqual(p.registration_status, expected, f"{ris_status} → {expected}")

    def test_ris_unknown_status_falls_back_to_axl(self) -> None:
        """Unmapped RIS status → adapter falls back to the AXL field."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[
            {"name": "SEPCAFEBABE0001",
             "currentRegistrationStatus": "registered"},
        ])
        ris_client = MagicMock()
        ris_client.select_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "status": "MysteryStatusValue",
        }])
        adapter = _run(client, enrich_phone_ip=True, ris_client=ris_client)
        p = next(iter(adapter.get_all("phone")))
        # The unmapped status string falls back to AXL's currentRegistrationStatus.
        self.assertEqual(p.registration_status, "registered")


# ---------------------------------------------------------------------------
# _fetch_ris_data — bulk RIS fetch error handling + record indexing
# ---------------------------------------------------------------------------


class TestFetchRisData(SimpleTestCase):
    """``_fetch_ris_data`` populates the ``_ris_map`` dict by device-name."""

    def test_success_indexes_by_name(self) -> None:
        client = _make_client()
        client.list_phones = MagicMock(return_value=[
            {"name": "SEPCAFEBABE0001"},
            {"name": "SEPDECAFB0BA002"},
        ])
        ris_client = MagicMock()
        ris_client.select_phones = MagicMock(return_value=[
            {"name": "SEPCAFEBABE0001", "ip_address": "10.0.0.1", "status": "Registered"},
            {"name": "SEPDECAFB0BA002", "ip_address": "10.0.0.2", "status": "UnRegistered"},
        ])
        adapter = _run(client, enrich_phone_ip=True, ris_client=ris_client)
        phones = {p.device_name: p for p in adapter.get_all("phone")}
        self.assertEqual(phones["SEPCAFEBABE0001"].last_registered_ip, "10.0.0.1")
        self.assertEqual(phones["SEPDECAFB0BA002"].last_registered_ip, "10.0.0.2")

    def test_failed_fetch_caught_silently(self) -> None:
        """RIS fetch exception → continues sync; phones get blank live fields.

        This is critical: a downed RIS endpoint must NOT abort the whole
        sync. We've seen real outages where RIS is restarting while AXL
        is fine; the sync should produce stale-but-usable Phone records
        rather than failing entirely."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{"name": "SEPCAFEBABE0001"}])
        ris_client = MagicMock()
        ris_client.select_phones = MagicMock(side_effect=Exception("RIS timeout"))
        adapter = _run(client, enrich_phone_ip=True, ris_client=ris_client)
        # Phone still emitted, just without RIS data.
        p = next(iter(adapter.get_all("phone")))
        self.assertEqual(p.device_name, "SEPCAFEBABE0001")
        self.assertIsNone(p.last_registered_ip)

    def test_blank_name_skipped_in_ris_map(self) -> None:
        """Defensive: a RIS row with blank Name doesn't pollute the map."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{"name": "SEPCAFEBABE0001"}])
        ris_client = MagicMock()
        ris_client.select_phones = MagicMock(return_value=[
            {"name": "", "ip_address": "1.1.1.1", "status": "Registered"},  # skipped
            {"name": "SEPCAFEBABE0001", "ip_address": "10.0.0.1", "status": "Registered"},
        ])
        adapter = _run(client, enrich_phone_ip=True, ris_client=ris_client)
        p = next(iter(adapter.get_all("phone")))
        self.assertEqual(p.last_registered_ip, "10.0.0.1")


# ---------------------------------------------------------------------------
# Phone fields: FK resolution, vendor_extras flow, axl_model promotion
# ---------------------------------------------------------------------------


class TestPhoneFields(SimpleTestCase):
    """Per-phone field extraction: FK names, vendor_extras, axl_model."""

    def _xfk(self, value: str) -> Any:
        """Build an XFkType mock — what AXL returns for FK refs."""
        obj = MagicMock(spec=["_value_1"])
        obj._value_1 = value
        return obj

    def test_fk_refs_resolve_to_plain_names(self) -> None:
        """devicePoolName, locationName, ownerUserName are XFkType refs —
        adapter pulls the ``_value_1`` plain string and threads them
        through to the appropriate columns or vendor_extras."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "devicePoolName": self._xfk("Default-DP"),
            "locationName": self._xfk("Hub-Site"),
            "ownerUserName": self._xfk("jdoe"),
            "model": "Cisco 8845",
        }])
        adapter = _run(client)
        p = next(iter(adapter.get_all("phone")))
        self.assertEqual(p.device_profile__name, "Default-DP")
        self.assertEqual(p.media_zone, "Hub-Site")
        self.assertEqual(p.owner_user_id, "jdoe")

    def test_ccm_literal_none_treated_as_blank_fk(self) -> None:
        """CCM emits the literal STRING 'None' for empty FKs — treat as blank
        rather than passing through. Otherwise FK resolution downstream tries
        to look up a record literally named 'None'."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "devicePoolName": self._xfk("None"),
            "ownerUserName": self._xfk("None"),
        }])
        adapter = _run(client)
        p = next(iter(adapter.get_all("phone")))
        self.assertIsNone(p.device_profile__name)
        self.assertEqual(p.owner_user_id, "")

    def test_axl_model_promoted_to_vendor_extras(self) -> None:
        """``model`` lives in vendor_extras['axl_model'] — Phone.model itself
        was removed (the DCIM Device is the source of truth for hardware
        identity, and the model is read back through that)."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "model": "Cisco 8845",
        }])
        adapter = _run(client)
        p = next(iter(adapter.get_all("phone")))
        self.assertEqual(p.vendor_extras["axl_model"], "Cisco 8845")

    def test_stringly_typed_bool_coerced(self) -> None:
        """mtpRequired comes back as a string ('true'/'false') in AXL —
        adapter coerces to a real bool inside vendor_extras."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "mtpRequired": "true",
        }])
        adapter = _run(client)
        p = next(iter(adapter.get_all("phone")))
        self.assertTrue(p.vendor_extras["mtpRequired"])

    def test_dnd_status_axl_bool_coercion(self) -> None:
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "dndStatus": "true",
        }])
        adapter = _run(client)
        p = next(iter(adapter.get_all("phone")))
        self.assertTrue(p.dnd_status)


# ---------------------------------------------------------------------------
# Inline line emission from listPhone nested response
# ---------------------------------------------------------------------------


class TestInlineLineEmission(SimpleTestCase):
    """Lines come from ``phone.lines.line[*]`` in the bulk listPhone response."""

    def test_one_phone_with_lines(self) -> None:
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "lines": {"line": [
                {
                    "index": 1,
                    "dirn": {"pattern": "1001",
                             "routePartitionName": {"_value_1": "Internal-PT"}},
                    "label": "Main",
                    "ringSetting": "Ring",
                },
                {
                    "index": 2,
                    "dirn": {"pattern": "1002",
                             "routePartitionName": {"_value_1": "Internal-PT"}},
                    "label": "Backup",
                    "ringSetting": "Ring",
                },
            ]},
        }])
        adapter = _run(client)
        lines = sorted(adapter.get_all("line"), key=lambda L: L.button_index)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].button_index, 1)
        self.assertEqual(lines[0].directory_number__extension, "1001")
        self.assertEqual(lines[0].label, "Main")
        self.assertEqual(lines[1].directory_number__extension, "1002")

    def test_line_without_dirn_skipped(self) -> None:
        """A line entry with no dirn (rare but possible for park buttons,
        etc.) is silently skipped — no broken FK chain."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "lines": {"line": [
                {"index": 1, "dirn": None},  # skipped
                {"index": 2,
                 "dirn": {"pattern": "1003",
                          "routePartitionName": {"_value_1": "Internal-PT"}}},
            ]},
        }])
        adapter = _run(client)
        lines = list(adapter.get_all("line"))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].directory_number__extension, "1003")

    def test_label_fallback_chain(self) -> None:
        """label → displayAscii → display → "" — adapter picks first non-empty."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001",
            "lines": {"line": [
                {"index": 1,
                 "dirn": {"pattern": "1001",
                          "routePartitionName": {"_value_1": "Internal-PT"}},
                 "label": "", "displayAscii": "ASCII", "display": "Display"},
            ]},
        }])
        adapter = _run(client)
        L = next(iter(adapter.get_all("line")))
        self.assertEqual(L.label, "ASCII")  # First non-empty wins.


# ---------------------------------------------------------------------------
# _enrich_lines — per-phone getPhone for Speed Dials / BLFs / Service URLs
# ---------------------------------------------------------------------------


class TestEnrichLines(SimpleTestCase):
    """``_enrich_lines`` (only runs when enrich_phone_lines=True) pulls four
    button categories from getPhone: Lines (with per-line extras), Speed
    Dials, BLFs, Service URLs."""

    def _client_with_sep_phone(self) -> Any:
        """A SEP phone on listPhone, ready for enrichment."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[{
            "name": "SEPCAFEBABE0001", "model": "Cisco 8845",
        }])
        return client

    def _phone_obj(self, **kwargs) -> Any:
        """Build a getPhone response dict with the four button categories."""
        return {
            "lines": kwargs.get("lines"),
            "speeddials": kwargs.get("speeddials"),
            "busyLampFields": kwargs.get("busyLampFields"),
            "services": kwargs.get("services"),
        }

    def test_speed_dial_emission(self) -> None:
        client = self._client_with_sep_phone()
        client.get_phone = MagicMock(return_value=self._phone_obj(
            speeddials={"speeddial": [
                {"index": 1, "dirn": "9911", "label": "Emergency"},
                {"index": 2, "dirn": "5550100", "label": "Help Desk"},
                {"index": 3, "dirn": "", "label": "Empty"},  # skipped
            ]},
        ))
        adapter = _run(client, enrich_phone_lines=True)
        sds = sorted(adapter.get_all("speed_dial"), key=lambda s: s.button_index)
        self.assertEqual(len(sds), 2)
        self.assertEqual(sds[0].number, "9911")
        self.assertEqual(sds[1].label, "Help Desk")

    def test_busy_lamp_field_emission(self) -> None:
        client = self._client_with_sep_phone()
        client.get_phone = MagicMock(return_value=self._phone_obj(
            busyLampFields={"busyLampField": [
                {"index": 4, "blfDest": "1010", "label": "Alice",
                 "asteriskService": "true"},
                {"index": 5, "blfDest": "", "label": "Empty"},  # skipped
            ]},
        ))
        adapter = _run(client, enrich_phone_lines=True)
        blfs = list(adapter.get_all("busy_lamp_field"))
        self.assertEqual(len(blfs), 1)
        self.assertEqual(blfs[0].destination, "1010")
        self.assertTrue(blfs[0].asterisk_service)

    def test_service_url_uses_array_position_when_index_blank(self) -> None:
        """``urlButtonIndex=0`` / blank → fall back to array position so
        multi-service phones don't collide on (phone, button_index)."""
        client = self._client_with_sep_phone()
        client.get_phone = MagicMock(return_value=self._phone_obj(
            services={"service": [
                {"url": "http://corp/dir.xml", "label": "Dir"},  # no urlButtonIndex
                {"url": "http://corp/wx.xml", "label": "Weather"},  # no urlButtonIndex
            ]},
        ))
        adapter = _run(client, enrich_phone_lines=True)
        urls = sorted(adapter.get_all("phone_service_url"), key=lambda u: u.button_index)
        self.assertEqual([u.button_index for u in urls], [0, 1])

    def test_service_url_explicit_button_index_honored(self) -> None:
        client = self._client_with_sep_phone()
        client.get_phone = MagicMock(return_value=self._phone_obj(
            services={"service": [
                {"url": "http://corp/dir.xml", "urlButtonIndex": "7", "label": "Dir"},
            ]},
        ))
        adapter = _run(client, enrich_phone_lines=True)
        u = next(iter(adapter.get_all("phone_service_url")))
        self.assertEqual(u.button_index, 7)

    def test_service_url_missing_url_skipped(self) -> None:
        client = self._client_with_sep_phone()
        client.get_phone = MagicMock(return_value=self._phone_obj(
            services={"service": [
                {"url": "", "label": "Empty"},
                {"url": "http://corp/ok.xml", "label": "OK"},
            ]},
        ))
        adapter = _run(client, enrich_phone_lines=True)
        urls = list(adapter.get_all("phone_service_url"))
        self.assertEqual(len(urls), 1)

    def test_per_line_enrichment_pulls_max_calls_etc(self) -> None:
        """Per-line fields (max_num_calls, busy_trigger, missed_call_logging,
        plus CCM-specific extras like mwlPolicy) come from getPhone's
        line entries, not from listPhone."""
        client = self._client_with_sep_phone()
        client.get_phone = MagicMock(return_value=self._phone_obj(
            lines={"line": [
                {"index": 1,
                 "dirn": {"pattern": "1001",
                          "routePartitionName": {"_value_1": "Internal-PT"}},
                 "label": "Main",
                 "maxNumCalls": "4",
                 "busyTrigger": "2",
                 "missedCallLogging": "true",
                 "mwlPolicy": "Use System Policy",
                 "recordingFlag": "Call Recording Disabled"},
            ]},
        ))
        adapter = _run(client, enrich_phone_lines=True)
        L = next(iter(adapter.get_all("line")))
        self.assertEqual(L.max_num_calls, 4)
        self.assertEqual(L.busy_trigger, 2)
        self.assertTrue(L.missed_call_logging)
        # CCM-specific per-line extras go to vendor_extras.
        self.assertIn("mwlPolicy", L.vendor_extras)
        self.assertIn("recordingFlag", L.vendor_extras)

    def test_int_or_none_handles_zero_and_blank(self) -> None:
        """``maxNumCalls=0`` or blank → None (not 0) since 0 is meaningless
        for these capacity fields."""
        client = self._client_with_sep_phone()
        client.get_phone = MagicMock(return_value=self._phone_obj(
            lines={"line": [
                {"index": 1,
                 "dirn": {"pattern": "1001",
                          "routePartitionName": {"_value_1": "Internal-PT"}},
                 "maxNumCalls": "0",
                 "busyTrigger": ""},
            ]},
        ))
        adapter = _run(client, enrich_phone_lines=True)
        L = next(iter(adapter.get_all("line")))
        self.assertIsNone(L.max_num_calls)
        self.assertIsNone(L.busy_trigger)

    def test_getphone_failure_skips_phone_enrichment(self) -> None:
        """A failed getPhone for ONE phone shouldn't kill the whole pass —
        adapter logs + skips that phone, continues with the rest."""
        client = _make_client()
        client.list_phones = MagicMock(return_value=[
            {"name": "SEPCAFEBABE0001", "model": "Cisco 8845"},
            {"name": "SEPDECAFB0BA002", "model": "Cisco 8845"},
        ])

        def fake_get_phone(name):
            if "DECAF" in name:
                raise Exception("AXL timeout")
            return self._phone_obj(speeddials={"speeddial": [
                {"index": 1, "dirn": "9911", "label": "OK"},
            ]})

        client.get_phone = MagicMock(side_effect=fake_get_phone)
        adapter = _run(client, enrich_phone_lines=True)
        # Speed dial only emitted for the working phone.
        sds = list(adapter.get_all("speed_dial"))
        self.assertEqual(len(sds), 1)

    def test_getphone_returns_none_skips_gracefully(self) -> None:
        client = self._client_with_sep_phone()
        client.get_phone = MagicMock(return_value=None)
        adapter = _run(client, enrich_phone_lines=True)
        # No speed dials / BLFs / services emitted, but no crash.
        self.assertEqual(len(list(adapter.get_all("speed_dial"))), 0)
