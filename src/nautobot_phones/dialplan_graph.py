"""Dial-plan graph builder — walks the synced data to emit Cytoscape JSON.

Where ``dialplan.trace()`` answers "what happens for this one call?"
in a linear step list, this module answers "what is the *shape* of
the dial plan around this anchor?" as a graph. Operators use it to
spot capacity, coverage, and unintended-reachability issues that a
single-call trace can't surface.

Two directions supported:

* **Forward** — root = CSS; walk → partitions → patterns →
  destinations (DN, RouteList, Trunk, HuntPilot). Answers "what can
  this CSS reach?"
* **Backward** — root = Trunk; walk → RouteGroup memberships →
  RouteLists → RoutePatterns → Partitions → CSSes. Answers "who can
  use this trunk?" (plus a thinner branch for the rare RoutePatterns
  that point directly at the trunk without a RouteList in between).

Output is Cytoscape's standard data shape — `{nodes, edges}` with
per-element `data` dicts. Each node carries `kind`, `label`,
`detail_url`, and any annotation the renderer wants to style on. No
DOM / layout decisions live here — that's the template's job.

We deliberately do NOT explode pattern lists at full depth. A
partition with 50 patterns becomes one "+ N patterns" supernode
unless the operator drills in; otherwise even a single CSS view
overflows the screen for real LAB-CCM data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from nautobot_phones import models


# UUID regex — matches the standard hex+dash form Nautobot uses everywhere.
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)

# Maps TraceStep.kind → graph node-id prefix. Steps with kind not in this
# map are terminal/non-mappable (no_match, recursion_limit) — they don't
# correspond to a specific graph node so we skip them when overlaying.
_STEP_KIND_TO_NODE_PREFIX = {
    "css": "css",
    "partition_check": "partition",
    "dn_match": "dn",
    "route_pattern_match": "pattern",
    "translation_match": "translation",
    "hunt_pilot_match": "hunt_pilot",
    "hunt_subsystem": "hunt_list",      # closest graph node for hunt expansion
    "trunk_egress": "trunk",
    "route_list_egress": "route_list",
    "route_group_select": "route_group",
    # likely_egress is special: it can resolve to either a trunk or a
    # route_list depending on whether the list had any members. We pick
    # the prefix by inspecting the detail_url path slug — handled in
    # _trace_step_to_node_id() below rather than via this static map.
}


def trace_step_to_node_id(step) -> Optional[str]:
    """Map a TraceStep to the matching graph-node id, or None if the
    step doesn't correspond to a single node (terminal kinds, etc.).

    Works by combining a kind-derived prefix with the UUID extracted
    from the step's ``detail_url``. Keeps the trace and graph layers
    decoupled — the trace doesn't need to know about graph ids, and
    the graph doesn't need to call back into the trace engine.
    """
    if step.kind in ("no_match", "recursion_limit"):
        return None
    prefix = _STEP_KIND_TO_NODE_PREFIX.get(step.kind)
    if prefix is None:
        # likely_egress — derive from URL slug.
        if step.kind == "likely_egress":
            if "/trunks/" in step.detail_url:
                prefix = "trunk"
            elif "/route-lists/" in step.detail_url:
                prefix = "route_list"
            else:
                return None
        else:
            return None
    match = _UUID_RE.search(step.detail_url or "")
    if not match:
        return None
    return f"{prefix}:{match.group(0).lower()}"


PATTERN_FANOUT_LIMIT = 8
"""When a partition (or other parent) would emit more than this many
pattern leaf nodes, collapse the tail into a single "+ N more"
supernode. Operators can navigate to the partition's list view to see
the full set. The cap balances "see the shape at a glance" against
"the canvas turns into spaghetti past ~100 nodes per CSS."""


@dataclass
class GraphNode:
    """One Cytoscape node. ``kind`` controls color/icon in the
    renderer; ``label`` is what shows on the node; ``detail_url`` is
    the click-through target (empty string = no link)."""

    id: str
    label: str
    kind: str          # css | partition | pattern | dn | trunk | route_list | route_group | hunt_pilot | hunt_list | collapsed
    detail_url: str = ""
    extras: dict = field(default_factory=dict)

    def to_cyto(self) -> dict:
        return {"data": {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "detail_url": self.detail_url,
            **self.extras,
        }}


