"""Dial-plan trace engine — walks what would happen when a pattern is dialed.

Operator question this answers: *"From this calling search space, what
happens when I dial these digits?"* — without forcing a click through 8
different CCM admin pages to follow the trace by hand.

The trace honors CCM dial-plan evaluation semantics (which the
vendor-agnostic unified model mirrors closely):

1. **Calling Search Space** lists Partitions in priority order.
2. The dialed digits are matched against patterns in each partition,
   visiting partitions in CSS order. Best-match-wins (most-specific
   pattern in the highest-priority partition).
3. The matched pattern type determines what happens next:

   * **Directory Number** — ring whatever lines this DN appears on.
   * **TranslationPattern** — rewrite digits (per the mask /
     transform fields) and re-enter matching with the new digits +
     possibly a different CSS.
   * **RoutePattern** — resolve the destination (Trunk → off-net,
     RouteList → ordered list of Route Groups → devices, or DN — the
     last is FreePBX-only since CCM patterns don't directly target DNs).
   * **HuntPilot** — enter the hunt subsystem (HuntList → LineGroups
     in priority order → DNs in distribution-algorithm order).

The trace function is pure-Python and deterministic given the same DB
state. No live AXL / FreePBX calls; all data comes from already-synced
Nautobot records.

Output shape: a list of :class:`TraceStep` dataclasses. Each step has
a `kind` (string discriminator), a `summary` (one-line human-readable),
optional `detail_url` (link to the source ORM record), and a `subject`
(the matched pattern/DN/etc. for context).

Recursion safety: TranslationPattern can technically loop forever
(pattern A rewrites to digits that match pattern B which rewrites
back to A). We cap at ``MAX_TRANSLATION_DEPTH`` and emit a
``"unreachable"`` step when the cap is hit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from nautobot_phones.models import (
    CallingSearchSpace,
    DirectoryNumber,
    HuntPilot,
    PhoneSystem,
    RoutePattern,
    TranslationPattern,
)


MAX_TRANSLATION_DEPTH = 8
"""Hard cap on TranslationPattern recursion. Real dial plans rarely
chain more than 2-3 deep; this catches cycles without truncating
legitimate paths."""


@dataclass
class TraceStep:
    """One step in the dial-plan walk.

    ``kind`` discriminates how the UI should render the step. Each
    UI template handles each kind with a slightly different icon /
    color / detail block. Kinds:

    * ``"css"`` — the trace started from this CSS
    * ``"partition_check"`` — visiting a partition in CSS order
    * ``"dn_match"`` — dialed digits match a DN; trace terminates
    * ``"route_pattern_match"`` — RoutePattern matched; trace continues
      to whatever it points at (trunk / route list / DN)
    * ``"translation_match"`` — TransPattern matched; trace re-enters
      with rewritten digits
    * ``"hunt_pilot_match"`` — HuntPilot matched; trace enters hunt subsystem
    * ``"hunt_subsystem"`` — within the hunt subsystem, the line groups
      and DNs that will be tried in order
    * ``"trunk_egress"`` — call leaves directly via a Trunk (RoutePattern
      points at one); terminal step
    * ``"route_list_egress"`` — call enters a RouteList; the egress chase
      then continues with ``route_group_select`` step(s)
    * ``"route_group_select"`` — within a RouteList, one RouteGroup is
      being attempted (in priority order). ``extras["members"]`` lists
      its targets (Trunks / AnalogGateways) in their own priority order.
    * ``"likely_egress"`` — best-effort hint at the *first* target that
      would actually carry the call (top-priority member of the
      top-priority RouteGroup). Not authoritative — real CCM evaluates
      circuit availability and time-of-day routing at runtime.
    * ``"no_match"`` — no pattern matched in any visited partition;
      caller hears reorder/unreachable
    * ``"recursion_limit"`` — translation chain exceeded MAX_TRANSLATION_DEPTH
    """

    kind: str
    summary: str
    subject: str = ""
    detail_url: str = ""
    extras: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pattern matching — small subset of CCM's regex-ish syntax
# ---------------------------------------------------------------------------


def _pattern_to_regex(pattern: str) -> re.Pattern:
    """Convert a CCM-style dial pattern into a Python regex.

    Supported metachars:

    * ``X`` → any single digit (``[0-9]``)
    * ``[abc]`` → character class (passed through)
    * ``[2-9]`` → range in a character class (passed through)
    * ``.`` → position marker (NOT a wildcard). CCM uses this as a
      separator for PreDot/PostDot digit-discard; it does not consume
      any input character itself. Output as empty string in the regex
      so adjacent constructs match correctly (``9.@`` → ``9`` then
      ``@``-wildcard).
    * ``@`` → "remaining digits per E.164 / NANP numbering plan" —
      CCM uses this in patterns like ``9.@`` (NANP outbound) and
      ``\\+.@`` (E.164 catcher). Approximated as ``\\d*``.
    * ``!`` → one or more digits — Python regex ``\\d+``
    * ``\\<char>`` → literal next char regardless of metachar status.
      CCM uses this to escape ``+`` in E.164-catcher patterns —
      ``\\+.@`` means "literal ``+`` then any digits". Without this
      handling, the ``+`` would still get re-escaped after the
      backslash itself was escaped, producing a regex that requires
      a literal backslash in the input.
    * ``+`` → literal ``+`` (e.g. unescaped E.164 prefix; CCM
      operators usually write this as ``\\+`` but accept the bare
      form too)
    * ``*`` → literal ``*`` (e.g. feature codes ``*72``)
    * ``#`` → literal ``#``
    * Digits 0-9 → themselves

    Anchored at both ends so partial matches don't slip through.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            # ``\<char>`` escape — treat the next char as a literal,
            # regardless of whether it would otherwise be a metachar.
            # Most common in CCM: ``\+`` for the E.164 leading plus.
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        if ch == "X":
            out.append("[0-9]")
        elif ch == "[":
            # Pass character classes through as-is. Find the closing ].
            end = pattern.find("]", i)
            if end < 0:
                out.append(re.escape(ch))
                i += 1
                continue
            out.append(pattern[i:end + 1])
            i = end + 1
            continue
        elif ch == ".":
            # Position marker (NOT a wildcard). Doesn't consume input.
            pass
        elif ch == "@":
            # CCM's "remaining digits per E.164 / NANP plan" wildcard.
            # For trace purposes we treat it like ``.`` — match any
            # remaining digits — since we're checking whole strings,
            # not progressive collection.
            out.append(r"\d*")
        elif ch == "!":
            out.append(r"\d+")
        elif ch == "+":
            out.append(r"\+")
        elif ch == "*":
            out.append(r"\*")
        elif ch == "#":
            out.append("#")
        elif ch.isdigit():
            out.append(ch)
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile(f"^{''.join(out)}$")


