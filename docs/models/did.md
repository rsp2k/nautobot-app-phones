# DID

An individual E.164 number, materialized only when needed: assigned to a DN/Trunk/voicemail (via [DIDAssignment](didassignment.md)), marked special (reserved/test/non-routable), or kept as a sparse one-off outside any [DIDBlock](didblock.md).

The vast majority of delivered DIDs never become DID rows — they live implicitly as members of their parent block's range. Materialization is on-demand so row counts stay proportional to *interesting* DIDs, not *delivered* DIDs.

| Field | Description |
|-------|-------------|
| `e164` | Full E.164 number (digits only, globally unique) |
| `block` | FK to [DIDBlock](didblock.md), nullable — null for one-offs not in any block |
| `circuit` | FK to `circuits.Circuit`, nullable — usually inherited from `block.circuit`; set directly for one-offs |
| `is_special` | Boolean — reserved, test, or otherwise non-routable |

**Natural key:** `e164`.

**Base class:** `PrimaryModel`.

**Relationships:** Optionally a child of [DIDBlock](didblock.md). Carries an optional [DIDAssignment](didassignment.md) pointing at the routing target. Optionally attached directly to a `circuits.Circuit` for inventory grouping when not part of a block.

::: nautobot_phones.models.DID
    options:
      show_root_heading: false
      heading_level: 2
