"""Tests for ``dialplan_graph.build_graph()`` + the standalone view.

Two layers:

* **Builder** — pure-Python; verifies the right nodes/edges come out
  for both directions, the fanout-collapse triggers correctly, and
  bad/missing anchors produce an empty graph rather than raising.
* **View** — exercises the standalone page renders and the JSON
  endpoint returns the Cytoscape-shaped payload.
"""

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from nautobot.core.testing import TestCase

from nautobot_phones import models
from nautobot_phones.dialplan_graph import (
    PATTERN_FANOUT_LIMIT, build_graph,
)


class _GraphFixtureMixin:
    """Mid-sized fixture: one CSS with two partitions, mixed pattern
    kinds, and a route-list path to a trunk. Lets every code path
    in the builder exercise on the same setup."""

    def setUp(self):
        super().setUp()
        self.ps = models.PhoneSystem.objects.create(
            name="LAB-CCM", vendor="cisco_ucm",
            version="15.0", hostname="ccm.example.com",
        )
        self.css = models.CallingSearchSpace.objects.create(
            name="Internal-CSS", phone_system=self.ps,
        )
        self.partition_dn = models.Partition.objects.create(
            name="Internal-PT", phone_system=self.ps,
        )
        self.partition_pstn = models.Partition.objects.create(
            name="PSTN-PT", phone_system=self.ps,
        )
        models.CSSPartitionMembership.objects.create(
            css=self.css, partition=self.partition_dn, priority=1,
        )
        models.CSSPartitionMembership.objects.create(
            css=self.css, partition=self.partition_pstn, priority=2,
        )
        self.dn = models.DirectoryNumber.objects.create(
            extension="1001", partition=self.partition_dn,
            phone_system=self.ps, alerting_name="Alice",
        )
        # Trunk reachable via a RouteList → RouteGroup → this trunk.
        self.trunk = models.Trunk.objects.create(
            name="SIP-OUT", phone_system=self.ps, trunk_type="sip",
            destination_address="198.51.100.10",
        )
        self.route_list = models.RouteList.objects.create(
            name="NANP-RL", phone_system=self.ps,
        )
        self.route_group = models.RouteGroup.objects.create(
            name="ITSP-RG", phone_system=self.ps,
            distribution_algorithm="top_down",
        )
        models.RouteListMember.objects.create(
            route_list=self.route_list, route_group=self.route_group,
            priority=1,
        )
        ct = ContentType.objects.get_for_model(models.Trunk)
        models.RouteGroupMember.objects.create(
            route_group=self.route_group, target_type=ct,
            target_id=self.trunk.pk, priority=1,
        )
        # RoutePattern in PSTN-PT pointing at the route list.
        self.route_pattern = models.RoutePattern.objects.create(
            pattern="9.NXXNXXXXXX", partition=self.partition_pstn,
            target_route_list=self.route_list,
        )


# ---------------------------------------------------------------------------
# Builder — forward
# ---------------------------------------------------------------------------