@dataclass
class GraphEdge:
    """One Cytoscape edge. ``label`` annotates the connection (priority,
    pattern syntax, etc.); ``kind`` lets the renderer style different
    relationships differently (CSS-priority vs RouteList-priority etc.)."""

    id: str
    source: str
    target: str
    label: str = ""
    kind: str = ""

    def to_cyto(self) -> dict:
        return {"data": {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "kind": self.kind,
        }}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_graph(
    anchor_kind: str,
    anchor_id: str,
    direction: str,
    trace_steps: Optional[list] = None,
) -> dict:
    """Build a Cytoscape-shaped graph from the given anchor.

    Returns ``{"nodes": [...], "edges": [...], "meta": {...}}``. The
    meta dict carries the anchor label + direction so the UI can render
    a header without re-fetching the anchor.

    Unknown anchor kinds or missing objects produce an empty graph
    rather than raising — the renderer surfaces "anchor not found" to
    the operator.

    When ``trace_steps`` is supplied (a list from ``dialplan.trace()``),
    the builder additionally:

    * Annotates each graph node matching a trace step with
      ``extras.step_index`` (zero-based position in the trace).
    * Skips aggregation for DNs/TranslationPatterns that are *in* the
      trace — so an aggregated supernode would otherwise hide the very
      thing the trace points at, which would break the visual story.
    * Emits ``meta.trace_steps`` as a serialized list for the side
      panel to render (label, kind, summary, subject, detail_url,
      and the resolved node_id for click-to-zoom).
    """
    # Compute trace-touched node ids upfront so the walker can decide
    # whether to aggregate. Steps without a mappable node id (terminal
    # kinds) get filtered out here.
    trace_step_ids: list[Optional[str]] = []
    if trace_steps:
        for step in trace_steps:
            trace_step_ids.append(trace_step_to_node_id(step))
    touched_ids: set[str] = {nid for nid in trace_step_ids if nid}

    builder = _Builder(touched_ids=touched_ids)
    if direction == "forward":
        if anchor_kind == "css":
            css = (
                models.CallingSearchSpace.objects
                .filter(pk=anchor_id)
                .select_related("phone_system")
                .first()
            )
            if css is None:
                return builder.empty(anchor_kind, anchor_id, direction)
            builder.walk_css_forward(css)
            return builder.finalize(direction=direction,
                                    anchor_label=css.name,
                                    anchor_kind="css",
                                    trace_steps=trace_steps,
                                    trace_step_ids=trace_step_ids)
        # Could add partition/trunk forward starts in a future pass.
        return builder.empty(anchor_kind, anchor_id, direction)

    if direction == "backward":
        if anchor_kind == "trunk":
            trunk = (
                models.Trunk.objects
                .filter(pk=anchor_id)
                .select_related("phone_system")
                .first()
            )
            if trunk is None:
                return builder.empty(anchor_kind, anchor_id, direction)
            builder.walk_trunk_backward(trunk)
            return builder.finalize(direction=direction,
                                    anchor_label=trunk.name,
                                    anchor_kind="trunk",
                                    trace_steps=trace_steps,
                                    trace_step_ids=trace_step_ids)
        return builder.empty(anchor_kind, anchor_id, direction)

    return builder.empty(anchor_kind, anchor_id, direction)


# ---------------------------------------------------------------------------
# Internal builder — encapsulates dedup + edge-id assignment
# ---------------------------------------------------------------------------