def _specificity(pattern: str) -> int:
    """Rank a pattern by how specific it is. Higher = more specific.

    CCM "longest match wins" applies; we approximate by counting
    literal-digit characters (the most-specific bits) and subtracting
    wildcards. Ties broken by overall pattern length (longer = more
    specific in practice).
    """
    literal_digits = sum(1 for c in pattern if c.isdigit())
    wildcards = pattern.count("X") + pattern.count(".") + pattern.count("!")
    return literal_digits * 10 - wildcards + len(pattern)


# ---------------------------------------------------------------------------
# Trace engine
# ---------------------------------------------------------------------------


def trace(
    *,
    phone_system: PhoneSystem,
    starting_css: CallingSearchSpace,
    dialed_digits: str,
    _depth: int = 0,
) -> list[TraceStep]:
    """Trace what happens when ``dialed_digits`` is dialed from ``starting_css``.

    Returns an ordered list of :class:`TraceStep`. Always non-empty —
    if no match is found, the last step is a ``no_match`` step.
    """
    steps: list[TraceStep] = []

    if _depth >= MAX_TRANSLATION_DEPTH:
        steps.append(TraceStep(
            kind="recursion_limit",
            summary=f"Translation chain exceeded {MAX_TRANSLATION_DEPTH} hops — "
                    f"likely a loop in the dial plan",
            subject=dialed_digits,
        ))
        return steps

    if _depth == 0:
        # Initial step records the entry point.
        steps.append(TraceStep(
            kind="css",
            summary=f"Caller is in CSS {starting_css.name!r}; "
                    f"will check {starting_css.memberships.count()} partition(s) "
                    f"in priority order",
            subject=starting_css.name,
            detail_url=starting_css.get_absolute_url() if hasattr(starting_css, "get_absolute_url") else "",
        ))

    # Resolve the partition list in priority order.
    memberships = starting_css.memberships.select_related("partition").order_by("priority")
    partition_ids: list[str] = []
    for mship in memberships:
        partition_ids.append(str(mship.partition_id))
        steps.append(TraceStep(
            kind="partition_check",
            summary=f"Looking in partition {mship.partition.name!r} "
                    f"(priority {mship.priority})",
            subject=mship.partition.name,
            detail_url=mship.partition.get_absolute_url() if hasattr(mship.partition, "get_absolute_url") else "",
        ))

    if not partition_ids:
        steps.append(TraceStep(
            kind="no_match",
            summary=f"CSS {starting_css.name!r} has no partition memberships — "
                    f"call cannot route",
            subject=dialed_digits,
        ))
        return steps

    # Best-match-wins across all visited partitions.
    candidate = _find_best_match(
        phone_system=phone_system,
        partition_ids=partition_ids,
        digits=dialed_digits,
    )

    if candidate is None:
        steps.append(TraceStep(
            kind="no_match",
            summary=f"No pattern in any visited partition matches "
                    f"{dialed_digits!r} — caller hears reorder/unreachable",
            subject=dialed_digits,
        ))
        return steps

    kind, obj = candidate

    if kind == "dn":
        steps.append(TraceStep(
            kind="dn_match",
            summary=f"DN {obj.extension!r} in partition {obj.partition.name!r} "
                    f"matched — would ring any phones with this DN as a line",
            subject=obj.extension,
            detail_url=obj.get_absolute_url() if hasattr(obj, "get_absolute_url") else "",
            extras={"partition": obj.partition.name,
                    "alerting_name": obj.alerting_name},
        ))
        return steps

    if kind == "translation":
        new_digits = _apply_translation(obj, dialed_digits)
        steps.append(TraceStep(
            kind="translation_match",
            summary=f"TranslationPattern {obj.pattern!r} matched — "
                    f"rewrites to {new_digits!r}",
            subject=obj.pattern,
            detail_url=obj.get_absolute_url() if hasattr(obj, "get_absolute_url") else "",
            extras={"new_digits": new_digits},
        ))
        # Re-enter trace with the new digits. CSS-for-translation isn't
        # modeled in our schema as a first-class field; for v1 we re-enter
        # with the same CSS (covers the common "internal translation" case).
        # If/when the adapter populates css__name on TransPattern, we can
        # hop to that CSS here instead.
        sub_steps = trace(
            phone_system=phone_system,
            starting_css=starting_css,
            dialed_digits=new_digits,
            _depth=_depth + 1,
        )
        # Drop the sub-trace's "css" header step — we're continuing the
        # same trace, not starting a new one.
        steps.extend(s for s in sub_steps if s.kind != "css")
        return steps

    if kind == "route_pattern":
        if obj.target_route_list_id is not None:
            steps.append(TraceStep(
                kind="route_pattern_match",
                summary=f"RoutePattern {obj.pattern!r} matched — routes "
                        f"through RouteList {obj.target_route_list.name!r}",
                subject=obj.pattern,
                detail_url=obj.get_absolute_url() if hasattr(obj, "get_absolute_url") else "",
            ))
            steps.append(TraceStep(
                kind="route_list_egress",
                summary=f"Call hits RouteList {obj.target_route_list.name!r} → "
                        f"evaluates RouteGroups in priority order",
                subject=obj.target_route_list.name,
                detail_url=obj.target_route_list.get_absolute_url() if hasattr(obj.target_route_list, "get_absolute_url") else "",
            ))
            steps.extend(_walk_route_list(obj.target_route_list))
        elif obj.target_trunk_id is not None:
            steps.append(TraceStep(
                kind="route_pattern_match",
                summary=f"RoutePattern {obj.pattern!r} matched — egresses via "
                        f"Trunk {obj.target_trunk.name!r}",
                subject=obj.pattern,
                detail_url=obj.get_absolute_url() if hasattr(obj, "get_absolute_url") else "",
            ))
            steps.append(TraceStep(
                kind="trunk_egress",
                summary=f"Call leaves cluster via Trunk {obj.target_trunk.name!r} "
                        f"({obj.target_trunk.destination_address or 'no address'})",
                subject=obj.target_trunk.name,
                detail_url=obj.target_trunk.get_absolute_url() if hasattr(obj.target_trunk, "get_absolute_url") else "",
            ))
        elif obj.target_dn_id is not None:
            steps.append(TraceStep(
                kind="route_pattern_match",
                summary=f"RoutePattern {obj.pattern!r} matched — targets DN "
                        f"{obj.target_dn.extension!r} (FreePBX-style inbound route)",
                subject=obj.pattern,
                detail_url=obj.get_absolute_url() if hasattr(obj, "get_absolute_url") else "",
            ))
            steps.append(TraceStep(
                kind="dn_match",
                summary=f"DN {obj.target_dn.extension!r} would ring",
                subject=obj.target_dn.extension,
                detail_url=obj.target_dn.get_absolute_url() if hasattr(obj.target_dn, "get_absolute_url") else "",
            ))
        return steps

    if kind == "hunt_pilot":
        steps.append(TraceStep(
            kind="hunt_pilot_match",
            summary=f"HuntPilot {obj.pattern!r} matched — "
                    f"enters HuntList {(obj.hunt_list.name if obj.hunt_list else 'NONE')}",
            subject=obj.pattern,
            detail_url=obj.get_absolute_url() if hasattr(obj, "get_absolute_url") else "",
        ))
        if obj.hunt_list is not None:
            for hlm in obj.hunt_list.members.select_related("line_group").order_by("selection_order"):
                lg = hlm.line_group
                dns = list(
                    lg.members.select_related("directory_number__partition")
                    .order_by("line_selection_order")
                )
                summary = (
                    f"LineGroup {lg.name!r} (selection order {hlm.selection_order}, "
                    f"algorithm {lg.distribution_algorithm or '—'}): "
                    f"{len(dns)} DN(s)"
                )
                steps.append(TraceStep(
                    kind="hunt_subsystem",
                    summary=summary,
                    subject=lg.name,
                    detail_url=lg.get_absolute_url() if hasattr(lg, "get_absolute_url") else "",
                    extras={
                        "dns": [
                            {"extension": d.directory_number.extension,
                             "partition": d.directory_number.partition.name,
                             "line_selection_order": d.line_selection_order}
                            for d in dns
                        ],
                    },
                ))
        return steps

    # Fallthrough — shouldn't happen with the four kinds above.
    steps.append(TraceStep(
        kind="no_match",
        summary=f"Internal error: matched a pattern of unknown kind {kind!r}",
        subject=dialed_digits,
    ))
    return steps


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_best_match(
    *,
    phone_system: PhoneSystem,
    partition_ids: list[str],
    digits: str,
) -> Optional[tuple[str, object]]:
    """Find the highest-specificity pattern matching ``digits`` across the
    given partitions. Returns ``(kind, obj)`` or ``None``.

    Kind is one of ``"dn"``, ``"translation"``, ``"route_pattern"``,
    ``"hunt_pilot"``.
    """
    candidates: list[tuple[int, str, object]] = []  # (specificity, kind, obj)

    # DNs — exact-string only (DNs don't take regex metachars in practice).
    for dn in DirectoryNumber.objects.filter(
        partition_id__in=partition_ids, partition__phone_system=phone_system,
    ):
        if dn.extension == digits:
            candidates.append((_specificity(dn.extension), "dn", dn))

    # TranslationPatterns.
    for tp in TranslationPattern.objects.filter(
        partition_id__in=partition_ids, partition__phone_system=phone_system,
    ):
        if _pattern_to_regex(tp.pattern).match(digits):
            candidates.append((_specificity(tp.pattern), "translation", tp))

    # RoutePatterns.
    for rp in RoutePattern.objects.filter(
        partition_id__in=partition_ids, partition__phone_system=phone_system,
    ).select_related("target_route_list", "target_trunk", "target_dn"):
        if _pattern_to_regex(rp.pattern).match(digits):
            candidates.append((_specificity(rp.pattern), "route_pattern", rp))

    # HuntPilots.
    for hp in HuntPilot.objects.filter(
        partition_id__in=partition_ids, partition__phone_system=phone_system,
    ).select_related("hunt_list"):
        if _pattern_to_regex(hp.pattern).match(digits):
            candidates.append((_specificity(hp.pattern), "hunt_pilot", hp))

    if not candidates:
        return None

    # Highest specificity wins. Within a specificity tie, the order in
    # ``partition_ids`` (CSS priority) is the next tiebreaker — we already
    # filtered by that list so all candidates are equally CSS-priority-valid;
    # tiebreaker is pattern length (already factored into specificity).
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, kind, obj = candidates[0]
    return kind, obj


