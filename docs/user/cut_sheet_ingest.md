# SIP Cut Sheet Ingest

The `ingest_sip_cut_sheet` Django management command reads a vendor SIP cut-sheet JSON file and creates the matching records: `circuits.Provider`, `circuits.Circuit`, [SipCircuitProfile](../models/sipcircuitprofile.md), [DIDBlock](../models/didblock.md), and [DID](../models/did.md) rows in one pass.

Idempotent — re-running with the same input upserts via `get_or_create`. Safe to run repeatedly as the cut sheet is updated by the carrier.

## Usage

Inside the `nautobot-web` container:

```bash
nautobot-server ingest_sip_cut_sheet /path/to/cut-sheet.json \
    --circuit-cid SPARKLIGHT-BINGHAM-1 \
    --block-threshold 10 \
    --dry-run
```

## Flags

| Flag | Default | Purpose |
|---|---|---|
| `json_path` (positional) | — | Absolute path inside the container to the cut-sheet JSON file. |
| `--circuit-cid` | derived from `carrier` + `customerName` | The Circuit ID. If omitted, computed as `f"{CARRIER}-{CUSTOMER}-1"` from the JSON (uppercased, customer-truncated to first word). |
| `--circuit-type-name` | `SIP Trunk` | Name of the `circuits.CircuitType` to use (get-or-create). |
| `--block-threshold` | `10` | Runs of N+ consecutive DIDs become `DIDBlock` rows; smaller runs become individual `DID` rows. See [the trade-off](#block-threshold) below. |
| `--dry-run` | off | Roll back the whole transaction at the end. Use to preview counts before committing. |

## JSON shape

```json
{
  "carrier": "Acme Telecom",
  "customerName": "Example Hospital Main Campus",
  "accountNumber": "ACME-EXAMPLE-001",
  "pilotNumber": "8005550100",
  "sipSessions": 24,
  "oliClidPolicy": "Public, set to Pilot",
  "techSupport": "1-800-555-0199 (ext 2)",
  "cutSheetReceivedDate": "2026-05-22",
  "sourceFile": "cut-sheet-2026-05-22.xlsx",
  "sensitivityLevel": "public",
  "dids": [
    "8005552000",
    "8005552001",
    "8005552002",
    "..."
  ]
}
```

| JSON key | Lands on |
|---|---|
| `carrier` | `circuits.Provider.name` |
| `accountNumber` | `circuits.Provider.account` |
| `customerName` | informational only (used to derive the default Circuit CID); attach to the Circuit's `tenant` separately if needed |
| `pilotNumber` | `SipCircuitProfile.pilot_e164` |
| `sipSessions` | `SipCircuitProfile.sip_sessions` |
| `oliClidPolicy` | `SipCircuitProfile.oli_clid_policy` |
| `techSupport` | `SipCircuitProfile.tech_support` |
| `cutSheetReceivedDate` | `SipCircuitProfile.cut_sheet_received_date` (ISO 8601 date) |
| `sourceFile` | `SipCircuitProfile.source_doc` |
| `sensitivityLevel` | `SipCircuitProfile.sensitivity` |
| `dids[]` | sorted, deduplicated, then run-detected — see below |

A full reference file lives at `docs/examples/example-sip-cut-sheet.json` and reproduces every screenshot in these docs.

## DID compression: how runs become blocks

The DID list is sorted, deduplicated, then walked to detect contiguous runs of consecutive E.164 numbers. Runs of `--block-threshold` or more land as one `DIDBlock` row spanning the full range. Smaller runs (and isolated one-offs) become individual `DID` rows with the `circuit` FK set so they remain queryable as part of the same inventory.

For a real-world 1,757-DID hospital cut sheet at the default threshold, compression typically lands around 50–60%: a couple dozen `DIDBlock` rows + a few hundred individual `DID` rows.

### Block threshold

The trade-off the threshold controls:

| Threshold | Effect |
|---|---|
| **Low (3–5)** | Catches small port-cluster runs as blocks; fewer individual `DID` rows. Cheapest storage, but touching a single number inside a small block still requires materializing it as a `DID` row. |
| **Default (10)** | Sensible balance for typical hospital / enterprise inventories — captures fat carrier-delivered chunks as blocks, leaves individually-ported numbers as discrete rows. |
| **High (50+)** | Only fat chunks get compressed; almost everything stays materialized. Useful if you plan to assign most DIDs individually and want flat row visibility. |

The choice doesn't affect query results — `DIDBlock.objects.filter(circuit=c)` and `DID.objects.filter(circuit=c)` together cover the same set of numbers regardless. It only affects row count.

## Idempotence

Every record is created via `get_or_create` keyed on its natural key (or natural-key equivalent):

- `Provider` by name
- `CircuitType` by name
- `Circuit` by (cid, provider)
- `SipCircuitProfile` by circuit (OneToOne — only one can exist)
- `DIDBlock` by (start_e164, end_e164, provider)
- `DID` by e164

So re-running with the same JSON does nothing on the second pass. Re-running with an *updated* JSON adds new DIDs/blocks without disturbing the existing ones; it does NOT delete DIDs that have been removed from the source. To handle drift, prefer running the same `--dry-run` first, then manually deleting any orphans.

## End-to-end example

The example dataset at `docs/examples/example-sip-cut-sheet.json` (385 DIDs across 4 NPA-NXX prefixes) ingests like this:

```bash
$ nautobot-server ingest_sip_cut_sheet /tmp/example.json --circuit-cid=ACME-EXAMPLE-1
Ingesting 385 DIDs for Acme Telecom → ACME-EXAMPLE-1
  account_number='ACME-EXAMPLE-001'  pilot='8005550100'  sessions=24  source='example-sip-cut-sheet.json'
  created  Provider: Acme Telecom
  created  CircuitType: SIP Trunk
  created  Circuit: ACME-EXAMPLE-1
  created  SipCircuitProfile: ACME-EXAMPLE-1 (SIP, 24 sessions)
DID inventory: 53 runs → 8 DIDBlocks (>= 10) + 45 individual DIDs
DIDBlocks: 8 new, 0 already existed.
DIDs:      45 new, 0 already existed.
```

The resulting SipCircuitProfile detail page renders the [DID heatmap](did_heatmap.md) visualization of the same inventory.
