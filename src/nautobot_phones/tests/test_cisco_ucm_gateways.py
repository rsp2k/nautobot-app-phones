"""Tests for the CCM ``_load_gateways_and_ports`` two-phase loader.

The loader does two things:

  1. Sync AnalogGateway records from listGateway + getGateway. ``listGateway``
     returns the gateway under ``domainName`` (not ``name`` — earlier code
     used the wrong field and silently produced empty IDs); ``getGateway``
     enriches with a unit/subunit hierarchy that captures module count
     and FXS port capacity into ``vendor_extras.module_units``.

  2. Walk AN4* phone records to materialize AnalogPort rows. The CCM
     convention is ``AN4<9-char-mac-suffix><3-char-port-hex>`` — 15 chars
     total. The 9-char suffix matches the trailing 9 chars of a gateway
     name (``<SITE>GW<8-hex>01``-style), so we can link AN4 → gateway
     by suffix. Per-record getPhone fetches the DN binding for the
     first line on each port.
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
    """Empty-by-default AXL client mock."""
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


def _run(client: Any) -> CUCMSourceAdapter:
    adapter = CUCMSourceAdapter(
        client=client,
        phone_system_record=_make_phone_system_stub(),
        enrich_phone_lines=False,
        enrich_phone_ip=False,
    )
    adapter.load()
    return adapter


# ---------------------------------------------------------------------------
# Phase 1 — AnalogGateway emission from listGateway + getGateway
# ---------------------------------------------------------------------------


class TestGatewayEmission(SimpleTestCase):
    """``listGateway`` rows → AnalogGateway DiffSync records."""

    def test_uses_domainName_not_name_for_id(self) -> None:
        """``listGateway`` returns the canonical name under ``domainName``;
        ``name`` is something else (or absent). Earlier adapter code used
        ``name`` and silently produced empty-string identifiers."""
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[
            {"domainName": "HQGW4ABC0DEF01", "product": "VG450", "protocol": "MGCP"},
        ])
        adapter = _run(client)
        gw = next(iter(adapter.get_all("analog_gateway")))
        self.assertEqual(gw.name, "HQGW4ABC0DEF01")
        self.assertEqual(gw.model, "VG450")
        self.assertEqual(gw.protocol, "mgcp")  # lowercased

    def test_blank_domainName_skipped(self) -> None:
        """Defensive: rows without a usable name are dropped silently
        rather than creating an unidentifiable AnalogGateway."""
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[
            {"domainName": "", "product": "VG450"},
            {"domainName": "OK-GW", "product": "VG450"},
        ])
        adapter = _run(client)
        names = [g.name for g in adapter.get_all("analog_gateway")]
        self.assertEqual(names, ["OK-GW"])

    def test_protocol_defaults_to_mgcp_when_missing(self) -> None:
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[
            {"domainName": "GW1", "product": "VG450"},  # no protocol field
        ])
        adapter = _run(client)
        gw = next(iter(adapter.get_all("analog_gateway")))
        self.assertEqual(gw.protocol, "mgcp")

    def test_vendor_extras_excludes_promoted_fields(self) -> None:
        """``domainName``, ``product``, ``protocol`` are promoted to
        first-class fields — they should NOT also appear in vendor_extras."""
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[
            {"domainName": "GW1", "product": "VG450", "protocol": "MGCP",
             "description": "Site A gateway"},
        ])
        adapter = _run(client)
        gw = next(iter(adapter.get_all("analog_gateway")))
        self.assertNotIn("domainName", gw.vendor_extras)
        self.assertNotIn("product", gw.vendor_extras)
        self.assertNotIn("protocol", gw.vendor_extras)
        self.assertEqual(gw.vendor_extras.get("description"), "Site A gateway")


class TestGatewayUnitEnrichment(SimpleTestCase):
    """``getGateway`` enriches vendor_extras.module_units with subunit detail."""

    def _make_getGateway(self, units_payload: Any) -> Any:
        """Build a getGateway response with the given units/subunits shape.
        Adapter uses ``_get(_get(full, "return"), "gateway")`` — that path
        works with dict-shape mocks via _get's tolerant accessors."""
        return {"return": {"gateway": {"units": units_payload}}}

    def test_unit_subunit_array_captures_module_layout(self) -> None:
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[{"domainName": "GW1"}])
        client._service.getGateway = MagicMock(return_value=self._make_getGateway({
            "unit": [
                {"index": 1, "product": "VWIC3-2MFT-T1/E1", "subunits": {"subunit": [
                    {"index": 0, "product": "SM-X-72FXS-SCCP", "beginPort": 1},
                ]}},
                {"index": 2, "product": "VWIC3-1MFT-T1/E1", "subunits": {"subunit": [
                    {"index": 0, "product": "SM-X-48FXS", "beginPort": 73},
                ]}},
            ],
        }))
        adapter = _run(client)
        gw = next(iter(adapter.get_all("analog_gateway")))
        units = gw.vendor_extras["module_units"]
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0]["unit_index"], 1)
        self.assertEqual(units[0]["subunit_product"], "SM-X-72FXS-SCCP")
        self.assertEqual(units[1]["subunit_product"], "SM-X-48FXS")
        self.assertEqual(units[1]["begin_port"], 73)

    def test_scalar_unit_normalized_to_list(self) -> None:
        """zeep quirk: a 1-element unit array sometimes comes back as a
        scalar object instead of a list. Same for subunits. Adapter
        normalizes both."""
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[{"domainName": "GW1"}])
        client._service.getGateway = MagicMock(return_value=self._make_getGateway({
            # Single unit returned as scalar, single subunit also scalar.
            "unit": {"index": 1, "product": "MOD1", "subunits": {"subunit": {
                "index": 0, "product": "SM-X-24FXS", "beginPort": 1,
            }}},
        }))
        adapter = _run(client)
        gw = next(iter(adapter.get_all("analog_gateway")))
        units = gw.vendor_extras["module_units"]
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["subunit_product"], "SM-X-24FXS")

    def test_getGateway_failure_still_emits_gateway(self) -> None:
        """A failed getGateway leaves vendor_extras.module_units empty
        but doesn't drop the gateway record — listGateway gave us enough
        to identify it."""
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[
            {"domainName": "GW1", "product": "VG450"},
        ])
        client._service.getGateway = MagicMock(side_effect=Exception("AXL down"))
        adapter = _run(client)
        gws = list(adapter.get_all("analog_gateway"))
        self.assertEqual(len(gws), 1)
        self.assertEqual(gws[0].vendor_extras["module_units"], [])

    def test_no_units_in_response_yields_empty_summary(self) -> None:
        """A gateway with no module info just gets an empty list — the
        key still exists in vendor_extras for downstream consistency."""
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[{"domainName": "GW1"}])
        client._service.getGateway = MagicMock(return_value=self._make_getGateway(None))
        adapter = _run(client)
        gw = next(iter(adapter.get_all("analog_gateway")))
        self.assertEqual(gw.vendor_extras["module_units"], [])


