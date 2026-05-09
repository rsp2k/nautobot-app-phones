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

## Adapter API choice: GraphQL

FreePBX 17 exposes three API surfaces:

1. **Legacy REST** under `/admin/api/api/...` — XML, deprecated
2. **GraphQL** at `/admin/api/api/graphql` — modern, schema-introspectable,
   OAuth2 client-credentials auth (RECOMMENDED for adapter)
3. **Direct DB** against MariaDB — last resort if GraphQL doesn't expose
   what we need

GraphQL requires the "API" + "Application" modules from FreePBX module
admin. Once installed, you create an Application that gets a
`client_id` + `client_secret` for OAuth2 token requests.

## Seeding workflow (planned)

1. **Create admin user** — `fwconsole userman:addUser admin admin` or
   complete web wizard once.
2. **Install API + Application modules** via `fwconsole ma install api`
   + `fwconsole ma install pm2` + `fwconsole ma install application`.
3. **Create OAuth Application** in admin UI with scopes `read:extensions`,
   `read:trunks`, `read:routes`. Capture `client_id` + `client_secret`
   into `.env` as `FREEPBX_CLIENT_ID` / `FREEPBX_CLIENT_SECRET`.
4. **Seed minimum test data** for adapter parity testing:
   - 5 PJSIP extensions (e.g. 1001-1005 with display names)
   - 1 SIP trunk pointing at a fictional ITSP
   - 1 outbound route mapping `9NXXXXXXXXX` → trunk
   - 1 ring group at extension 600 fanning to 1001+1002+1003
   - 1 voicemail box on extension 1001
5. **Verify GraphQL queries** return seeded records before writing
   adapter code:
   ```graphql
   { allExtensions { extensionNumber displayName email } }
   { allTrunks { name techType } }
   ```

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
