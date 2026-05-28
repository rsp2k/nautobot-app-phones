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