class BuildGraphForwardTests(_GraphFixtureMixin, TestCase):
    """CSS-rooted graph contains every reachable destination."""

    def test_root_css_node_present(self):
        data = build_graph("css", str(self.css.pk), "forward")
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        self.assertIn(f"css:{self.css.pk}", node_ids)
        self.assertFalse(data["meta"]["empty"])
        self.assertEqual(data["meta"]["anchor_label"], "Internal-CSS")

    def test_both_partitions_emitted_in_priority_order(self):
        data = build_graph("css", str(self.css.pk), "forward")
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        self.assertIn(f"partition:{self.partition_dn.pk}", node_ids)
        self.assertIn(f"partition:{self.partition_pstn.pk}", node_ids)
        # Edges from CSS to partitions carry the priority label.
        css_partition_edges = [
            e["data"] for e in data["edges"]
            if e["data"]["source"] == f"css:{self.css.pk}"
            and e["data"]["kind"] == "css_priority"
        ]
        self.assertEqual(len(css_partition_edges), 2)
        labels = sorted(e["label"] for e in css_partition_edges)
        self.assertEqual(labels, ["priority 1", "priority 2"])

    def test_dn_in_partition_emits_dn_node(self):
        data = build_graph("css", str(self.css.pk), "forward")
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        self.assertIn(f"dn:{self.dn.pk}", node_ids)

    def test_route_pattern_emits_pattern_routelist_routegroup_trunk_chain(self):
        data = build_graph("css", str(self.css.pk), "forward")
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        # Whole chain present.
        self.assertIn(f"pattern:{self.route_pattern.pk}", node_ids)
        self.assertIn(f"route_list:{self.route_list.pk}", node_ids)
        self.assertIn(f"route_group:{self.route_group.pk}", node_ids)
        self.assertIn(f"trunk:{self.trunk.pk}", node_ids)
        # Connectivity: pattern → route_list, route_list → route_group,
        # route_group → trunk.
        edges = {(e["data"]["source"], e["data"]["target"]) for e in data["edges"]}
        self.assertIn((f"pattern:{self.route_pattern.pk}",
                       f"route_list:{self.route_list.pk}"), edges)
        self.assertIn((f"route_list:{self.route_list.pk}",
                       f"route_group:{self.route_group.pk}"), edges)
        self.assertIn((f"route_group:{self.route_group.pk}",
                       f"trunk:{self.trunk.pk}"), edges)

    def test_dns_aggregate_when_partition_has_many(self):
        """Partitions with > 1 DN emit a single supernode rather than
        one node per DN. Critical for canvas readability: a real
        partition might hold hundreds of DNs."""
        for i in range(15):
            models.DirectoryNumber.objects.create(
                extension=f"500{i:03d}", partition=self.partition_dn,
                phone_system=self.ps,
            )
        data = build_graph("css", str(self.css.pk), "forward")
        agg = [n for n in data["nodes"]
               if n["data"]["id"] == f"dn_agg:{self.partition_dn.pk}"]
        self.assertEqual(len(agg), 1)
        # 1 pre-existing + 15 new
        self.assertIn("16 DNs", agg[0]["data"]["label"])
        # Individual DN nodes for partition_dn should NOT appear when
        # aggregated. (The single original self.dn would have rendered
        # alone, but with 16 total we aggregate.)
        individual_dn_ids = [n["data"]["id"] for n in data["nodes"]
                             if n["data"]["id"].startswith("dn:")]
        self.assertEqual(individual_dn_ids, [],
                         "individual DN nodes should not appear when DNs are aggregated")

    def test_route_pattern_fanout_collapses_past_limit(self):
        """RoutePatterns DON'T aggregate (each is operationally distinct
        — different destinations) — they cap-and-collapse instead."""
        # 1 pre-existing RoutePattern in partition_pstn; add enough to
        # blow past the cap.
        for i in range(PATTERN_FANOUT_LIMIT + 2):
            models.RoutePattern.objects.create(
                pattern=f"8.{i}XX", partition=self.partition_pstn,
                target_trunk=self.trunk,
            )
        data = build_graph("css", str(self.css.pk), "forward")
        collapsed = [n for n in data["nodes"]
                     if n["data"]["id"] == f"rp_collapsed:{self.partition_pstn.pk}"]
        self.assertEqual(len(collapsed), 1)
        self.assertIn("RoutePatterns", collapsed[0]["data"]["label"])

    def test_translation_pattern_emits_node_without_recursing(self):
        models.TranslationPattern.objects.create(
            pattern="2XXX", partition=self.partition_dn,
            called_party_transformation_mask="555XXXX",
        )
        data = build_graph("css", str(self.css.pk), "forward")
        translations = [n for n in data["nodes"]
                        if n["data"]["kind"] == "translation"]
        self.assertEqual(len(translations), 1)
        self.assertIn("rewrites", translations[0]["data"]["summary"])

    def test_missing_anchor_returns_empty_meta(self):
        data = build_graph("css", "00000000-0000-0000-0000-000000000000", "forward")
        self.assertEqual(data["nodes"], [])
        self.assertEqual(data["edges"], [])
        self.assertTrue(data["meta"]["empty"])


# ---------------------------------------------------------------------------
# Builder — backward
# ---------------------------------------------------------------------------


