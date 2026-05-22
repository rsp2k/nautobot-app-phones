"""Heatmap data structures for visualizing DID inventory on a Circuit.

Renders ``DIDBlock`` and ``DID`` records on a given circuit as a nested grid:
NPA-NXX group → 100-cell hundred-block → individual DID cell.

The grouping key is the first 8 digits of an E.164 string (NPA + NXX + first
two digits of the line number). For each hundred-block, the cells at positions
00-99 represent the last two digits — present iff the number is in inventory
(either covered by a DIDBlock or materialized as a DID row), absent otherwise.

Coloring layers (data attributes the template reads):
- ``data-status="present"``: number is in inventory, no routing info yet
- ``data-status="routed"``: number has a DIDAssignment to a DirectoryNumber
- ``data-status="unrouted"``: number is in inventory but unassigned
- ``data-status="pilot"``: number == SipCircuitProfile.pilot_e164

Scope-A version: only present-vs-gap + pilot. Routed/unrouted gets layered in
once DIDAssignment data is populated.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class HeatmapCell:
    """One DID cell in a hundred-block grid."""

    position: str           # "00" through "99"
    e164: str | None        # full E.164 if present, else None for gaps
    status: str             # "gap" | "present" | "routed" | "unrouted" | "pilot"


@dataclass
class HundredBlock:
    """A 100-number sub-range (e.g. 208-782-37xx = 2087823700-2087823799)."""

    prefix_8: str           # first 8 digits, e.g. "20878237"
    label: str              # display label, e.g. "37xx"
    cells: list[HeatmapCell] = field(default_factory=list)
    filled_count: int = 0
    routed_count: int = 0


@dataclass
class NpaNxxGroup:
    """All inventory for one NPA-NXX, broken into hundred-blocks."""

    npa_nxx: str            # "208-782"
    dids_count: int         # total filled cells across all hundred-blocks
    routed_count: int       # total cells with status="routed"
    hundred_blocks: list[HundredBlock] = field(default_factory=list)

    @property
    def hundred_blocks_count(self) -> int:
        """Distinct hundred-blocks in this group."""
        return len(self.hundred_blocks)


@dataclass
class HeatmapData:
    """Top-level structure handed to the template."""

    total_dids: int
    total_routed: int
    total_unrouted: int
    pilot_e164: str
    groups: list[NpaNxxGroup] = field(default_factory=list)


def _expand_block_e164s(start_e164: str, end_e164: str) -> Iterable[str]:
    """Yield every E.164 string in [start, end], inclusive."""
    start_int = int(start_e164)
    end_int = int(end_e164)
    width = len(start_e164)
    for n in range(start_int, end_int + 1):
        yield str(n).zfill(width)


def build_heatmap_data(profile) -> HeatmapData:
    """Build a HeatmapData for the given SipCircuitProfile.

    Walks the DIDBlocks + DIDs attached to the profile's circuit, expands
    every block into its constituent E.164 strings, deduplicates against
    individually-materialized DIDs, then groups by NPA-NXX and hundred-block.

    Routing status comes from DIDAssignment lookups against the materialized
    DID rows. Block-only DIDs (never materialized as a DID row) can't have
    an assignment, so they're marked "unrouted" by definition.
    """
    from nautobot_phones.models import DID, DIDAssignment, DIDBlock

    circuit = profile.circuit
    pilot_e164 = profile.pilot_e164 or ""

    # Step 1: collect every E.164 the circuit owns, with its source-of-truth flag.
    # owned[e164] = {"in_block": bool, "did_obj": DID | None}
    owned: dict[str, dict] = {}

    blocks = DIDBlock.objects.filter(circuit=circuit).order_by("start_e164")
    for block in blocks:
        for e164 in _expand_block_e164s(block.start_e164, block.end_e164):
            owned[e164] = {"in_block": True, "did_obj": None}

    dids = DID.objects.filter(circuit=circuit).select_related("assignment")
    for did in dids:
        record = owned.setdefault(did.e164, {"in_block": False, "did_obj": None})
        record["did_obj"] = did

    # Step 2: figure out routing status for materialized DIDs.
    # A DID is "routed" iff its DIDAssignment.target_type is directorynumber.
    # We could check the GFK target_type FK, but the simpler approach is
    # to look at whether an assignment exists at all (in scope-A there are
    # no assignments anywhere, so this is all "unrouted" — but the code
    # path is in place for when scope B/C lands).
    routed_e164s: set[str] = set()
    if dids:
        from django.contrib.contenttypes.models import ContentType

        dn_ct = ContentType.objects.get(app_label="nautobot_phones", model="directorynumber")
        assignments = DIDAssignment.objects.filter(
            did__circuit=circuit, target_type=dn_ct,
        ).values_list("did__e164", flat=True)
        routed_e164s = set(assignments)

    # Step 3: group by hundred-block prefix (first 8 digits).
    # hundred[prefix_8] = {position: cell}
    hundred: dict[str, dict[str, HeatmapCell]] = defaultdict(dict)

    for e164, info in owned.items():
        prefix_8 = e164[:8]
        position = e164[8:10]
        if e164 == pilot_e164:
            status = "pilot"
        elif e164 in routed_e164s:
            status = "routed"
        elif info["did_obj"] is not None or info["in_block"]:
            # Present in inventory but not routed yet.
            status = "unrouted"
        else:  # pragma: no cover - shouldn't happen given owned[] construction
            status = "gap"
        hundred[prefix_8][position] = HeatmapCell(
            position=position, e164=e164, status=status,
        )

    # Step 4: build every hundred-block's full 100-cell grid, filling
    # absent positions with status="gap".
    hundred_blocks_by_prefix: dict[str, HundredBlock] = {}
    for prefix_8, present_cells in hundred.items():
        hb = HundredBlock(prefix_8=prefix_8, label=f"{prefix_8[6:8]}xx")
        for i in range(100):
            position = f"{i:02d}"
            cell = present_cells.get(position) or HeatmapCell(
                position=position, e164=None, status="gap",
            )
            hb.cells.append(cell)
            if cell.status != "gap":
                hb.filled_count += 1
                if cell.status == "routed":
                    hb.routed_count += 1
        hundred_blocks_by_prefix[prefix_8] = hb

    # Step 5: group hundred-blocks by NPA-NXX (first 6 digits).
    groups_by_npa_nxx: dict[str, NpaNxxGroup] = {}
    for prefix_8, hb in sorted(hundred_blocks_by_prefix.items()):
        npa_nxx_digits = prefix_8[:6]
        # Format "208782" → "208-782"
        npa_nxx_label = f"{npa_nxx_digits[:3]}-{npa_nxx_digits[3:6]}"
        group = groups_by_npa_nxx.setdefault(
            npa_nxx_label,
            NpaNxxGroup(npa_nxx=npa_nxx_label, dids_count=0, routed_count=0),
        )
        group.hundred_blocks.append(hb)
        group.dids_count += hb.filled_count
        group.routed_count += hb.routed_count

    # Step 6: totals across all groups.
    total_dids = sum(g.dids_count for g in groups_by_npa_nxx.values())
    total_routed = sum(g.routed_count for g in groups_by_npa_nxx.values())

    return HeatmapData(
        total_dids=total_dids,
        total_routed=total_routed,
        total_unrouted=total_dids - total_routed,
        pilot_e164=pilot_e164,
        groups=sorted(
            groups_by_npa_nxx.values(),
            # Largest groups first.
            key=lambda g: (-g.dids_count, g.npa_nxx),
        ),
    )