# ---------------------------------------------------------------------------
# Phase 2 — AnalogPort emission from AN4 phones
# ---------------------------------------------------------------------------


class TestAnalogPortEmission(SimpleTestCase):
    """AN4* phone records → AnalogPort rows, linked to gateway via suffix."""

    def _client_with_gateway_and_an4(
        self,
        gw_name: str,
        an4_devices: list[dict],
        get_phone_responses: dict[str, Any] | None = None,
    ) -> Any:
        """One gateway + the supplied AN4 devices. ``get_phone_responses``
        maps device name → getPhone return value (for the per-record DN
        binding lookup)."""
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[{"domainName": gw_name}])
        # _list is the wrapper used for the AN4% query.
        client._list = MagicMock(return_value=an4_devices)
        responses = get_phone_responses or {}
        client.get_phone = MagicMock(
            side_effect=lambda name: responses.get(name, {"lines": None}),
        )
        return client

    def test_matched_suffix_emits_port_with_correct_index(self) -> None:
        """Use a gateway name + AN4 name pair whose 9-char suffixes match exactly."""
        # Pick gw_name so gw_name[-9:].upper() = "4ABC0DEF0" (length 9).
        # AN4 device: "AN4" + "4ABC0DEF0" + "201" = 15 chars, mac_suffix = "4ABC0DEF0"
        # 0x201 = 513.
        client = self._client_with_gateway_and_an4(
            gw_name="GW-4ABC0DEF0",  # length=12, last 9 chars = "4ABC0DEF0"
            an4_devices=[{"name": "AN44ABC0DEF0201"}],
        )
        adapter = _run(client)
        ports = list(adapter.get_all("analog_port"))
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].port_index, 0x201)
        self.assertEqual(ports[0].port_type, "fxs")
        self.assertEqual(ports[0].gateway__name, "GW-4ABC0DEF0")

    def test_an4_with_unknown_suffix_skipped(self) -> None:
        """AN4 device referencing a gateway we don't have → silently skipped."""
        client = self._client_with_gateway_and_an4(
            gw_name="GW-KNOWN",
            an4_devices=[
                {"name": "AN4UNKNOWN12201"},  # suffix doesn't match GW-KNOWN
            ],
        )
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("analog_port"))), 0)

    def test_wrong_prefix_skipped(self) -> None:
        """A non-AN4 phone in the AN4% query result (shouldn't happen but
        defensive) is skipped."""
        client = self._client_with_gateway_and_an4(
            gw_name="GW-4ABC0DEF0",
            an4_devices=[
                {"name": "SEP4ABC0DEF0201"},  # SEP, not AN4
            ],
        )
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("analog_port"))), 0)

    def test_wrong_length_skipped(self) -> None:
        """AN4 name must be exactly 15 chars (3+9+3). Anything else
        can't be cleanly decoded — skipped."""
        client = self._client_with_gateway_and_an4(
            gw_name="GW-4ABC0DEF0",
            an4_devices=[
                {"name": "AN44ABC0DEF02"},   # too short
                {"name": "AN44ABC0DEF02011"},  # too long
            ],
        )
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("analog_port"))), 0)

    def test_invalid_port_hex_skipped(self) -> None:
        """The trailing 3 chars must be valid hex — non-hex skips the row
        rather than crashing on int(..., 16)."""
        client = self._client_with_gateway_and_an4(
            gw_name="GW-4ABC0DEF0",
            an4_devices=[
                # Trailing 3 chars "ZZZ" aren't valid hex.
                {"name": "AN44ABC0DEF0ZZZ"},
            ],
        )
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("analog_port"))), 0)

    def test_getphone_failure_skips_only_that_port(self) -> None:
        """A failed getPhone for one AN4 device skips that single port
        but doesn't kill the whole loop."""
        client = self._client_with_gateway_and_an4(
            gw_name="GW-4ABC0DEF0",
            an4_devices=[
                {"name": "AN44ABC0DEF0201"},
                {"name": "AN44ABC0DEF0202"},
            ],
        )

        def fake_get_phone(name):
            if name.endswith("202"):
                raise Exception("AXL timeout")
            return {"lines": None}

        client.get_phone = MagicMock(side_effect=fake_get_phone)
        adapter = _run(client)
        ports = list(adapter.get_all("analog_port"))
        # Only the one that didn't error gets a port.
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].port_index, 0x201)

    def test_no_lines_yields_port_with_null_dn(self) -> None:
        """An AN4 port with no line/DN binding emits the port but with
        a NULL directory_number — operators may bind it later."""
        client = self._client_with_gateway_and_an4(
            gw_name="GW-4ABC0DEF0",
            an4_devices=[{"name": "AN44ABC0DEF0201"}],
            get_phone_responses={"AN44ABC0DEF0201": {"lines": None}},
        )
        adapter = _run(client)
        port = next(iter(adapter.get_all("analog_port")))
        self.assertIsNone(port.directory_number__extension)
        self.assertIsNone(port.directory_number__partition__name)

    def test_first_line_dn_extracted(self) -> None:
        """When getPhone returns a line with a dirn, the port records the
        bound extension + partition. (Only the first line is used —
        analog ports terminate one DN.)"""
        client = self._client_with_gateway_and_an4(
            gw_name="GW-4ABC0DEF0",
            an4_devices=[{"name": "AN44ABC0DEF0201"}],
            get_phone_responses={"AN44ABC0DEF0201": {
                "lines": {"line": [
                    {"dirn": {"pattern": "5550100",
                              "routePartitionName": {"_value_1": "Analog-PT"}}},
                ]},
            }},
        )
        adapter = _run(client)
        port = next(iter(adapter.get_all("analog_port")))
        self.assertEqual(port.directory_number__extension, "5550100")
        self.assertEqual(port.directory_number__partition__name, "Analog-PT")

    def test_scalar_line_normalized_to_list(self) -> None:
        """zeep quirk: a 1-element `lines.line` sometimes comes back as
        scalar instead of list. Adapter normalizes."""
        client = self._client_with_gateway_and_an4(
            gw_name="GW-4ABC0DEF0",
            an4_devices=[{"name": "AN44ABC0DEF0201"}],
            get_phone_responses={"AN44ABC0DEF0201": {
                "lines": {"line": {  # single line as scalar, not list
                    "dirn": {"pattern": "5550100",
                             "routePartitionName": {"_value_1": "Analog-PT"}},
                }},
            }},
        )
        adapter = _run(client)
        port = next(iter(adapter.get_all("analog_port")))
        self.assertEqual(port.directory_number__extension, "5550100")