class _Builder:
    def __init__(self, touched_ids: Optional[set[str]] = None):
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._edge_seq = 0
        # Trace-touched node ids — drives un-aggregation logic for
        # DN/TranslationPattern leaves so the trace's path stays
        # visually identifiable even when other siblings get bucketed.
        self._touched_ids: set[str] = touched_ids or set()

    def empty(self, anchor_kind, anchor_id, direction):
        return {
            "nodes": [],
            "edges": [],
            "meta": {
                "anchor_kind": anchor_kind,
                "anchor_id": anchor_id,
                "anchor_label": "(not found)",
                "direction": direction,
                "empty": True,
            },
        }

    def finalize(self, *, direction, anchor_label, anchor_kind,
                 trace_steps=None, trace_step_ids=None):
        # Annotate nodes with their position in the trace, if any.
        # Walking the trace_step_ids list rather than touched_ids
        # preserves the ORDER (step 0, 1, 2…) which the renderer uses
        # to color/number nodes by step position.
        if trace_step_ids:
            for idx, node_id in enumerate(trace_step_ids):
                if node_id and node_id in self._nodes:
                    self._nodes[node_id].extras["step_index"] = idx
        # Serialize trace steps for the side panel, paired with the
        # resolved node_id so click-to-zoom works.
        trace_payload = None
        if trace_steps:
            trace_payload = []
            for idx, step in enumerate(trace_steps):
                nid = trace_step_ids[idx] if trace_step_ids else None
                trace_payload.append({
                    "index": idx,
                    "kind": step.kind,
                    "summary": step.summary,
                    "subject": step.subject,
                    "detail_url": step.detail_url,
                    "node_id": nid,
                })
        return {
            "nodes": [n.to_cyto() for n in self._nodes.values()],
            "edges": [e.to_cyto() for e in self._edges],
            "meta": {
                "anchor_kind": anchor_kind,
                "anchor_label": anchor_label,
                "direction": direction,
                "node_count": len(self._nodes),
                "edge_count": len(self._edges),
                "empty": False,
                "trace_steps": trace_payload,
                "has_trace": bool(trace_payload),
            },
        }

    def add_node(self, node: GraphNode) -> str:
        """Dedupe by id — same object referenced from multiple places
        gets one node, not several. Returns the node id."""
        if node.id not in self._nodes:
            self._nodes[node.id] = node
        return node.id

    def add_edge(self, source: str, target: str, label: str = "",
                 kind: str = "") -> None:
        self._edge_seq += 1
        self._edges.append(GraphEdge(
            id=f"e{self._edge_seq}", source=source, target=target,
            label=label, kind=kind,
        ))

    # -- Forward (CSS-rooted) ---------------------------------------------

    def walk_css_forward(self, css):
        """CSS → its partition memberships (priority-ordered) → each
        partition's patterns → terminal destinations."""
        css_id = self.add_node(GraphNode(
            id=f"css:{css.pk}",
            label=css.name,
            kind="css",
            detail_url=_url(css),
        ))
        memberships = (
            css.memberships
            .select_related("partition")
            .order_by("priority")
        )
        for mem in memberships:
            pid = self._add_partition(mem.partition)
            self.add_edge(css_id, pid,
                          label=f"priority {mem.priority}",
                          kind="css_priority")
            self._add_partition_patterns_forward(mem.partition, pid)

    def _add_partition(self, partition) -> str:
        return self.add_node(GraphNode(
            id=f"partition:{partition.pk}",
            label=partition.name,
            kind="partition",
            detail_url=_url(partition),
        ))

    def _add_partition_patterns_forward(self, partition, partition_node_id):
        """All four pattern kinds in the partition.

        Aggregation strategy (critical for readability — a real LAB-CCM
        partition can hold hundreds of DNs):

        * **DNs and TranslationPatterns** are bucket-aggregated. If a
          partition has more than 1, we emit a single supernode like
          "📋 200 DNs" so the canvas doesn't explode. Single members
          still render individually so the trace from a small partition
          stays meaningful.
        * **RoutePatterns and HuntPilots** are typically a handful per
          partition and each one is operationally distinct (different
          destinations), so they render individually up to
          ``PATTERN_FANOUT_LIMIT``, then the tail collapses.

        Without this, an Internal-CSS forward graph against the real
        ~1400-DN cluster produces ~1500 nodes spanning >100K vertical
        pixels — unusable.
        """
        # -- DNs: aggregate when count > 1 (with un-aggregation for
        # any DN the active trace touched, so the trace's visual path
        # stays intact). --
        dns = list(models.DirectoryNumber.objects.filter(partition=partition))
        touched_dns = [d for d in dns if f"dn:{d.pk}" in self._touched_ids]
        other_dns = [d for d in dns if f"dn:{d.pk}" not in self._touched_ids]
        for dn in touched_dns:
            leaf = self._add_dn(dn)
            self.add_edge(partition_node_id, leaf,
                          label=dn.extension, kind="dn")
        if len(other_dns) == 1 and not touched_dns:
            # No trace, single DN — render individually.
            leaf = self._add_dn(other_dns[0])
            self.add_edge(partition_node_id, leaf,
                          label=other_dns[0].extension, kind="dn")
        elif len(other_dns) >= 1:
            # Aggregate the remainder (or the whole bucket if no trace).
            # Use a stable id so the renderer doesn't duplicate.
            agg_id = f"dn_agg:{partition.pk}"
            label = (f"{len(other_dns)} DNs" if not touched_dns
                     else f"+ {len(other_dns)} other DNs")
            self.add_node(GraphNode(
                id=agg_id,
                label=label,
                kind="dn",
                detail_url=_url(partition),
                extras={"aggregated": True, "count": len(other_dns)},
            ))
            self.add_edge(partition_node_id, agg_id,
                          label=label, kind="dn")

        # -- TranslationPatterns: same un-aggregation logic --
        translations = list(models.TranslationPattern.objects.filter(partition=partition))
        touched_tps = [t for t in translations
                       if f"translation:{t.pk}" in self._touched_ids]
        other_tps = [t for t in translations
                     if f"translation:{t.pk}" not in self._touched_ids]
        for tp in touched_tps:
            tp_id = self.add_node(GraphNode(
                id=f"translation:{tp.pk}",
                label=tp.pattern,
                kind="translation",
                detail_url=_url(tp),
                extras={"summary": f"rewrites → {tp.called_party_transformation_mask or '(via prefix)'}"},
            ))
            self.add_edge(partition_node_id, tp_id,
                          label=tp.pattern, kind="translation")
        if len(other_tps) == 1 and not touched_tps:
            tp = other_tps[0]
            tp_id = self.add_node(GraphNode(
                id=f"translation:{tp.pk}",
                label=tp.pattern,
                kind="translation",
                detail_url=_url(tp),
                extras={"summary": f"rewrites → {tp.called_party_transformation_mask or '(via prefix)'}"},
            ))
            self.add_edge(partition_node_id, tp_id,
                          label=tp.pattern, kind="translation")
        elif len(other_tps) >= 1:
            agg_id = f"translation_agg:{partition.pk}"
            label = (f"{len(other_tps)} TransPatterns" if not touched_tps
                     else f"+ {len(other_tps)} other TransPatterns")
            self.add_node(GraphNode(
                id=agg_id,
                label=label,
                kind="translation",
                detail_url=_url(partition),
                extras={"aggregated": True, "count": len(other_tps)},
            ))
            self.add_edge(partition_node_id, agg_id,
                          label=label, kind="translation")

        # -- RoutePatterns: individual nodes, fanout-capped --
        route_patterns = list(
            models.RoutePattern.objects
            .filter(partition=partition)
            .select_related("target_trunk", "target_route_list", "target_dn")
        )
        for rp in route_patterns[:PATTERN_FANOUT_LIMIT]:
            leaf = self._add_route_pattern_forward(rp)
            self.add_edge(partition_node_id, leaf,
                          label=rp.pattern, kind="route_pattern")
        if len(route_patterns) > PATTERN_FANOUT_LIMIT:
            extra = len(route_patterns) - PATTERN_FANOUT_LIMIT
            collapsed_id = f"rp_collapsed:{partition.pk}"
            self.add_node(GraphNode(
                id=collapsed_id,
                label=f"+ {extra} RoutePatterns",
                kind="collapsed",
                detail_url=_url(partition),
                extras={"hidden_count": extra},
            ))
            self.add_edge(partition_node_id, collapsed_id,
                          label=f"{extra} hidden", kind="collapsed")

        # -- HuntPilots: individual nodes, fanout-capped --
        hunt_pilots = list(
            models.HuntPilot.objects
            .filter(partition=partition)
            .select_related("hunt_list")
        )
        for hp in hunt_pilots[:PATTERN_FANOUT_LIMIT]:
            leaf = self._add_hunt_pilot(hp)
            self.add_edge(partition_node_id, leaf,
                          label=hp.pattern, kind="hunt_pilot")
        if len(hunt_pilots) > PATTERN_FANOUT_LIMIT:
            extra = len(hunt_pilots) - PATTERN_FANOUT_LIMIT
            collapsed_id = f"hp_collapsed:{partition.pk}"
            self.add_node(GraphNode(
                id=collapsed_id,
                label=f"+ {extra} HuntPilots",
                kind="collapsed",
                detail_url=_url(partition),
                extras={"hidden_count": extra},
            ))
            self.add_edge(partition_node_id, collapsed_id,
                          label=f"{extra} hidden", kind="collapsed")

    def _add_dn(self, dn) -> str:
        return self.add_node(GraphNode(
            id=f"dn:{dn.pk}",
            label=dn.extension,
            kind="dn",
            detail_url=_url(dn),
        ))

    def _add_route_pattern_forward(self, rp) -> str:
        """RoutePattern → its destination node. Returns the RoutePattern
        node id (not the destination) so the partition's edge connects
        to the pattern, then the pattern's edge connects on to its
        target — keeps the graph readable."""
        rp_id = self.add_node(GraphNode(
            id=f"pattern:{rp.pk}",
            label=rp.pattern,
            kind="pattern",
            detail_url=_url(rp),
        ))
        if rp.target_trunk_id:
            tr_id = self._add_trunk(rp.target_trunk)
            self.add_edge(rp_id, tr_id, label="→ trunk", kind="rp_to_trunk")
        elif rp.target_route_list_id:
            rl_id = self._add_route_list_forward(rp.target_route_list)
            self.add_edge(rp_id, rl_id, label="→ list", kind="rp_to_rl")
        elif rp.target_dn_id:
            dn_id = self._add_dn(rp.target_dn)
            self.add_edge(rp_id, dn_id, label="→ DN", kind="rp_to_dn")
        return rp_id

    def _add_trunk(self, trunk) -> str:
        return self.add_node(GraphNode(
            id=f"trunk:{trunk.pk}",
            label=trunk.name,
            kind="trunk",
            detail_url=_url(trunk),
            extras={"trunk_type": trunk.trunk_type,
                    "destination": trunk.destination_address or ""},
        ))

    def _add_route_list_forward(self, rl) -> str:
        rl_id = self.add_node(GraphNode(
            id=f"route_list:{rl.pk}",
            label=rl.name,
            kind="route_list",
            detail_url=_url(rl),
        ))
        for mem in rl.memberships.select_related("route_group").order_by("priority"):
            rg = mem.route_group
            rg_id = self.add_node(GraphNode(
                id=f"route_group:{rg.pk}",
                label=rg.name,
                kind="route_group",
                detail_url=_url(rg),
                extras={"algorithm": rg.distribution_algorithm or ""},
            ))
            self.add_edge(rl_id, rg_id,
                          label=f"priority {mem.priority}",
                          kind="rl_priority")
            for rgm in rg.members.order_by("priority"):
                target = rgm.target
                if target is None:
                    continue
                target_id = self._add_polymorphic_target(target)
                self.add_edge(rg_id, target_id,
                              label=f"priority {rgm.priority}",
                              kind="rg_priority")
        return rl_id

    def _add_polymorphic_target(self, target) -> str:
        """RouteGroupMember.target is GFK to Trunk or AnalogGateway."""
        if isinstance(target, models.Trunk):
            return self._add_trunk(target)
        # AnalogGateway — same node shape, different kind for color.
        return self.add_node(GraphNode(
            id=f"analog_gateway:{target.pk}",
            label=target.name,
            kind="analog_gateway",
            detail_url=_url(target),
        ))

    def _add_hunt_pilot(self, hp) -> str:
        hp_id = self.add_node(GraphNode(
            id=f"hunt_pilot:{hp.pk}",
            label=hp.pattern,
            kind="hunt_pilot",
            detail_url=_url(hp),
        ))
        if hp.hunt_list_id:
            hl = hp.hunt_list
            hl_id = self.add_node(GraphNode(
                id=f"hunt_list:{hl.pk}",
                label=hl.name,
                kind="hunt_list",
                detail_url=_url(hl),
                extras={"member_count": hl.members.count()},
            ))
            self.add_edge(hp_id, hl_id, label="→ list", kind="hp_to_hl")
        return hp_id

    # -- Backward (Trunk-rooted) ------------------------------------------

    def walk_trunk_backward(self, trunk):
        """Trunk ← RouteGroup memberships ← RouteLists ← RoutePatterns
        ← Partitions ← CSSes."""
        from django.contrib.contenttypes.models import ContentType
        trunk_id = self._add_trunk(trunk)
        trunk_ct = ContentType.objects.get_for_model(models.Trunk)

        # Path 1: RoutePatterns targeting this trunk directly.
        for rp in (
            models.RoutePattern.objects
            .filter(target_trunk=trunk)
            .select_related("partition")
        ):
            rp_id = self.add_node(GraphNode(
                id=f"pattern:{rp.pk}",
                label=rp.pattern,
                kind="pattern",
                detail_url=_url(rp),
            ))
            self.add_edge(rp_id, trunk_id, label="→ trunk", kind="rp_to_trunk")
            if rp.partition_id:
                self._walk_partition_backward(rp.partition, rp_id)

        # Path 2: Trunk is a member of RouteGroup(s); each group lives
        # in RouteList(s); each list is targeted by RoutePatterns; each
        # pattern lives in a Partition; each partition belongs to CSSes.
        rgms = models.RouteGroupMember.objects.filter(
            target_type=trunk_ct, target_id=trunk.pk,
        ).select_related("route_group")
        for rgm in rgms:
            rg = rgm.route_group
            rg_id = self.add_node(GraphNode(
                id=f"route_group:{rg.pk}",
                label=rg.name,
                kind="route_group",
                detail_url=_url(rg),
                extras={"algorithm": rg.distribution_algorithm or ""},
            ))
            self.add_edge(rg_id, trunk_id,
                          label=f"priority {rgm.priority}",
                          kind="rg_priority")
            for rlm in models.RouteListMember.objects.filter(
                route_group=rg,
            ).select_related("route_list"):
                rl = rlm.route_list
                rl_id = self.add_node(GraphNode(
                    id=f"route_list:{rl.pk}",
                    label=rl.name,
                    kind="route_list",
                    detail_url=_url(rl),
                ))
                self.add_edge(rl_id, rg_id,
                              label=f"priority {rlm.priority}",
                              kind="rl_priority")
                for rp in models.RoutePattern.objects.filter(
                    target_route_list=rl,
                ).select_related("partition"):
                    rp_id = self.add_node(GraphNode(
                        id=f"pattern:{rp.pk}",
                        label=rp.pattern,
                        kind="pattern",
                        detail_url=_url(rp),
                    ))
                    self.add_edge(rp_id, rl_id, label="→ list",
                                  kind="rp_to_rl")
                    if rp.partition_id:
                        self._walk_partition_backward(rp.partition, rp_id)

    def _walk_partition_backward(self, partition, leaf_node_id):
        """Edge: partition → leaf (the pattern); then partition ← CSSes
        that include this partition."""
        p_id = self._add_partition(partition)
        self.add_edge(p_id, leaf_node_id, label="contains", kind="partition_contains")
        for mem in partition.memberships.select_related("css"):
            css_id = self.add_node(GraphNode(
                id=f"css:{mem.css.pk}",
                label=mem.css.name,
                kind="css",
                detail_url=_url(mem.css),
            ))
            self.add_edge(css_id, p_id,
                          label=f"priority {mem.priority}",
                          kind="css_priority")


def _url(obj) -> str:
    """Safe get_absolute_url — returns '' if unavailable."""
    try:
        return obj.get_absolute_url()
    except Exception:  # pragma: no cover - defensive
        return ""