def _apply_translation(tp: TranslationPattern, dialed: str) -> str:
    """Apply a TranslationPattern's transforms to the dialed digits.

    Simplified model: we honor ``called_party_transformation_mask`` if
    present (the most-used field in practice), falling back to the
    original dialed string. Full CCM transform support would also walk
    ``prefix_digits_out``, ``digit_discard_instruction``, and the
    ``calling_party_*`` fields — those are operationally important but
    aren't all promoted to first-class columns in our schema yet
    (they're in vendor_extras for many adapters).
    """
    mask = getattr(tp, "called_party_transformation_mask", "") or ""
    prefix = getattr(tp, "prefix_digits_out", "") or ""
    discard = (getattr(tp, "digit_discard_instruction", "") or "").lower()

    out = dialed
    # Apply digit-discard first (CCM order). PreDot strips up to the
    # last "." in the matching pattern position; we approximate by
    # treating "predot" / "pre-dot" as "strip everything before the
    # last dot in the matching pattern".
    if discard in ("predot", "pre-dot", "pre dot"):
        # PreDot removes the literal-prefix portion of the matching pattern
        # (everything up to the first "."). Approximation: strip the
        # literal-prefix from the dialed string by aligning lengths.
        dot_idx = tp.pattern.find(".")
        if dot_idx > 0 and dot_idx <= len(out):
            out = out[dot_idx:]

    # Then apply the mask (if any). Mask uses ``X`` placeholders that
    # take the corresponding digit from the post-discard digits; literal
    # digits in the mask appear verbatim in the output.
    if mask:
        masked: list[str] = []
        digit_idx = 0
        for ch in mask:
            if ch == "X":
                if digit_idx < len(out):
                    masked.append(out[digit_idx])
                    digit_idx += 1
            else:
                masked.append(ch)
        out = "".join(masked)

    # Prefix-digits-out tacks on a fixed prefix.
    if prefix:
        out = prefix + out

    return out


