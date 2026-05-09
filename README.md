# nautobot-app-phones

A [Nautobot](https://nautobot.com) app that mirrors a multi-site campus phone
system (Cisco UCM today; FreePBX planned) into Nautobot as a queryable
inventory: phones, DIDs, trunks, ATAs, analog gateways, dial-plan structure
(partitions, CSSes, route patterns, translation patterns), and the
relationships between them.

> **Status: pre-alpha.** Single-vendor (Cisco UCM via AXL 15.x). Use at your
> own risk; no backwards-compatibility promises until v1.

## What it does

- **Reads** from a CCM cluster's AXL SOAP API + RisPort70 real-time service
- **Writes** to Nautobot's database via the [Nautobot SSoT](https://github.com/nautobot/nautobot-app-ssot) framework
- **Models** ~20 voice-domain object types (PhoneSystem, Partition, CSS, DN, Phone, Line, Trunk, RoutePattern, TranslationPattern, AnalogGateway, etc.)
- **Links** synced Phones and AnalogGateways to Nautobot DCIM `Device` records so cabling, racks, IP addresses, and physical locations work through Nautobot's core
- **Surfaces live status** (Webex/Jabber build version, registration state, currently-signed-in user) from RisPort70

The UI follows CCM's admin-form structure where it makes sense — operators
who jump between Nautobot and CCM see the same field grouping in both
places (Pattern Definition / Calling Party Transformations / Called Party
Transformations on Translation Patterns; Device Information / Protocol
Specific Information on Phones).

## Why mirror, not authoritative?

CCM is the authoritative source for call-routing config; Nautobot is where
the rest of the network's identity lives (DCIM, IPAM, cabling, sites). This
app makes Nautobot a queryable read-only view of CCM, so you can answer
questions like:

- "Show me every Webex Windows install below build 46.4." (live load IDs)
- "Which phones are at site BH01 and registered against pub vs sub?"
- "What FXS port on which gateway serves DN 3875?"
- "Which translation patterns block calls from spammer numbers?"
- "What's the patch panel cable to receptionist Jane's analog phone?"

without polling 1000+ phone web admin pages or scraping CCM admin screens.

## Installation

Install into your Nautobot environment:

```bash
pip install nautobot-app-phones[cisco_ucm]
```

Add to `nautobot_config.py`:

```python
PLUGINS = ["nautobot_phones"]
```

Run migrations:

```bash
nautobot-server migrate
nautobot-server collectstatic
```

## Quick start — sync a Cisco UCM cluster

1. **Create a `SecretsGroup`** in Nautobot Admin with HTTP-access type, USERNAME and PASSWORD secret types pointing at an AXL-enabled service account on your CCM cluster.

2. **Create a `PhoneSystem`** record:
   - Name: a friendly cluster name (e.g. `hq-ccm`)
   - Vendor: `cisco_ucm`
   - Hostname: your CCM publisher's FQDN (e.g. `ccm-pub.example.com`)
   - Secrets group: the one created above
   - Location: a `dcim.Location` for the physical site (optional)

3. **Run the sync job** at *Jobs → SSoT → Cisco UCM → Nautobot*:
   - **Verify TLS**: leave on for production CCM clusters with valid certs
   - **Enrich phone IP**: on (cheap RisPort70 call; populates live status + IPs)
   - **Enrich phone lines**: on for first sync, off for routine re-syncs (slow — ~200-400ms per phone × N phones)
   - **Enrich phone devices**: on to auto-create Nautobot `dcim.Device` records linked to each Phone

   First sync of a 1000-phone cluster takes ~3 minutes for the bulk pass plus ~5 minutes if line/speed-dial/BLF enrichment is enabled.

4. **Browse the results** under *Phones* in the Nautobot top nav.

## Models synced from CCM

| Model | What it represents | Source AXL operation |
|-------|-------------------|----------------------|
| `PhoneSystem` | The CCM cluster itself | (operator-created) |
| `Partition` | A dial-plan partition | `listRoutePartition` |
| `CallingSearchSpace` | A CCM CSS | `listCss` + `getCss` |
| `DirectoryNumber` | A DN (CCM "Line" object) | `listLine` |
| `Phone` | Any registered phone (SEP, CSF, TCT, BOT, CSK, ATA) | `listPhone` + optional `getPhone` |
| `Line` | A DN appearance on a phone button | `getPhone` (nested `lines`) |
| `SpeedDial` | A speed-dial button on a phone | `getPhone` (nested `speeddials`) |
| `BusyLampField` | A BLF watch button on a phone | `getPhone` (nested `busyLampFields`) |
| `PhoneServiceUrl` | An XML service URL on a phone | `getPhone` (nested `services`) |
| `Trunk` | A SIP/PRI/H.323/MGCP trunk | `listSipTrunk` |
| `RoutePattern` | An outbound route pattern | `listRoutePattern` + `getRoutePattern` |
| `RouteList` | A route list (priority list of route groups) | `listRouteList` |
| `RouteGroup` | A route group (load-balanced trunks) | `listRouteGroup` |
| `TranslationPattern` | A digit-translation pattern | `listTransPattern` |
| `AnalogGateway` | A Cisco voice gateway (VG450, VG350, etc.) | `listGateway` + `getGateway` |
| `AnalogPort` | An FXS/FXO port on a gateway | derived from AN4-prefix Phone records |

## Live status (RisPort70)

When `enrich_phone_ip=true`, the sync calls RisPort70's `selectCmDevice` and populates per-phone:

- **`active_load`** — currently-running firmware (SEP) or Webex/Jabber client build (CSF/TCT/BOT). Examples: `Webex_for_Windows-46.4.0.34752`, `sip78xx.14-3-1-0001-60`.
- **`inactive_load`** — rollback-target firmware (relevant for IP phones; equal to active for softphones).
- **`live_login_user`** — who's signed in to the device right now (vs `owner_user_id`, the AXL-configured assignee).
- **`status_reason`** — Cisco's reason code for the current registration state, mapped to human-readable labels (`6 — Authentication failed`, etc.).
- **`live_status_polled_at`** — when the data was captured.

## DCIM linkage

The sync optionally creates Nautobot `dcim.Device` records for each Phone (and matches existing Devices for AnalogGateways). This unlocks:

- **Cabling**: connect phone interfaces to switch ports / patch panels
- **IP addresses**: phone IPs become first-class IPAM records
- **Racks/locations**: phones inherit physical placement from their Device

For analog gateways, the sync materializes **FXS/FXO port Interfaces** named in Cisco IOS voice-port convention (`voice-port 1/0/N`) so DCIM cabling and the gateway's running-config use the same identifiers. Two CustomFields (`voice_function`, `physical_connector`) tag each port as FXS/FXO + RJ-11/RJ-21 since core Nautobot doesn't have these as native interface types.

## Roadmap

| Phase | Status |
|-------|--------|
| Cisco UCM AXL adapter | ✅ shipping |
| RisPort70 live status | ✅ shipping |
| AnalogGateway → DCIM matching | ✅ shipping |
| FreePBX 17 adapter | 🚧 not started |
| CTI port modeling | ✅ shipping (CCX/CER/CTI prefixes) |
| Comprehensive test suite | 🚧 minimal |
| MkDocs documentation site | 🚧 README-only currently |

## Contributing

Issues + PRs welcome on [GitHub](https://git.supported.systems/nautobot-app-phones). Before submitting:

```bash
ruff check src/
ruff format src/
```

## License

Apache 2.0. See [LICENSE](LICENSE).

## Author

Ryan Malloy &lt;ryan@supported.systems&gt;