class BuildGraphBackwardTests(_GraphFixtureMixin, TestCase):
    """Trunk-rooted graph walks back to every CSS that can reach it."""

    def test_root_trunk_node_present(self):
        data = build_graph("trunk", str(self.trunk.pk), "backward")
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        self.assertIn(f"trunk:{self.trunk.pk}", node_ids)
        self.assertEqual(data["meta"]["anchor_label"], "SIP-OUT")

    def test_walks_back_through_routelist_to_css(self):
        data = build_graph("trunk", str(self.trunk.pk), "backward")
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        # Full back-walk present.
        self.assertIn(f"route_group:{self.route_group.pk}", node_ids)
        self.assertIn(f"route_list:{self.route_list.pk}", node_ids)
        self.assertIn(f"pattern:{self.route_pattern.pk}", node_ids)
        self.assertIn(f"partition:{self.partition_pstn.pk}", node_ids)
        self.assertIn(f"css:{self.css.pk}", node_ids)

    def test_direct_pattern_trunk_path_also_traced(self):
        """A RoutePattern that points DIRECTLY at the trunk (no
        route-list) should also appear in the backward graph."""
        direct_rp = models.RoutePattern.objects.create(
            pattern="91.NXXNXXXXXX", partition=self.partition_dn,
            target_trunk=self.trunk,
        )
        data = build_graph("trunk", str(self.trunk.pk), "backward")
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        self.assertIn(f"pattern:{direct_rp.pk}", node_ids)
        # Partition holding the direct pattern is also visited.
        self.assertIn(f"partition:{self.partition_dn.pk}", node_ids)

    def test_missing_anchor_returns_empty_meta(self):
        data = build_graph("trunk", "00000000-0000-0000-0000-000000000000", "backward")
        self.assertEqual(data["nodes"], [])
        self.assertTrue(data["meta"]["empty"])


# ---------------------------------------------------------------------------
# Builder — defensive
# ---------------------------------------------------------------------------


class BuildGraphDefensiveTests(TestCase):
    """Unknown kind / direction inputs return empty rather than 500."""

    def test_unknown_direction_treated_as_empty(self):
        data = build_graph("css", "anything", "sideways")
        self.assertEqual(data["nodes"], [])
        self.assertTrue(data["meta"]["empty"])

    def test_unknown_anchor_kind_returns_empty(self):
        data = build_graph("widget", "x", "forward")
        self.assertEqual(data["nodes"], [])
        self.assertTrue(data["meta"]["empty"])


# ---------------------------------------------------------------------------
# View — standalone page + JSON endpoint
# ---------------------------------------------------------------------------


