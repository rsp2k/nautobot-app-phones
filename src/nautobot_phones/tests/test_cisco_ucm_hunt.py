"""Tests for the CCM ``_load_hunt_subsystem`` three-phase loader.

The hunt subsystem in CCM has three first-class records and two
through-tables, evaluated in this order at call time:

  HuntPilot (dial pattern)
    → HuntList (priority list of LineGroups)
      → LineGroup (DNs with a distribution algorithm)

The loader walks this in reverse — leaf-first — so DiffSync identifier
resolution works (each phase's records depend on the prior phase's
identifiers existing in the in-memory store).

Mocking strategy: the same ``client._list(method, model, ...)`` helper
is invoked three times with different list-method names, so we
dispatch the mock's behavior by the first positional argument.
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


def _make_client_with_hunt_data(
    *,
    line_groups: list[dict] | None = None,
    hunt_lists: list[dict] | None = None,
    hunt_pilots: list[dict] | None = None,
    get_line_group: Any = None,
    get_hunt_list: Any = None,
) -> Any:
    """Build a client mock that dispatches ``_list`` on the first arg.

    Each phase calls ``client._list(method_name, ...)``; we route each
    method name to the matching list of rows. Everything else returns
    empty.
    """
    client = MagicMock()
    for name in (
        "list_route_lists", "list_route_groups", "list_route_partitions",
        "list_css", "list_lines", "list_phones", "list_sip_trunks",
        "list_route_patterns", "list_translation_patterns", "list_gateways",
    ):
        setattr(client, name, MagicMock(return_value=[]))

    routes = {
        "listLineGroup": line_groups or [],
        "listHuntList": hunt_lists or [],
        "listHuntPilot": hunt_pilots or [],
    }

    def _list_dispatcher(method_name: str, *args: Any, **kwargs: Any) -> list:
        return routes.get(method_name, [])

    client._list = MagicMock(side_effect=_list_dispatcher)

    client._service = MagicMock()
    # Per-record enrichment defaults — empty.
    for name in (
        "getRouteList", "getRouteGroup", "getHuntList", "getLineGroup",
        "getGateway", "getDevicePool", "getVoiceMailProfile",
        "getCallPickupGroup", "getRoutePattern", "getCss",
    ):
        setattr(client._service, name, MagicMock(return_value={"return": {}}))
    # Override the ones the test specifically wants.
    if get_line_group is not None:
        client._service.getLineGroup = MagicMock(return_value=get_line_group)
    if get_hunt_list is not None:
        client._service.getHuntList = MagicMock(return_value=get_hunt_list)

    # listX (via _service) used by other loaders — empty so they don't pollute.
    for name in ("listDevicePool", "listVoiceMailProfile",
                 "listCallPickupGroup", "listLine"):
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


def _line_group_with_members(name: str, members: list[dict]) -> dict:
    """Build a getLineGroup-shaped response with the given members."""
    return {"return": {"lineGroup": {
        "name": name,
        "members": {"member": members},
    }}}


def _hunt_list_with_members(name: str, members: list[dict]) -> dict:
    return {"return": {"huntList": {
        "name": name,
        "members": {"member": members},
    }}}


# ---------------------------------------------------------------------------
# Phase 1 — LineGroup + LineGroupMember
# ---------------------------------------------------------------------------


class TestLoadLineGroups(SimpleTestCase):
    """LineGroups: scalar metadata + per-record getLineGroup enrichment for members."""

    def test_emits_line_group_with_algorithm(self) -> None:
        client = _make_client_with_hunt_data(
            line_groups=[{
                "name": "Helpdesk-LG",
                "distributionAlgorithm": "Top Down",
                "rnaReversionTimeOut": "20",
                "huntAlgorithmNoAnswer": "Try next member; then, try next group in Hunt List",
                "huntAlgorithmBusy": "Try next member; then, try next group in Hunt List",
                "huntAlgorithmNotAvailable": "Try next member; then, try next group in Hunt List",
                "autoLogOffHunt": "false",
            }],
        )
        adapter = _run(client)
        lg = next(iter(adapter.get_all("line_group")))
        self.assertEqual(lg.name, "Helpdesk-LG")
        self.assertEqual(lg.distribution_algorithm, "Top Down")
        self.assertEqual(lg.rna_reversion_timeout, 20)
        self.assertFalse(lg.auto_log_off_hunt)
        self.assertIn("Try next member", lg.hunt_algorithm_no_answer)

    def test_blank_name_skipped(self) -> None:
        client = _make_client_with_hunt_data(
            line_groups=[{"name": ""}, {"name": "Valid"}],
        )
        adapter = _run(client)
        names = [lg.name for lg in adapter.get_all("line_group")]
        self.assertEqual(names, ["Valid"])

    def test_blank_rna_reversion_timeout_becomes_none(self) -> None:
        """Blank or missing rnaReversionTimeOut → None (not 0)."""
        client = _make_client_with_hunt_data(
            line_groups=[{"name": "LG1", "rnaReversionTimeOut": ""}],
        )
        adapter = _run(client)
        lg = next(iter(adapter.get_all("line_group")))
        self.assertIsNone(lg.rna_reversion_timeout)

    def test_invalid_rna_reversion_timeout_becomes_none(self) -> None:
        """Non-numeric rnaReversionTimeOut → None rather than crashing."""
        client = _make_client_with_hunt_data(
            line_groups=[{"name": "LG1", "rnaReversionTimeOut": "garbage"}],
        )
        adapter = _run(client)
        lg = next(iter(adapter.get_all("line_group")))
        self.assertIsNone(lg.rna_reversion_timeout)


class TestLineGroupMembers(SimpleTestCase):
    """getLineGroup-derived through-table: DN members with line_selection_order."""

    def _client_with_lg_members(self, members: list[dict]) -> Any:
        return _make_client_with_hunt_data(
            line_groups=[{"name": "Helpdesk-LG"}],
            get_line_group=_line_group_with_members("Helpdesk-LG", members),
        )

    def test_emits_one_member_per_dn(self) -> None:
        adapter = _run(self._client_with_lg_members([
            {"directoryNumber": {"pattern": "1001",
                                  "routePartitionName": {"_value_1": "Internal-PT"}},
             "lineSelectionOrder": 1},
            {"directoryNumber": {"pattern": "1002",
                                  "routePartitionName": {"_value_1": "Internal-PT"}},
             "lineSelectionOrder": 2},
        ]))
        members = sorted(adapter.get_all("line_group_member"),
                         key=lambda m: m.line_selection_order)
        self.assertEqual([(m.directory_number__extension, m.line_selection_order)
                          for m in members],
                         [("1001", 1), ("1002", 2)])

    def test_member_without_dn_pattern_skipped(self) -> None:
        """Member with missing pattern can't reference a DN — silently skipped
        rather than emitting a broken FK row."""
        adapter = _run(self._client_with_lg_members([
            {"directoryNumber": {"pattern": "", "routePartitionName": None},
             "lineSelectionOrder": 1},
            {"directoryNumber": {"pattern": "1003",
                                  "routePartitionName": {"_value_1": "Internal-PT"}},
             "lineSelectionOrder": 2},
        ]))
        members = list(adapter.get_all("line_group_member"))
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].directory_number__extension, "1003")

    def test_member_without_partition_falls_back_to_null_placeholder(self) -> None:
        """A member's DN with no partition resolves to the synthetic NULL
        placeholder (same convention as inline-line emission)."""
        adapter = _run(self._client_with_lg_members([
            {"directoryNumber": {"pattern": "1001", "routePartitionName": None},
             "lineSelectionOrder": 1},
        ]))
        m = next(iter(adapter.get_all("line_group_member")))
        # NULL_PARTITION_NAME placeholder kicks in when partition is unset.
        self.assertTrue(m.directory_number__partition__name)

    def test_non_int_selection_order_defaults_to_0(self) -> None:
        adapter = _run(self._client_with_lg_members([
            {"directoryNumber": {"pattern": "1001",
                                  "routePartitionName": {"_value_1": "Internal-PT"}},
             "lineSelectionOrder": "garbage"},
        ]))
        m = next(iter(adapter.get_all("line_group_member")))
        self.assertEqual(m.line_selection_order, 0)

    def test_blank_selection_order_defaults_to_0(self) -> None:
        adapter = _run(self._client_with_lg_members([
            {"directoryNumber": {"pattern": "1001",
                                  "routePartitionName": {"_value_1": "Internal-PT"}},
             "lineSelectionOrder": ""},
        ]))
        m = next(iter(adapter.get_all("line_group_member")))
        self.assertEqual(m.line_selection_order, 0)

    def test_scalar_member_normalized_to_list(self) -> None:
        """zeep quirk: single-element member array as scalar instead of list."""
        client = _make_client_with_hunt_data(
            line_groups=[{"name": "Helpdesk-LG"}],
            get_line_group={"return": {"lineGroup": {
                "name": "Helpdesk-LG",
                "members": {"member": {  # scalar, not list
                    "directoryNumber": {"pattern": "1001",
                                         "routePartitionName": {"_value_1": "Internal-PT"}},
                    "lineSelectionOrder": 1,
                }},
            }}},
        )
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("line_group_member"))), 1)

    def test_getlinegroup_failure_keeps_group_drops_members(self) -> None:
        """A failed getLineGroup leaves the LineGroup record but emits no
        members — same pattern as RouteList, HuntList, etc."""
        client = _make_client_with_hunt_data(
            line_groups=[{"name": "Helpdesk-LG"}],
        )
        client._service.getLineGroup = MagicMock(side_effect=Exception("AXL down"))
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("line_group"))), 1)
        self.assertEqual(len(list(adapter.get_all("line_group_member"))), 0)


# ---------------------------------------------------------------------------
# Phase 2 — HuntList + HuntListMember
# ---------------------------------------------------------------------------


class TestLoadHuntLists(SimpleTestCase):
    """HuntLists: scalar metadata + per-record getHuntList enrichment for members."""

    def test_emits_hunt_list_with_cmg_in_vendor_extras(self) -> None:
        """callManagerGroup is CCM-only — stored in vendor_extras (not a
        first-class column) per the vendor-agnostic schema discipline."""
        client = _make_client_with_hunt_data(
            hunt_lists=[{
                "name": "Helpdesk-HL",
                "description": "Helpdesk hunt list",
                "callManagerGroupName": {"_value_1": "Default-CMG"},
                "routeListEnabled": "true",
                "voiceMailUsage": "false",
            }],
        )
        adapter = _run(client)
        hl = next(iter(adapter.get_all("hunt_list")))
        self.assertEqual(hl.name, "Helpdesk-HL")
        self.assertEqual(hl.description, "Helpdesk hunt list")
        self.assertTrue(hl.route_list_enabled)
        self.assertFalse(hl.voice_mail_usage)
        # CCM-only CMG ref lives in vendor_extras.
        self.assertEqual(hl.vendor_extras["callManagerGroupName"], "Default-CMG")

    def test_missing_cmg_omitted_from_extras(self) -> None:
        """No callManagerGroupName → key absent from vendor_extras (no
        ``None`` placeholder polluting the dict)."""
        client = _make_client_with_hunt_data(
            hunt_lists=[{"name": "HL1", "callManagerGroupName": None}],
        )
        adapter = _run(client)
        hl = next(iter(adapter.get_all("hunt_list")))
        self.assertNotIn("callManagerGroupName", hl.vendor_extras)

    def test_blank_name_skipped(self) -> None:
        client = _make_client_with_hunt_data(
            hunt_lists=[{"name": ""}, {"name": "Valid"}],
        )
        adapter = _run(client)
        names = [hl.name for hl in adapter.get_all("hunt_list")]
        self.assertEqual(names, ["Valid"])


class TestHuntListMembers(SimpleTestCase):
    """getHuntList-derived through-table: LineGroup members with selection_order."""

    def _client_with_hl_members(self, members: list[dict]) -> Any:
        return _make_client_with_hunt_data(
            hunt_lists=[{"name": "Helpdesk-HL"}],
            get_hunt_list=_hunt_list_with_members("Helpdesk-HL", members),
        )

    def test_emits_one_member_per_line_group(self) -> None:
        adapter = _run(self._client_with_hl_members([
            {"lineGroupName": {"_value_1": "Primary-LG"}, "selectionOrder": 1},
            {"lineGroupName": {"_value_1": "Backup-LG"}, "selectionOrder": 2},
        ]))
        members = sorted(adapter.get_all("hunt_list_member"),
                         key=lambda m: m.selection_order)
        self.assertEqual(
            [(m.line_group__name, m.selection_order) for m in members],
            [("Primary-LG", 1), ("Backup-LG", 2)],
        )

    def test_member_without_line_group_name_skipped(self) -> None:
        """Empty lineGroupName ref → skipped (no broken FK row)."""
        adapter = _run(self._client_with_hl_members([
            {"lineGroupName": {"_value_1": ""}, "selectionOrder": 1},
            {"lineGroupName": {"_value_1": "Valid-LG"}, "selectionOrder": 2},
        ]))
        members = list(adapter.get_all("hunt_list_member"))
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].line_group__name, "Valid-LG")

    def test_null_line_group_ref_skipped(self) -> None:
        """``lineGroupName=None`` (rare zeep edge case) silently skipped."""
        adapter = _run(self._client_with_hl_members([
            {"lineGroupName": None, "selectionOrder": 1},
            {"lineGroupName": {"_value_1": "LG-OK"}, "selectionOrder": 2},
        ]))
        members = list(adapter.get_all("hunt_list_member"))
        self.assertEqual(len(members), 1)

    def test_non_int_selection_order_defaults_to_1(self) -> None:
        """HuntListMember default is 1 (vs 0 for LineGroupMember).
        Different defaults are intentional: HuntList priority starts
        at 1 in the CCM UI; LineGroup line selection is 0-indexed."""
        adapter = _run(self._client_with_hl_members([
            {"lineGroupName": {"_value_1": "LG1"}, "selectionOrder": "garbage"},
        ]))
        m = next(iter(adapter.get_all("hunt_list_member")))
        self.assertEqual(m.selection_order, 1)

    def test_scalar_member_normalized_to_list(self) -> None:
        client = _make_client_with_hunt_data(
            hunt_lists=[{"name": "Helpdesk-HL"}],
            get_hunt_list={"return": {"huntList": {
                "name": "Helpdesk-HL",
                "members": {"member": {  # scalar
                    "lineGroupName": {"_value_1": "Lonely-LG"},
                    "selectionOrder": 1,
                }},
            }}},
        )
        adapter = _run(client)
        members = list(adapter.get_all("hunt_list_member"))
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].line_group__name, "Lonely-LG")

    def test_gethuntlist_failure_keeps_list_drops_members(self) -> None:
        client = _make_client_with_hunt_data(
            hunt_lists=[{"name": "Helpdesk-HL"}],
        )
        client._service.getHuntList = MagicMock(side_effect=Exception("AXL down"))
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("hunt_list"))), 1)
        self.assertEqual(len(list(adapter.get_all("hunt_list_member"))), 0)


# ---------------------------------------------------------------------------
# Phase 3 — HuntPilot (single-pass, no enrichment)
# ---------------------------------------------------------------------------


class TestLoadHuntPilots(SimpleTestCase):
    """HuntPilots: dial pattern → HuntList, single-pass."""

    def test_emits_hunt_pilot_with_full_metadata(self) -> None:
        client = _make_client_with_hunt_data(
            hunt_pilots=[{
                "pattern": "5550100",
                "description": "Helpdesk pilot",
                "routePartitionName": {"_value_1": "Internal-PT"},
                "huntListName": {"_value_1": "Helpdesk-HL"},
                "alertingName": "Helpdesk",
                "maxHuntduration": "60",
            }],
        )
        adapter = _run(client)
        hp = next(iter(adapter.get_all("hunt_pilot")))
        self.assertEqual(hp.pattern, "5550100")
        self.assertEqual(hp.description, "Helpdesk pilot")
        self.assertEqual(hp.partition__name, "Internal-PT")
        self.assertEqual(hp.hunt_list__name, "Helpdesk-HL")
        self.assertEqual(hp.alerting_name, "Helpdesk")
        self.assertEqual(hp.max_hunt_duration, 60)
        # The long-tail forward-hunt destination fields default to empty
        # — the loader defers their extraction (would need getHuntPilot
        # enrichment to walk the nested objects).
        self.assertEqual(hp.forward_hunt_no_answer_destination, "")
        self.assertEqual(hp.forward_hunt_busy_destination, "")

    def test_blank_pattern_skipped(self) -> None:
        client = _make_client_with_hunt_data(
            hunt_pilots=[{"pattern": ""}, {"pattern": "5550100"}],
        )
        adapter = _run(client)
        patterns = [hp.pattern for hp in adapter.get_all("hunt_pilot")]
        self.assertEqual(patterns, ["5550100"])

    def test_missing_partition_resolves_to_null_placeholder(self) -> None:
        """No partition ref → ``_resolve_partition`` returns the synthetic
        NULL_PARTITION_NAME so the FK chain has something concrete."""
        client = _make_client_with_hunt_data(
            hunt_pilots=[{"pattern": "5550100",
                          "routePartitionName": None,
                          "huntListName": {"_value_1": "HL1"}}],
        )
        adapter = _run(client)
        hp = next(iter(adapter.get_all("hunt_pilot")))
        # NULL placeholder kicks in.
        self.assertTrue(hp.partition__name)

    def test_blank_max_hunt_duration_becomes_none(self) -> None:
        client = _make_client_with_hunt_data(
            hunt_pilots=[{"pattern": "5550100",
                          "maxHuntduration": "",
                          "routePartitionName": {"_value_1": "Internal-PT"}}],
        )
        adapter = _run(client)
        hp = next(iter(adapter.get_all("hunt_pilot")))
        self.assertIsNone(hp.max_hunt_duration)

    def test_invalid_max_hunt_duration_becomes_none(self) -> None:
        client = _make_client_with_hunt_data(
            hunt_pilots=[{"pattern": "5550100",
                          "maxHuntduration": "garbage",
                          "routePartitionName": {"_value_1": "Internal-PT"}}],
        )
        adapter = _run(client)
        hp = next(iter(adapter.get_all("hunt_pilot")))
        self.assertIsNone(hp.max_hunt_duration)

    def test_missing_hunt_list_ref_yields_none(self) -> None:
        """No huntListName → hunt_list__name is None (loosely-bound pilot,
        e.g. forwarding-only or block patterns)."""
        client = _make_client_with_hunt_data(
            hunt_pilots=[{"pattern": "5550100",
                          "huntListName": None,
                          "routePartitionName": {"_value_1": "Internal-PT"}}],
        )
        adapter = _run(client)
        hp = next(iter(adapter.get_all("hunt_pilot")))
        self.assertIsNone(hp.hunt_list__name)


# ---------------------------------------------------------------------------
# End-to-end — all three phases working together
# ---------------------------------------------------------------------------


class TestHuntSubsystemFullChain(SimpleTestCase):
    """End-to-end: all three phases load + reference each other by natural key."""

    def test_full_chain_emits_all_record_kinds(self) -> None:
        """Realistic small cluster: 1 HuntPilot → 1 HuntList → 2 LineGroups
        (Primary, Backup), each with 2 DN members. Verifies the full
        three-phase load fires in order and all reference chains resolve."""
        client = _make_client_with_hunt_data(
            line_groups=[
                {"name": "Primary-LG", "distributionAlgorithm": "Top Down"},
                {"name": "Backup-LG", "distributionAlgorithm": "Top Down"},
            ],
            hunt_lists=[{"name": "Helpdesk-HL"}],
            hunt_pilots=[{
                "pattern": "5550100",
                "routePartitionName": {"_value_1": "Internal-PT"},
                "huntListName": {"_value_1": "Helpdesk-HL"},
                "alertingName": "Helpdesk",
            }],
        )
        # Multi-arg getLineGroup — return different members per name.
        def fake_get_line_group(name: str, **_kwargs) -> dict:
            return {"return": {"lineGroup": {
                "name": name,
                "members": {"member": [
                    {"directoryNumber": {"pattern": f"{name[:1]}001",
                                          "routePartitionName": {"_value_1": "Internal-PT"}},
                     "lineSelectionOrder": 1},
                    {"directoryNumber": {"pattern": f"{name[:1]}002",
                                          "routePartitionName": {"_value_1": "Internal-PT"}},
                     "lineSelectionOrder": 2},
                ]},
            }}}

        client._service.getLineGroup = MagicMock(side_effect=fake_get_line_group)
        client._service.getHuntList = MagicMock(return_value=_hunt_list_with_members(
            "Helpdesk-HL", [
                {"lineGroupName": {"_value_1": "Primary-LG"}, "selectionOrder": 1},
                {"lineGroupName": {"_value_1": "Backup-LG"}, "selectionOrder": 2},
            ],
        ))
        adapter = _run(client)
        # 2 LineGroups, 4 LineGroupMembers (2 per group), 1 HuntList,
        # 2 HuntListMembers, 1 HuntPilot — all wired up by natural key.
        self.assertEqual(len(list(adapter.get_all("line_group"))), 2)
        self.assertEqual(len(list(adapter.get_all("line_group_member"))), 4)
        self.assertEqual(len(list(adapter.get_all("hunt_list"))), 1)
        self.assertEqual(len(list(adapter.get_all("hunt_list_member"))), 2)
        self.assertEqual(len(list(adapter.get_all("hunt_pilot"))), 1)

        # Spot-check one of each kind for cross-phase integrity.
        hp = next(iter(adapter.get_all("hunt_pilot")))
        self.assertEqual(hp.hunt_list__name, "Helpdesk-HL")
        hlm = next(iter(m for m in adapter.get_all("hunt_list_member")
                        if m.selection_order == 1))
        self.assertEqual(hlm.line_group__name, "Primary-LG")
