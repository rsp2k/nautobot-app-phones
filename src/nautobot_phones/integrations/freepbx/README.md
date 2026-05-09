# FreePBX 17 integration

Source-side adapter for the FreePBX 17 phone system. Mirrors the shape
of `cisco_ucm/` so operators familiar with one adapter can navigate the
other — both load into the same vendor-agnostic Nautobot phones schema.

## Files

| File | Role |
|------|------|
| `client.py` | OAuth2 + GraphQL HTTP client (`httpx`-based) |
| `adapter.py` | `FreePBXSourceAdapter` — DiffSync source side |
| `jobs.py` | `FreePBXDataSource` — Nautobot SSoT Job entry point |

## API choice: GraphQL over `/admin/api/api/graphql`

FreePBX 17 has three callable surfaces; we use GraphQL because it's
schema-introspectable and stable across patch releases. The legacy
`/admin/api/api/...` REST endpoints are XML-based and deprecated.
Direct DB queries against MariaDB are reserved as a fallback when
GraphQL doesn't expose what we need.

Authentication is OAuth2 `client_credentials` — operators create an
"Application" in **Admin > API > Applications** and the resulting
`client_id` + `client_secret` get stored in the PhoneSystem's
SecretsGroup as the standard HTTP USERNAME / PASSWORD pair (we reuse
those slot names so the SecretsGroup schema is identical for CCM and
FreePBX — no per-vendor vocabulary to memorize).

## Mapping (FreePBX → unified)

| FreePBX | Our model | Notes |
|---------|-----------|-------|
| Extension (PJSIP/SIP/IAX) | `DirectoryNumber` + `Phone(device_kind="other")` | DN holds the extension number; Phone holds the SIP technology + device_name (e.g. `PJSIP/1001`) |
| Voicemail box | `VoicemailProfile` (synthesized per ext, or shared default) | FreePBX vmail is per-extension, no separate "profile" table |
| Trunk | `Trunk` | trunk_type from FreePBX `tech` (sip/pjsip/iax2/dahdi) |
| Outbound Route | `RoutePattern` (target_trunk) | match patterns map directly |
| Inbound Route | `RoutePattern` (incoming) | DID + CID match; destination is RingGroup/Queue/Ext |
| Ring Group | `HuntPilot` + `HuntList` + `LineGroup` | Group extension = HuntPilot pattern; member ext list = LineGroupMember |
| Pickup Group | `CallPickupGroup` | direct match — both vendors model this the same |
| Custom Context | `Partition` | FreePBX context ≈ CCM partition |
| `internal` settings (codec etc.) | `DeviceProfile` (synthesized) | minimal — most FreePBX deployments don't have multiple |

## What we don't model in v1

- **Queue** — would need a new Queue model (defer)
- **Time Condition / Time Group** — defer until we have a multi-vendor pattern
- **Conferences** — no equivalent CCM concept yet
- **Paging/intercom** — defer
- **Fax** — defer
- **Custom dialplan injection** — out of scope; operators edit raw
  Asterisk dialplan rather than via FreePBX UI

## Stage status

- [x] **Stage 1**: dev container up (`make freepbx-up`)
- [x] **Stage 2**: admin reachable, seeding plan documented
- [x] **Stage 3**: scaffold (this file + client/adapter/jobs)
- [ ] **Stage 4**: extensions → DirectoryNumber + Phone
- [ ] **Stage 5+**: trunks, routes, ring groups, voicemail, pickup groups

See `development/freepbx/SEED_PLAN.md` for the test-data + auth setup
plan that needs to land before stage 4 can run end-to-end.