class DialPlanGraphViewTests(_GraphFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.client.defaults["SERVER_NAME"] = "localhost"
        self.page_url = reverse("plugins:nautobot_phones:dialplan_graph")
        self.data_url = reverse("plugins:nautobot_phones:dialplan_graph_data")

    def test_page_renders(self):
        resp = self.client.get(self.page_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Dial-plan graph")
        # Anchor select + direction buttons render.
        self.assertContains(resp, "dpg-anchor")
        self.assertContains(resp, "Forward")
        self.assertContains(resp, "Backward")

    def test_page_with_initial_anchor_query_string(self):
        resp = self.client.get(self.page_url, {
            "anchor": f"css:{self.css.pk}",
            "direction": "forward",
        })
        self.assertEqual(resp.status_code, 200)
        # Initial anchor appears as a selected option.
        self.assertContains(resp, f"css:{self.css.pk}")

    def test_data_endpoint_forward(self):
        resp = self.client.get(self.data_url, {
            "anchor": f"css:{self.css.pk}",
            "direction": "forward",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["meta"]["empty"])
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        self.assertIn(f"css:{self.css.pk}", node_ids)
        self.assertIn(f"partition:{self.partition_dn.pk}", node_ids)

    def test_data_endpoint_backward(self):
        resp = self.client.get(self.data_url, {
            "anchor": f"trunk:{self.trunk.pk}",
            "direction": "backward",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["meta"]["empty"])
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        self.assertIn(f"trunk:{self.trunk.pk}", node_ids)
        self.assertIn(f"css:{self.css.pk}", node_ids)

    def test_data_endpoint_bad_anchor(self):
        resp = self.client.get(self.data_url, {
            "anchor": "garbage",
            "direction": "forward",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["meta"]["empty"])


# ---------------------------------------------------------------------------
# Trace overlay — bridges dialplan.trace() + build_graph()
# ---------------------------------------------------------------------------


class TraceStepToNodeIdTests(TestCase):
    """Pure-function mapping from TraceStep → graph node id."""

    def _step(self, kind, url):
        from nautobot_phones.dialplan import TraceStep
        return TraceStep(kind=kind, summary="x", subject="y", detail_url=url)

    def test_css_step_maps_to_css_node(self):
        from nautobot_phones.dialplan_graph import trace_step_to_node_id
        nid = trace_step_to_node_id(self._step(
            "css", "/plugins/phones/calling-search-spaces/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/"
        ))
        self.assertEqual(nid, "css:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    def test_partition_check_maps_to_partition_node(self):
        from nautobot_phones.dialplan_graph import trace_step_to_node_id
        nid = trace_step_to_node_id(self._step(
            "partition_check", "/plugins/phones/partitions/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/"
        ))
        self.assertEqual(nid, "partition:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    def test_route_pattern_maps_to_pattern_node(self):
        from nautobot_phones.dialplan_graph import trace_step_to_node_id
        nid = trace_step_to_node_id(self._step(
            "route_pattern_match", "/plugins/phones/route-patterns/cccccccc-cccc-cccc-cccc-cccccccccccc/"
        ))
        self.assertEqual(nid, "pattern:cccccccc-cccc-cccc-cccc-cccccccccccc")

    def test_no_match_step_returns_none(self):
        from nautobot_phones.dialplan_graph import trace_step_to_node_id
        nid = trace_step_to_node_id(self._step("no_match", ""))
        self.assertIsNone(nid)

    def test_likely_egress_derives_prefix_from_url(self):
        """The 'likely_egress' kind can resolve to either a trunk or a
        route_list depending on whether the list had members. Derive
        from URL slug, not from a static map."""
        from nautobot_phones.dialplan_graph import trace_step_to_node_id
        # Empty route-list → likely_egress points at the route_list.
        nid = trace_step_to_node_id(self._step(
            "likely_egress", "/plugins/phones/route-lists/dddddddd-dddd-dddd-dddd-dddddddddddd/"
        ))
        self.assertEqual(nid, "route_list:dddddddd-dddd-dddd-dddd-dddddddddddd")
        # Populated → likely_egress points at the trunk.
        nid = trace_step_to_node_id(self._step(
            "likely_egress", "/plugins/phones/trunks/eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee/"
        ))
        self.assertEqual(nid, "trunk:eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

    def test_url_without_uuid_returns_none(self):
        from nautobot_phones.dialplan_graph import trace_step_to_node_id
        nid = trace_step_to_node_id(self._step("css", "/plugins/phones/calling-search-spaces/"))
        self.assertIsNone(nid)


class BuildGraphWithTraceTests(_GraphFixtureMixin, TestCase):
    """build_graph + trace_steps round-trip: matching nodes get
    ``step_index`` annotations and the meta carries the step list."""

    def setUp(self):
        super().setUp()
        # Bump existing partition memberships' priorities first to make
        # room for a top-priority 911CER-PT (unique_together(css,
        # priority) prevents two rows colliding at the same priority).
        m1 = models.CSSPartitionMembership.objects.get(
            css=self.css, partition=self.partition_dn,
        )
        m1.priority = 3
        m1.save()
        m2 = models.CSSPartitionMembership.objects.get(
            css=self.css, partition=self.partition_pstn,
        )
        m2.priority = 4
        m2.save()
        # Add a 911 DN at the top of the priority list so the trace
        # from Internal-CSS for "911" actually lands on it.
        self.cer_pt = models.Partition.objects.create(
            name="911CER-PT", phone_system=self.ps,
        )
        models.CSSPartitionMembership.objects.create(
            css=self.css, partition=self.cer_pt, priority=1,
        )
        self.dn_911 = models.DirectoryNumber.objects.create(
            extension="911", partition=self.cer_pt, phone_system=self.ps,
        )

    def _trace(self, digits):
        from nautobot_phones import dialplan as dp_engine
        return dp_engine.trace(
            phone_system=self.ps,
            starting_css=self.css,
            dialed_digits=digits,
        )

    def test_trace_annotates_nodes_with_step_index(self):
        from nautobot_phones.dialplan_graph import build_graph
        steps = self._trace("911")
        data = build_graph("css", str(self.css.pk), "forward",
                           trace_steps=steps)
        # CSS node = step 0
        css_node = next(n for n in data["nodes"]
                        if n["data"]["id"] == f"css:{self.css.pk}")
        self.assertEqual(css_node["data"].get("step_index"), 0)
        # The 911CER-PT partition + the DN should be present and
        # annotated (their step_index depends on partition priority
        # walking; we just verify they're > 0).
        cer_node = next((n for n in data["nodes"]
                         if n["data"]["id"] == f"partition:{self.cer_pt.pk}"), None)
        self.assertIsNotNone(cer_node)
        self.assertIn("step_index", cer_node["data"])
        dn_node = next((n for n in data["nodes"]
                        if n["data"]["id"] == f"dn:{self.dn_911.pk}"), None)
        self.assertIsNotNone(dn_node)
        self.assertIn("step_index", dn_node["data"])

    def test_meta_carries_serialized_trace_steps(self):
        from nautobot_phones.dialplan_graph import build_graph
        steps = self._trace("911")
        data = build_graph("css", str(self.css.pk), "forward",
                           trace_steps=steps)
        self.assertTrue(data["meta"]["has_trace"])
        payload = data["meta"]["trace_steps"]
        self.assertEqual(len(payload), len(steps))
        # First step is the CSS — must be the same kind + carry the
        # resolved node_id for the JS to use.
        self.assertEqual(payload[0]["kind"], "css")
        self.assertEqual(payload[0]["node_id"], f"css:{self.css.pk}")

    def test_no_trace_no_annotation(self):
        """When trace_steps is None, the graph is identical to the
        plain topology (no step_index keys, has_trace=False)."""
        from nautobot_phones.dialplan_graph import build_graph
        data = build_graph("css", str(self.css.pk), "forward")
        self.assertFalse(data["meta"]["has_trace"])
        for n in data["nodes"]:
            self.assertNotIn("step_index", n["data"])

    def test_trace_unaggregates_touched_dn_when_other_dns_exist(self):
        """If the trace lands on a DN inside a partition with many DNs,
        the touched DN must render INDIVIDUALLY (so the highlight
        works) even though siblings would normally aggregate."""
        from nautobot_phones.dialplan_graph import build_graph
        # Stuff the 911CER partition with extra non-911 DNs so it would
        # otherwise aggregate.
        for ext in ("9001", "9002", "9003", "9004", "9005"):
            models.DirectoryNumber.objects.create(
                extension=ext, partition=self.cer_pt, phone_system=self.ps,
            )
        steps = self._trace("911")
        data = build_graph("css", str(self.css.pk), "forward",
                           trace_steps=steps)
        node_ids = {n["data"]["id"] for n in data["nodes"]}
        # The 911 DN itself MUST appear individually.
        self.assertIn(f"dn:{self.dn_911.pk}", node_ids,
                      "trace-touched DN should not be aggregated away")
        # Other 5 DNs still get an aggregate.
        agg = [n for n in data["nodes"]
               if n["data"]["id"] == f"dn_agg:{self.cer_pt.pk}"]
        self.assertEqual(len(agg), 1)
        self.assertIn("5 other", agg[0]["data"]["label"])


class DialPlanGraphDataViewTraceTests(_GraphFixtureMixin, TestCase):
    """The JSON endpoint accepts dialed_digits and overlays the trace."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.client.defaults["SERVER_NAME"] = "localhost"
        self.data_url = reverse("plugins:nautobot_phones:dialplan_graph_data")

    def test_dialed_digits_runs_trace_and_overlays(self):
        # 1001 is the DN in Internal-PT (from the fixture).
        resp = self.client.get(self.data_url, {
            "anchor": f"css:{self.css.pk}",
            "direction": "forward",
            "dialed_digits": "1001",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["meta"]["has_trace"])
        self.assertGreaterEqual(len(data["meta"]["trace_steps"]), 1)

    def test_no_dialed_digits_no_overlay(self):
        resp = self.client.get(self.data_url, {
            "anchor": f"css:{self.css.pk}",
            "direction": "forward",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["meta"]["has_trace"])

    def test_backward_with_dialed_uses_trunks_inbound_css(self):
        """Backward + dialed_digits on a trunk with inbound_css set —
        the trace runs from the inbound CSS, not from the trunk itself."""
        # Set the trunk's inbound CSS.
        self.trunk.inbound_css = self.css
        self.trunk.save()
        resp = self.client.get(self.data_url, {
            "anchor": f"trunk:{self.trunk.pk}",
            "direction": "backward",
            "dialed_digits": "1001",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["meta"]["has_trace"])

    def test_backward_with_no_inbound_css_degrades_gracefully(self):
        """If the trunk has no inbound_css, trace can't run — graph
        should still render, just without overlay."""
        # self.trunk.inbound_css is unset by default.
        resp = self.client.get(self.data_url, {
            "anchor": f"trunk:{self.trunk.pk}",
            "direction": "backward",
            "dialed_digits": "1001",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["meta"]["empty"])  # graph still renders
        self.assertFalse(data["meta"]["has_trace"])  # no overlay
