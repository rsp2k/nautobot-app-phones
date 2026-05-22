"""Idempotency tests for the source ↔ Nautobot adapter round-trip.

The contract under test: ``sync_from(source) → load() → diff_from(source)``
returns ``{create:0, update:0, delete:0}`` on the second pass.

If a sync wants to create or update *anything* on its second run with
the same source data, something is non-deterministic in the
source→ORM→source pipeline. Common culprits we want this test to catch:

* Zeep object reprs leaking into ``vendor_extras`` JSON (read-back
  doesn't recover the original string)
* GFK virtual-field extraction misaligned with the source-side
  emission (e.g. source emits ``target_name="1001"`` but read-back
  produces ``target_name="Internal-PT/1001"``)
* FK natural-key chains that don't round-trip (rare but possible
  when the source emits a normalized name that the DB then stores
  differently)
* Default-value drift (source omits a field that the DB defaults to
  some value, then re-emits with the default value next pass)

We use mocked vendor clients (same pattern as test_cisco_ucm_adapter.py
and test_freepbx_adapter.py) rather than a live container — keeps CI
fast and reproducible. The interesting bug surface is at the
DiffSync ↔ ORM boundary, not at the vendor-API boundary.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from django.test import TestCase

from nautobot_phones import models
from nautobot_phones.diffsync.adapters.nautobot import PhonesNautobotAdapter
from nautobot_phones.integrations.cisco_ucm.adapter import CUCMSourceAdapter
from nautobot_phones.integrations.freepbx.adapter import FreePBXSourceAdapter
from nautobot_phones.integrations.freepbx.client import FreePBXClient


def _assert_zero_diff(test_case, source_adapter, dest_adapter) -> None:
    """Reload both adapters, diff source-from-dest, assert zero changes."""
    diff = source_adapter.diff_from(dest_adapter)
    summary = diff.summary()
    test_case.assertEqual(
        summary.get("create", 0), 0,
        f"Idempotency: expected 0 creates on pass 2, got {summary.get('create', 0)}. "
        f"Full summary: {summary}\nFull diff:\n{diff.dict()}",
    )
    test_case.assertEqual(
        summary.get("update", 0), 0,
        f"Idempotency: expected 0 updates on pass 2, got {summary.get('update', 0)}. "
        f"Full summary: {summary}\nFull diff:\n{diff.dict()}",
    )
    test_case.assertEqual(
        summary.get("delete", 0), 0,
        f"Idempotency: expected 0 deletes on pass 2, got {summary.get('delete', 0)}. "
        f"Full summary: {summary}\nFull diff:\n{diff.dict()}",
    )


# ---------------------------------------------------------------------------
# CCM idempotency — exercises the GFK round-trip (RouteGroupMember)
# ---------------------------------------------------------------------------


def _make_ccm_client() -> Any:
    """Mock AXLClient returning a representative slice: one partition,
    one CSS, one trunk, one analog gateway, one route group containing
    BOTH as members (so the GFK round-trip is exercised end to end)."""
    client = MagicMock()

    # All collections empty by default — tests opt in to non-empty ones below.
    for name in (
        "list_route_lists", "list_partitions", "list_css",
        "list_directory_numbers", "list_phones", "list_translation_patterns",
        "list_device_pools", "list_voicemail_profiles",
        "list_call_pickup_groups", "list_route_patterns",
    ):
        setattr(client, name, MagicMock(return_value=[]))
    client._list = MagicMock(return_value=[])

    # Populated collections:
    client.list_partitions = MagicMock(return_value=[
        {"name": "Internal-PT", "description": "Internal calls"},
    ])
    client.list_sip_trunks = MagicMock(return_value=[
        {"name": "SIP-OUTBOUND", "destinations": {"destination": [
            {"addressIpv4": "203.0.113.10", "port": 5060},
        ]}},
    ])
    client.list_gateways = MagicMock(return_value=[
        # listGateway uses ``domainName``, not ``name``.
        {"domainName": "VG224-LAB", "product": "VG224", "protocol": "MGCP"},
    ])
    client.list_route_groups = MagicMock(return_value=[
        {"name": "Group-A", "description": "", "distributionAlgorithm": "Top Down"},
    ])

    # Per-record enrichment — defaults are empty zeep-style wrappers.
    client._service = MagicMock()
    for name in (
        "getRouteList", "getHuntList", "getLineGroup", "getDevicePool",
        "getVoiceMailProfile", "getCallPickupGroup", "getRoutePattern",
    ):
        # The unwrapping path uses {"return": {<model>: None}} so an empty
        # response is treated as "no nested data".
        setattr(client._service, name, MagicMock(return_value={"return": {name[3].lower() + name[4:]: None}}))

    # getGateway — returns no unit subdetail (the adapter tolerates this).
    client._service.getGateway = MagicMock(return_value={"return": {"gateway": None}})
    # getRouteGroup — returns members covering BOTH GFK target kinds.
    client._service.getRouteGroup = MagicMock(return_value={
        "return": {"routeGroup": {
            "name": "Group-A",
            "members": {"member": [
                {"deviceName": {"_value_1": "SIP-OUTBOUND"}, "deviceSelectionOrder": 1},
                {"deviceName": {"_value_1": "VG224-LAB"}, "deviceSelectionOrder": 2},
            ]},
        }},
    })

    return client


class TestCCMIdempotency(TestCase):
    """CCM source → Nautobot ORM round-trip produces zero diff on pass 2.

    Specifically validates the GFK round-trip: a RouteGroupMember whose
    target is a Trunk + another whose target is an AnalogGateway, both
    written to the DB by ``sync_from``, then read back via the GFK
    extractor and compared to the source. Any drift between
    ``_gfk_lookups`` (write path) and ``_gfk_reads`` (read path) would
    surface as a delete-then-create cycle here.
    """

    def setUp(self) -> None:
        """Create the target PhoneSystem the adapter syncs into."""
        self.ps = models.PhoneSystem.objects.create(
            name="LAB-CCM",
            vendor="cisco_ucm",
            version="15.0",
            hostname="ccm-pub.example.com",
        )

    def _build_source(self, client: Any) -> CUCMSourceAdapter:
        source = CUCMSourceAdapter(
            client=client,
            phone_system_record=self.ps,
            enrich_phone_lines=False,
            enrich_phone_ip=False,
        )
        source.load()
        return source

    def _build_dest(self) -> PhonesNautobotAdapter:
        dest = PhonesNautobotAdapter(job=None, include_lines=False)
        dest.load()
        return dest

    def test_second_pass_zero_diff(self) -> None:
        """Two passes against identical mocked source → zero changes on pass 2."""
        client = _make_ccm_client()

        # Pass 1: load source + dest, sync into DB.
        source1 = self._build_source(client)
        dest1 = self._build_dest()
        dest1.sync_from(source1)

        # Records should now exist in the DB.
        self.assertEqual(models.RouteGroupMember.objects.count(), 2,
                         "Expected 2 RouteGroupMember rows (Trunk + AnalogGateway targets)")

        # Pass 2: fresh adapters reload from current DB state.
        source2 = self._build_source(client)
        dest2 = self._build_dest()

        _assert_zero_diff(self, source2, dest2)

    def test_gfk_target_kinds_round_trip(self) -> None:
        """Concrete RouteGroupMember.target round-trip: the same target_kind
        and target_name extracted from the DB matches what the source emits."""
        client = _make_ccm_client()
        source = self._build_source(client)
        dest = self._build_dest()
        dest.sync_from(source)

        # Read back via the destination adapter — this is what the GFK
        # extractor will produce on the second pass.
        fresh_dest = self._build_dest()
        rgms = sorted(
            fresh_dest.get_all("route_group_member"),
            key=lambda r: r.priority,
        )
        self.assertEqual(
            [(m.target_kind, m.target_name, m.priority) for m in rgms],
            [("trunk", "SIP-OUTBOUND", 1), ("analoggateway", "VG224-LAB", 2)],
        )


# ---------------------------------------------------------------------------
# FreePBX idempotency — exercises the synthesized one-trunk-per-group path
# ---------------------------------------------------------------------------


def _make_freepbx_client() -> FreePBXClient:
    """Mock FreePBXClient with a representative slice of seeded data."""
    with patch("nautobot_phones.integrations.freepbx.client.httpx.Client"):
        client = FreePBXClient(
            base_url="http://freepbx",
            client_id="test-id",
            client_secret="test-secret",
        )

    # Stub HTTP-level methods so nothing reaches the network.
    client.gql = MagicMock(return_value={})
    client._get_token = MagicMock(return_value="dummy-token")

    # Adapter-facing helpers (mirrors test_freepbx_adapter.py patterns).
    client.list_extensions = MagicMock(return_value=[
        {
            "extensionId": "1001",
            "user": {"name": "Alice", "voicemail": "novm"},
            "coreDevice": {"id": "1001", "deviceId": "PJSIP/1001",
                           "tech": "pjsip", "description": "Alice's desk"},
        },
    ])
    client.list_trunks = MagicMock(return_value=[
        {"trunkid": 1, "name": "ITSP-1", "tech": "pjsip",
         "outcid": "5551234567", "channelid": "5060", "disabled": "off"},
    ])
    client.list_outbound_routes = MagicMock(return_value=[
        {
            "route_id": 1,
            "name": "NANP",
            "outcid": "5551234567",
            "patterns": [{"prepend": "", "prefix": "", "match_pattern": "NXXNXXXXXX",
                          "match_cid": "", "pattern_position": 1}],
            "trunk_seq": [(1, 1)],
        },
    ])
    # ``list_voicemail_boxes`` (not ``list_voicemail_profiles``) is the
    # real adapter surface — caught by the first test run.
    client.list_voicemail_boxes = MagicMock(return_value={})
    client.list_inbound_routes = MagicMock(return_value=[])
    client.list_pickup_groups = MagicMock(return_value=[])
    client.list_ring_groups = MagicMock(return_value=[])

    return client


class TestFreePBXIdempotency(TestCase):
    """FreePBX source → Nautobot ORM round-trip produces zero diff on pass 2.

    Lighter than the CCM test — FreePBX semantics are simpler (one trunk
    per synthesized route group, no GFK heterogeneity) — but it still
    exercises every model class we emit + the new
    RouteGroupMember(target_kind='trunk') row.
    """

    def setUp(self) -> None:
        self.ps = models.PhoneSystem.objects.create(
            name="LAB-FREEPBX",
            vendor="freepbx",
            version="17.0.21",
            hostname="http://freepbx",
        )

    def _build_source(self, client: FreePBXClient) -> FreePBXSourceAdapter:
        source = FreePBXSourceAdapter(client=client, phone_system_record=self.ps)
        source.load()
        return source

    def _build_dest(self) -> PhonesNautobotAdapter:
        dest = PhonesNautobotAdapter(job=None, include_lines=False)
        dest.load()
        return dest

    def test_second_pass_zero_diff(self) -> None:
        client = _make_freepbx_client()

        source1 = self._build_source(client)
        dest1 = self._build_dest()
        dest1.sync_from(source1)

        # Sanity — the synthesized RouteGroupMember made it in.
        self.assertEqual(models.RouteGroupMember.objects.count(), 1,
                         "Expected 1 RouteGroupMember per synthesized RouteGroup")

        source2 = self._build_source(client)
        dest2 = self._build_dest()
        _assert_zero_diff(self, source2, dest2)
