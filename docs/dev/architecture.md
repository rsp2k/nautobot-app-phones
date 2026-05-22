# Architecture Decisions

Brief log of design choices made during pre-1.0. Knowing *why* helps
future contributors avoid re-litigating settled questions.

## ADR-001: Mirror role, not authoritative

CCM is the source of truth for call-routing. This app reads from CCM and
writes to Nautobot. We don't push Nautobot edits back to CCM.

**Why**: AXL writes are a much larger surface area (validation rules,
ordering constraints, transactional semantics). Read-only delivers 95%
of the operational value (queryable inventory) at 20% of the complexity.

## ADR-002: `vendor_extras` JSONField on every PrimaryModel

Each PrimaryModel carries a `vendor_extras: JSONField` for vendor-specific
fields not modeled as columns.

**Why**:

- Avoids schema explosion as CCM adds fields per release
- Different vendors (Cisco UCM vs FreePBX) have wildly different field
  sets — JSONField is the lowest-friction shared layer
- Doesn't conflict with Nautobot's `_custom_field_data` namespace,
  which is for user-driven custom fields

**Tradeoff**: Long-tail fields are less filterable than first-class
columns. Operationally-important fields (Device Pool, Webex build, MAC,
etc.) get explicit columns; everything else flows through.

## ADR-003: Phone is keyed by `device_name`, not MAC

CCM uses `device_name` (e.g. `SEPCAFEBABE0001`, `CSFJDOE`,
`AN4ABC0DEF0101`) as the canonical identifier across all phone-class
prefixes. Softphones (CSF/TCT/BOT) have no MAC address — they're
software endpoints with synthetic identifiers.

The unique constraint is `(phone_system, device_name)`. MAC is optional,
populated only for SEP/ATA prefixes where it's encoded in the device_name.

## ADR-004: `Phone.model` and `Phone.location` are properties, not fields

Both read through the linked `dcim.Device`:

- `Phone.model` → `self.device.device_type.model`
- `Phone.location` → `self.device.location`

**Why**: Nautobot's DCIM is the authority for hardware identity and
physical placement. Storing them on Phone too would conflate "what CCM
calls this thing" with "what the inventory system calls this thing"
and create drift opportunities.

**Tradeoff**: Phones without a linked Device return None/empty. The
adapter stashes the AXL `model` string in `vendor_extras['axl_model']`
so the device-creation pass can find/create the right DeviceType.

## ADR-005: AnalogGateway → Device matches existing, never creates

Phone-Device sync auto-creates Devices because each Phone is uniquely
identified by MAC. AnalogGateway-Device sync only *matches* existing
Devices because gateway hardware is owned by network discovery
(CDP/LLDP/manual import), not CCM.

Three matching strategies attempted in order: exact name, MAC-base hint
in serial/name/comments, unique-DeviceType in cluster location.

## ADR-006: FXS interface naming uses Cisco IOS convention

Each AnalogPort in CCM gets materialized as a `dcim.Interface` named
`voice-port S/SS/P` (e.g. `voice-port 1/0/0`). The same identifier
appears in the gateway's running-config, so DCIM cabling and the
gateway's `show running-config` use matching names.

The CCM port-index integer is bit-packed: bits 9-11 = slot, bit 8 =
sub-slot, bits 0-7 = port (1-based; IOS displays as port-1). Empirically
verified against multiple chassis configs.

## ADR-007: Voice CustomFields, not native Interface types

Nautobot core's `InterfaceTypeChoices` doesn't include FXS/FXO/RJ-21.
Rather than monkey-patching the choice set (fragile when upstream
changes), the app declares two CustomFields on `dcim.Interface` via
migration:

- `voice_function`: select [`fxs`, `fxo`]
- `physical_connector`: select [`rj-11`, `rj-21`]

Filterable via `?cf_voice_function=fxs`. Set programmatically by the
sync; operators can override per-port via the Interface UI.

## ADR-008: DataSource (not DataTarget) SSoT job

The Nautobot SSoT framework has two base classes: `DataSource` (external
→ Nautobot) and `DataTarget` (Nautobot → external). We use DataSource
because CCM IS the source.

This is the reverse of the sibling Hudu plugin (which uses DataTarget
because Hudu is the destination for Nautobot data).

## ADR-009: GFK-aware DiffSync base class

Some through-tables in our schema use a `GenericForeignKey` so a single
row can target multiple model types:

- `RouteGroupMember.target` — `Trunk` OR `AnalogGateway`
- `DIDAssignment.target` — `DirectoryNumber` OR `Trunk` (future: also Voicemail)

`nautobot_ssot.contrib.NautobotModel` resolves regular FKs through
natural-key chains (`trunk__name` → `Trunk.objects.get(name=...)`)
but doesn't know how to walk a GFK: the `(target_type, target_id)` pair
has no schema-level link to a single related model class.

**Solution**: `GFKNautobotModel` (in `diffsync/models/gfk.py`) overrides
two extension points in the framework:

1. **Write path** — `_update_obj_with_parameters` pops virtual identifier
   fields (`target_kind`, `target_name`, optionally
   `target_partition__name` / `target_phone_system__name`), resolves
   them to `(ContentType, target_id)` via a per-kind queryset lookup,
   sets them on the ORM instance, then delegates the rest of the FK
   machinery + `validated_save()` to super.

2. **Read path** — the Nautobot adapter's `_handle_single_parameter`
   override short-circuits virtual `target_*` field names BEFORE the
   framework calls `_meta.get_field()` on them (which would raise
   `FieldDoesNotExist`). Extraction logic lives in
   `GFKNautobotModel._extract_gfk_virtual_field`, which dispatches
   on `target_type.model` to per-kind reader callables.

**Per-kind configuration** (set on each concrete subclass):

| Attribute | Purpose |
|-----------|---------|
| `_gfk_targets` | `{kind: (app_label, model_name)}` — ContentType resolution |
| `_gfk_scope_from` | Identifier field whose value scopes default `name`-based lookups by `phone_system__name` |
| `_gfk_lookups` | `{kind: callable(target_name, parameters) -> filter_dict}` — for kinds whose natural key isn't `name` (e.g. DirectoryNumber's composite `extension`/`partition`/`phone_system`) |
| `_gfk_reads` | `{kind: callable(target_obj) -> {virtual_field: value}}` — complement of `_gfk_lookups` for the read path |

**Why**: A custom DiffSync model class for each GFK would force every
contributor to re-derive the same ContentType + dispatch logic. Encoding
it once in a base class means new GFK models declare *what* their target
kinds are and *how* each kind's natural key resolves, but never have to
override `create`/`update`/`delete`/`get_from_db`.

**Tradeoff**: Virtual identifier fields (`target_kind`, `target_name`,
etc.) don't appear on the ORM model — they're computed on demand. They
ARE filterable through the DiffSync representation but not directly via
Django ORM queries. For UI/REST filtering on a GFK target's name, use
the ORM-side `ContentType` filter (`target_type__model="trunk"`) plus
a join through `target_id`.

See `diffsync/models/gfk.py` for the implementation and
`tests/test_diffsync_gfk.py` for the contract.