class TestPhase2EarlyExit(SimpleTestCase):
    """When no gateways were emitted, Phase 2 returns early without calling
    the AN4 query — saves an AXL round-trip."""

    def _called_with_an4_query(self, list_mock: Any) -> bool:
        """Check whether ``_list`` was invoked with the AN4% search query.

        The same ``_list`` helper is also used by hunt-subsystem loaders
        (listLineGroup, listHuntList, listHuntPilot), so we can't just
        check call_count — we need to look for the AN4-specific signature.
        """
        for call in list_mock.call_args_list:
            args, kwargs = call
            crit = kwargs.get("search_criteria") or {}
            if crit.get("name") == "AN4%":
                return True
        return False

    def test_no_gateways_skips_an4_query(self) -> None:
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[])
        # If Phase 2 ran, this would emit a port (but the suffix wouldn't match
        # so we'd still see 0 ports). The stronger check is below: the AN4
        # query simply isn't issued.
        client._list = MagicMock(return_value=[{"name": "AN4WHATEVER0201"}])
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("analog_port"))), 0)
        # Other loaders may have called _list; the AN4-specific signature
        # should NOT be among them.
        self.assertFalse(self._called_with_an4_query(client._list))

    def test_only_short_named_gateway_skips_an4_query(self) -> None:
        """A gateway with name < 9 chars can't be in the suffix map →
        same early-exit path."""
        client = _make_client()
        client.list_gateways = MagicMock(return_value=[
            {"domainName": "GW"},  # only 2 chars, can't be a suffix-keyable gateway
        ])
        client._list = MagicMock(return_value=[{"name": "AN44ABC0DEF0201"}])
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("analog_port"))), 0)
        self.assertFalse(self._called_with_an4_query(client._list))


class TestServiceGetGatewayWrapper(SimpleTestCase):
    """``_service_get_gateway`` is the AXL call wrapper — returns None on
    exception so callers can fall through gracefully."""

    def test_returns_response_on_success(self) -> None:
        client = _make_client()
        client._service.getGateway = MagicMock(return_value={"ok": True})
        adapter = CUCMSourceAdapter(
            client=client,
            phone_system_record=_make_phone_system_stub(),
            enrich_phone_lines=False, enrich_phone_ip=False,
        )
        result = adapter._service_get_gateway("GW1")
        self.assertEqual(result, {"ok": True})
        client._service.getGateway.assert_called_once_with(domainName="GW1")

    def test_returns_none_on_exception(self) -> None:
        client = _make_client()
        client._service.getGateway = MagicMock(side_effect=Exception("AXL down"))
        adapter = CUCMSourceAdapter(
            client=client,
            phone_system_record=_make_phone_system_stub(),
            enrich_phone_lines=False, enrich_phone_ip=False,
        )
        result = adapter._service_get_gateway("GW1")
        self.assertIsNone(result)
