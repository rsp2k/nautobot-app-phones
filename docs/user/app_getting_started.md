# Getting Started

A first-sync walkthrough for operators who just installed the app.
Covers both vendors — pick the section that matches your phone system
and skip the other.

## Prerequisites

- Nautobot 3.0+ running and reachable
- The app installed and listed under **Apps > Installed Apps**
- For **Cisco UCM**: AXL credentials (read-only application user
  recommended); the AXL 15.x WSDL bundled with the app at
  `/opt/axl/15.0/AXLAPI.wsdl` (or set `AXL_WSDL_PATH` to override)
- For **FreePBX**: an OAuth2 application created via the FreePBX UI
  (Admin > API > Applications) or via the `fwconsole` CLI (see below)

---

## Cisco UCM: first sync

### 1. Create a SecretsGroup

**Secrets > Secrets Groups > Add**:

- Name: `Cisco UCM Lab`
- Add two associations:
    - Access type `HTTP`, Secret type `Generic Username` → secret name `axl_user`
    - Access type `HTTP`, Secret type `Generic Password` → secret name `axl_pass`

Each `Secret` can use the **environment-variable** provider (read
`AXL_USER` / `AXL_PASS` from the Nautobot process environment) OR the
**plaintext** provider (stored encrypted in the Nautobot DB). Either
works — env-var is preferred for production.

### 2. Create a PhoneSystem

**Apps > Phone Systems > Add**:

- Name: `LAB-CCM`
- Vendor: `Cisco Unified Communications Manager`
- Version: `15.0` (or your cluster's actual version)
- Hostname: bare publisher FQDN (e.g. `ccm-pub.example.com`) — the Job
  prepends `https://` and appends `:8443/axl`
- Secrets group: `Cisco UCM Lab` (from step 1)
- Location: optional but recommended — sets a default `dcim.Location`
  for auto-created Phone devices

### 3. Run the sync (dry-run first)

**Jobs > Cisco UCM -> Nautobot > Run**:

- Phone system: `LAB-CCM`
- Verify TLS: tick if the publisher has a real cert; untick for
  self-signed dev clusters
- Enrich phone IP: tick — RisPort70 is a single bulk call, cheap
- Enrich phone lines: leave unticked for first run (slow on large
  clusters; turn on once you confirm everything else works)
- **Dry run: tick**

Run it. The Job emits a Diff Sync artifact (CSV + JSON) listing every
record it WOULD create, update, or delete. Review the artifact —
specifically the create count by model — before running for real.

### 4. Run for real

Re-run the Job with **Dry run: unticked**. On a 1500-phone cluster,
expect 30s without enrichment, ~3-5 min with `enrich_phone_ip=True`,
5-10 min with `enrich_phone_lines=True`.

### 5. Verify records landed

- **Apps > Phones**: should show every device from the cluster
- **Apps > Directory Numbers**: every DN
- **Apps > Trunks**: every SIP/H323/MGCP trunk
- **Apps > Route Patterns**: every outbound dial-plan match

A second Job run should report `0 creates / 0 updates / 0 deletes` —
that's the idempotency check.

---

## FreePBX: first sync

### 1. Generate OAuth2 credentials

Skip the FreePBX web setup wizard entirely — `fwconsole` mints
credentials directly:

```bash
# inside the FreePBX server (or container)
fwconsole api gql genclientcred <serverip>
```

Output is a JSON blob with `client_id`, `client_secret`,
`token_url`, and `graphql_url`. Capture the `client_id` and
`client_secret`; the URLs are derived from the server IP you passed.

If you haven't installed the API module yet:

```bash
fwconsole ma downloadinstall userman
fwconsole ma downloadinstall api
```

### 2. Create a SecretsGroup

**Secrets > Secrets Groups > Add**:

- Name: `FreePBX Lab`
- Add two associations:
    - Access type `HTTP`, Secret type `Generic Username` → secret value: `client_id` from step 1
    - Access type `HTTP`, Secret type `Generic Password` → secret value: `client_secret` from step 1

For the optional **DB-direct path** (needed for Trunks + Outbound
Routes until FreePBX exposes them via GraphQL), add two more:

- Access type `Database`, Secret type `Generic Username` → MariaDB user
- Access type `Database`, Secret type `Generic Password` → MariaDB password

### 3. Create a PhoneSystem

**Apps > Phone Systems > Add**:

- Name: `LAB-FREEPBX`
- Vendor: `FreePBX`
- Version: `17.0.21`
- Hostname: full URL with scheme (e.g. `http://freepbx.example.com`
  or `https://pbx.example.com`)
- Secrets group: `FreePBX Lab`

For DB-direct trunks/routes, set
`vendor_extras = {"freepbx_db": {"host": "freepbx-mariadb.example.com",
"port": 3306, "name": "asterisk"}}`.

### 4. Run the sync

**Jobs > FreePBX -> Nautobot > Run** with the same dry-run-then-real
flow as the CCM section above. The FreePBX adapter automatically
applies `SKIP_UNMATCHED_DST` so a FreePBX sync never deletes records
from a CCM-vendor PhoneSystem (or vice versa).

### 5. Verify

- **Apps > Phones**: FreePBX extensions appear with `device_kind=other`
  and `device_name` like `PJSIP/1001`
- **Apps > Trunks**: SIP/PJSIP trunks
- **Apps > Route Lists / Route Groups / Route Patterns**: outbound
  routes expanded into our CCM-style RouteList ↔ RouteGroup model

---

## What's next

- Set up a **scheduled Job** (Jobs > [your job] > Edit > Scheduled
  job) for periodic syncs — typical cadence is once per hour for
  small/medium clusters, once per day with `enrich_phone_lines=True`
  for full per-line snapshot.
- Read [Sync Reference](sync_reference.md) for the complete list of
  Job toggles and what each populates.
- Read [External Interactions](external_interactions.md) to brief
  your security team on what flows the app initiates.
