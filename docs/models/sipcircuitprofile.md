# SipCircuitProfile

SIP-specific extension on Nautobot's built-in `circuits.Circuit`. One profile per circuit (OneToOne), holding the attributes that the core circuits app doesn't model: concurrent session ceiling, pilot DID for OLI/CLID, outbound-CLID policy, carrier tech-support contact, and cut-sheet provenance fields.

![SIP Circuit Profiles list view](../assets/screenshots/sip-circuit-profiles-list.png)

The split is deliberate: the carrier delivery (provider, cid, status, install date, commit rate, terminations) is exactly what `circuits.Circuit` already does. SIP semantics — sessions, pilot, CLID policy — don't belong on a generic circuit and aren't shared with MPLS / Internet / cross-connect circuits. The OneToOne extension keeps both shapes clean.

Created lazily — a `circuits.Circuit` doesn't need a profile unless it carries SIP. Deleting the parent Circuit cascades and removes the profile.

| Field | Description |
|-------|-------------|
| `circuit` | OneToOne to `circuits.Circuit` (cascade delete) |
| `pilot_e164` | Main/pilot number, digits only. Often the OLI/CLID for outbound calls. |
| `sip_sessions` | Concurrent SIP session ceiling sold by the carrier. Hard cap across the entire DID pool. |
| `oli_clid_policy` | Outbound CLID policy (e.g. `Public, set to Pilot`, `Pass-through DID`, `Anonymous`). |
| `tech_support` | Carrier tech-support contact as printed on the cut sheet. Free text — phone, email, or URL. |
| `cut_sheet_received_date` | Date the carrier delivered the cut sheet / config. Distinct from `circuits.Circuit.install_date`. |
| `source_doc` | Filename or reference for the source cut sheet (e.g. `cut-sheet-2026-05-22.xlsx`). |
| `sensitivity` | Sensitivity tag (`public`, `internal`, `confidential`). |
| `vendor_extras` | Carrier-specific fields not modeled as columns. Adapter-driven. |

**Natural key:** `circuit`.

**Base class:** `PrimaryModel`.

**Relationships:**

- OneToOne to `circuits.Circuit` via `circuit`. The reverse accessor is `circuit.sip_profile` — Nautobot's auto-detail-rendering surfaces it as a clickable row at the top of the Circuit detail page automatically.
- Indirectly groups [DIDBlock](didblock.md) and [DID](did.md) records that have `circuit=<same circuit>`. The detail page renders these as a [DID heatmap](../user/did_heatmap.md).
- Indirectly groups [Trunk](trunk.md) records (PBX-side egress) that terminate the same circuit via `Trunk.circuit`.

## Detail view

The SIP Circuit Profile detail page renders three sections:

1. **Carrier delivery** — the field table above, surfaced as a vertical key-value panel.
2. **Vendor-specific config (long-tail)** — the `vendor_extras` JSON, rendered as a single-line key:value summary.
3. **DID heatmap** — a full-width visualization grouping every DID attached to this circuit into 10×10 grids per hundred-block, color-coded by routing status. See [DID heatmap](../user/did_heatmap.md) for the reading guide.

## Ingest

For real-world cut sheets, use the [`ingest_sip_cut_sheet`](../user/cut_sheet_ingest.md) management command — it creates the Provider / Circuit / SipCircuitProfile / DIDBlock / DID records in one idempotent pass.

::: nautobot_phones.models.SipCircuitProfile
    options:
      show_root_heading: false
      heading_level: 2