def _walk_route_list(route_list) -> list[TraceStep]:
    """Continue an egress trace from a RouteList through its RouteGroups
    and their members (Trunks / AnalogGateways).

    Returns the new steps to append to the trace — does NOT include the
    prior ``route_list_egress`` header step (the caller already emitted
    that). Steps emitted, in order:

    * One ``route_group_select`` per RouteListMember, in ``priority``
      order. Each step's ``extras["members"]`` is a list of dicts
      describing each RouteGroupMember target (Trunk or AnalogGateway).
    * One terminal ``likely_egress`` step naming the top-priority target
      in the top-priority RouteGroup — or, if the list is empty,
      explaining that the call has nowhere to go (blackhole pattern).

    We deliberately stop at the *first* target. A real CCM evaluates
    each candidate in turn against circuit availability and we can't
    know that from a static snapshot, so naming a single "likely first
    egress attempt" is the most honest claim the trace can make.
    """
    steps: list[TraceStep] = []
    memberships = list(
        route_list.memberships.select_related("route_group").order_by("priority")
    )
    if not memberships:
        # Empty route list — classic CCM "blackhole" pattern. The call
        # matched a route pattern, hit the list, and the list has no
        # available group → reorder tone.
        steps.append(TraceStep(
            kind="likely_egress",
            summary=f"RouteList {route_list.name!r} has no member RouteGroups — "
                    f"call has nowhere to egress (blackhole / reorder)",
            subject=route_list.name,
            detail_url=route_list.get_absolute_url() if hasattr(route_list, "get_absolute_url") else "",
        ))
        return steps

    likely_target = None
    likely_target_kind = ""
    for rlm in memberships:
        rg = rlm.route_group
        # Walk the through-table directly so we get the priority field
        # without needing two queries per member.
        members = list(rg.members.order_by("priority"))
        member_extras = []
        for rgm in members:
            target = rgm.target  # GFK — Trunk or AnalogGateway
            if target is None:
                member_extras.append({
                    "name": "(missing)",
                    "type": rgm.target_type.model if rgm.target_type_id else "unknown",
                    "priority": rgm.priority,
                    "address": "",
                    "detail_url": "",
                })
                continue
            member_extras.append({
                "name": target.name,
                "type": rgm.target_type.model,
                "priority": rgm.priority,
                "address": getattr(target, "destination_address", "") or "",
                "detail_url": target.get_absolute_url() if hasattr(target, "get_absolute_url") else "",
            })
        steps.append(TraceStep(
            kind="route_group_select",
            summary=(
                f"RouteGroup {rg.name!r} (list priority {rlm.priority}, "
                f"algorithm {rg.distribution_algorithm or '—'}): "
                f"{len(members)} member(s)"
            ),
            subject=rg.name,
            detail_url=rg.get_absolute_url() if hasattr(rg, "get_absolute_url") else "",
            extras={"members": member_extras},
        ))
        # Record the first (highest priority) target across the whole walk
        # — that's the "first attempt" call path.
        if likely_target is None and member_extras:
            first = member_extras[0]
            likely_target = first
            likely_target_kind = first["type"]

    if likely_target is None:
        steps.append(TraceStep(
            kind="likely_egress",
            summary=f"RouteList {route_list.name!r} has groups but none contain "
                    f"any Trunks/Gateways — call has nowhere to egress",
            subject=route_list.name,
            detail_url=route_list.get_absolute_url() if hasattr(route_list, "get_absolute_url") else "",
        ))
    else:
        addr = f" ({likely_target['address']})" if likely_target["address"] else ""
        steps.append(TraceStep(
            kind="likely_egress",
            summary=(
                f"First egress attempt: {likely_target_kind} "
                f"{likely_target['name']!r}{addr}. Actual selection at "
                f"runtime depends on circuit availability and routing policy."
            ),
            subject=likely_target["name"],
            detail_url=likely_target["detail_url"],
        ))
    return steps
