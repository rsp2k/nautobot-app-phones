# FreePBX dev container — seed plan

## What's running

- `freepbx` container: FreePBX 17.0.21 + Asterisk 21 + PHP 8.2
- `freepbx-mariadb` container: MariaDB 10.11 holding the `asterisk` and `asteriskcdrdb` databases
- Reachable from `nautobot-web` via Docker DNS at `http://freepbx/admin/`
  (the caddy-network alias resolves to the container's caddy-net IP)
- First-boot installation done via `make freepbx-install` — populates
  `/var/www/html/` and the `asterisk` DB schema

## What's NOT done yet

The container is fresh — no admin user, no extensions, no trunks. Web
admin at `/admin/config.php` shows "Welcome to FreePBX Administration"
and walks through a setup wizard. We can drive that wizard programmatically
or bypass it.

## Adapter API choice: GraphQL (CONFIRMED)

The GraphQL endpoint is `POST /admin/api/api/gql` (note: `/gql`, not
`/graphql` — the `genclientcred` command reports both URLs but only the
`/gql` one actually serves; `/graphql` returns 403 even with a valid
token). Auth is OAuth2 `client_credentials`.

The `api` and `userman` modules need to be installed (run
`make freepbx-bootstrap` — automated). Then `fwconsole api gql
genclientcred <serverip>` mints OAuth2 credentials without going
through the web setup wizard. **No admin-user creation needed** — the
fwconsole CLI runs as root and bypasses the auth path entirely.

### Real schema field names (confirmed against 17.0.21 + api 17.0.6)

Top-level query fields are prefixed `fetchAll*` or `all*`, NOT just `all*`:

  - `fetchAllExtensions` (not `allExtensions`)
  - `fetchAllCoreDevices` — physical SIP peers (separate from extensions)
  - `fetchVoiceMail` — voicemail boxes
  - `allInboundRoutes`, `inboundRoute`
  - `fetchAllRecordings`
  - `allMusiconholds`

The Extension type wraps a Connection-style envelope:

```graphql
fetchAllExtensions {
  totalCount status message
  extension {                  # <- lowercase, the actual list
    id extensionId tech
    user { extension name voicemail outboundCid ringtimer ... }
    coreDevice { dial devicetype description emergencyCid }
  }
}
```

`coreDevice.dial` is `"PJSIP/1001"` etc. — exactly the device_name
shape we want for our `Phone` records. FreePBX prepends the SIP
technology to the extension number for us.

### Trunks and outbound routes (NOT yet exposed)

The default `api` module 17.0.6 doesn't include trunks or outbound-
routes in its GraphQL schema. They require additional API modules
(`outroutes`, `core-trunks`, etc.) that ship separately. Stage-5 work.

## Bootstrap workflow (automated)

1. `make freepbx-init` — generate Docker secrets from .env passwords
2. `make freepbx-up` — start FreePBX + MariaDB containers
3. `make freepbx-install` — `php install` to populate /var/www/html + DB
4. `make freepbx-bootstrap` — install userman + api modules + generate
   OAuth2 credentials (prints client_id + client_secret to stdout)
5. Stash credentials in `.env` as `FREEPBX_LAB_CLIENT_ID` /
   `FREEPBX_LAB_CLIENT_SECRET`, OR create a Nautobot SecretsGroup

## Test-data seeding (manual, optional)

Use the GraphQL `addExtension` mutation to seed test extensions:

```graphql
mutation {
  addExtension(input: {
    extensionId: "1001",
    name: "Alice Engineering",
    email: "alice@example.com",
    tech: "pjsip",
    outboundCid: "<5551001>"
  }) { status message }
}
```

For multi-extension seeds in stage 5+ we'll add a Makefile target that
loops over a YAML/CSV of extensions to create.

## Mapping (FreePBX → Nautobot phones)

| FreePBX | Our model | Notes |
|---------|-----------|-------|
| Extension (PJSIP/SIP/IAX) | `DirectoryNumber` + `Phone(device_kind="other")` | DN holds the extension number; Phone holds the SIP technology + device_name (e.g. `PJSIP/1001`) |
| Voicemail box | `VoicemailProfile` (one synthesized per ext, or shared default) | FreePBX vmail is per-extension, no separate "profile" table |
| Trunk | `Trunk` | trunk_type from FreePBX `tech` (sip/pjsip/iax2/dahdi) |
| Outbound Route | `RoutePattern` (target_trunk) | match patterns map directly |
| Inbound Route | `RoutePattern` (incoming) | DID + CID match; destination is RingGroup/Queue/Ext |
| Ring Group | `HuntPilot` + `HuntList` + `LineGroup` | Group extension = HuntPilot pattern; member ext list = LineGroupMember |
| Queue | (defer — would need a Queue model) | Phase 6+ |
| Time Condition | (defer) | Phase 6+ |
| Custom Context | `Partition` | FreePBX context ≈ CCM partition |
| Outbound Route Group | `CallingSearchSpace` | rough analogue |
| Pickup Group | `CallPickupGroup` | direct match — both vendors model this the same |
| `internal` settings (codec etc.) | `DeviceProfile` (synthesized) | minimal — most FreePBX deployments don't have multiple profiles |

## What we'll skip in v1

- Asterisk dialplan custom context manipulation (out of scope — operators
  edit raw dialplan rather than via FreePBX UI)
- Conferences (no equivalent CCM concept yet)
- Paging/intercom groups (defer until we have a multi-vendor pattern)
- Fax (defer)
