# Dial-Plan Trace

The dial-plan trace walks what happens when a phone (or trunk) dials a
number — step by step, sourced from the synced dial plan. It's an
operational diagnosis tool: "I think Alice's phone should be able to
reach 911 but I'm not sure why," "this trunk's inbound calls are
going to the wrong place," "translation-pattern X is supposed to
rewrite Y but I can't tell which path it takes." Run the trace, get
a clickable annotated path through the partitions, patterns, and
egress devices CCM (or FreePBX) would visit.

Pure-read tool — no writes, no side effects, no calls to the CCM. The
trace operates entirely on the data already synced into Nautobot.

!!! tip "Looking for the visual version?"
    The [dial-plan graph](dialplan_graph.md) renders the same trace as
    an overlay on the topology — the call path lights up against the
    full dial-plan structure, with non-traversed branches dimmed.
    Best for "show me where the call dies in context."

## Reaching the trace

Three entry points, all submit to the same standalone view:

* **Apps → Phones → Dial-plan trace** in the side nav
* **"Trace from this phone" panel** at the bottom of a Phone detail page — pre-fills `phone_system` + the phone's CSS
* **"Trace inbound from this trunk" panel** at the bottom of a Trunk detail page — pre-fills `phone_system` + `inbound_css`

Either panel submits to the standalone view; the resulting URL is
shareable ("here's the trace from Alice's phone dialing 911").

## Two-mode form

The standalone view has two tabs:

### By Endpoint

Type a phone name/MAC/description, DN extension, or trunk name into
the autocomplete. Each result carries the derived `phone_system` and
`starting_css` so submitting runs the trace without further clicks.

```
┌─ [● By Endpoint] [○ Manual] ─┐
│ 🔍 1300 → SEP0022EE194ACE   │
│ Calling from: Line 1: 1300  │
│ Dialed digits: [911     ]   │
│             [Trace]         │
└──────────────────────────────┘
```

* **Phone hit** — searches `device_name`, `mac_address`, `description`. CSS comes from `vendor_extras["callingSearchSpaceName"]`.
* **DN hit** — searches `DirectoryNumber.extension`, returns one row per holder phone. Selecting any holder traces from that phone's CSS.
* **Trunk hit** — searches `Trunk.name`. CSS = `Trunk.inbound_css` for inbound-call simulation.
* **Orphan DN** — a DN with no holder phone is included in results but disabled (no CSS to trace from). Surfaces stale data without letting operators select something the trace can't process.

When you pick a phone endpoint, the **Calling from** field auto-morphs
from a free-text input into a dropdown of that phone's lines. Pick
which line dials — matters for shared-line / multi-DN phones where
the choice changes ANI presentation.

### Manual

Pick `phone_system` and `starting_css` directly. Use this when:

* You want to test "what if Alice were in PSTN-Allowed-CSS?" — override the CSS
* The endpoint's derived CSS isn't right (e.g. vendor_extras hasn't been populated yet)
* You're debugging a CSS itself, not a specific endpoint

**Single-system convenience:** if exactly one `PhoneSystem` exists,
it's auto-selected so single-cluster operators don't have to click.

## The optional "Calling from" field

Captures the originating number for the trace header. Doesn't affect
pattern matching in v1 — purely for documenting "this trace simulates
DN 1300 dialing 911" in the result.

## Reading the trace

Each step has an icon, a kind tag, a one-line summary, and a clickable
link to the underlying object. Step kinds:

| Kind | Meaning |
|------|---------|
| **CSS** | Trace starting — names the CSS and how many partitions it scans |
| **PartitionCheck** | Walking one partition in CSS priority order |
| **DnMatch** | Dialed digits matched a DN — call rings any phones holding that DN |
| **RoutePatternMatch** | Pattern matched — call routes to its target (Trunk / RouteList / DN) |
| **TranslationMatch** | TransPattern rewrote the digits; trace re-enters with the new string |
| **HuntPilotMatch** | HuntPilot matched — enters the hunt subsystem |
| **HuntSubsystem** | Per-LineGroup expansion: ordered DNs that would ring |
| **TrunkEgress** | Direct trunk egress (RoutePattern → Trunk) — terminal |
| **RouteListEgress** | Call enters a RouteList (RoutePattern → RouteList) |
| **RouteGroupSelect** | One RouteGroup attempted in priority order; lists its Trunks/Gateways |
| **LikelyEgress** | Best-effort: top-priority target in top-priority group, or explains why nothing routes |
| **NoMatch** | Nothing matched in any visited partition — caller hears reorder |
| **RecursionLimit** | Translation chain exceeded MAX_TRANSLATION_DEPTH (8 hops) |

### Egress chase

For RouteList-routed calls the trace continues past the
`route_list_egress` step into per-RouteGroup expansion, then names a
**likely first egress attempt** at the bottom. The "likely" phrasing
is deliberate: real CCM evaluates circuit availability and time-of-day
routing at runtime, so the trace identifies the *first* candidate but
won't claim to know which trunk actually carries the call.

If a RouteList has no member groups (a common Cisco "blackhole"
pattern — intentional drop for restricted CSSes), the terminal step
spells it out: "RouteList 'Blackhole-RL' has no member RouteGroups —
call has nowhere to egress." Same outcome as a misconfiguration, but
the trace tells you it's by design.

### Translation chain

When a TranslationPattern matches, the trace shows the rewritten
digits and re-enters from the same CSS. Capped at 8 hops to prevent
runaway translation loops (rare in well-formed dial plans but a real
hazard worth guarding).

## Pattern syntax

The trace recognizes CCM-style dial patterns:

| Pattern | Meaning |
|---------|---------|
| `1234` | Literal digits |
| `X` | Any single digit (`[0-9]`) |
| `[2-9]` | Character class — passed through to regex |
| `.` | Position marker (NOT a wildcard) — separates PreDot/PostDot |
| `@` | NANP/E.164 remaining digits — approximated as `\d*` |
| `!` | One or more digits |
| `\<char>` | Escape — `\+` is the canonical E.164 leading-plus catcher |
| `+` `*` `#` | Literal characters |

The escape handling (`\+.@` for E.164 catchers) was a real adapter
bug we hit early — see `tests/test_dialplan_trace.py` for the
regression cases that pin the semantics.

## Operational findings the trace surfaces

* **Blackhole RouteLists** — RouteList with zero member groups indicates an intentional drop pattern. The trace reports this clearly, so operators see policy vs. failure.
* **Stale TranslationPatterns** — translation that rewrites to a non-existent DN/route shows `Re-enter trace with <new digits>` then `NoMatch`. Clear diagnosis of "this rewrite has no target."
* **Misleading CSS names** — a CSS named `PSTN-Allowed-CSS` that actually doesn't include any PSTN partitions will trace as `NoMatch` for PSTN dials. The trace surfaces the gap between what the CSS *looks like* and what it *is*.
* **CER 911 paths** — Cisco Emergency Responder typically lives in a `911CER-PT` partition with literal DN `911` at highest priority. Traces from any CSS that includes `911CER-PT` correctly identify it before falling through to lower-priority partitions.

## Embedded panels

Both `Phone.detail` and `Trunk.detail` get a "Trace …" panel that
inline-prefills and submits to the standalone view. Phone-side
prefills the phone's vendor CSS; trunk-side prefills the trunk's
`inbound_css`. Either way the result page is the same URL operators
can paste into a ticket.

## Not (yet) modeled

* **Time-of-day routing** — patterns that branch on day/hour aren't surfaced
* **Circuit availability** — `likely_egress` names the *first* target but real CCM picks based on RTP load + ICT health
* **CDR replay** — the trace simulates a synthetic call; it doesn't pull real call detail records
* **Calling-party transformations** — only `called_party_transformation_mask`, `prefix_digits_out`, and PreDot discard are modeled; `calling_party_*` fields are recorded but not applied
