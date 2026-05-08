# Extending

## Adding a new vendor adapter

The model graph is vendor-agnostic. To add a new phone-system source
(e.g. FreePBX, Asterisk, BroadWorks):

1. Create `src/nautobot_phones/integrations/<vendor>/`:
    - `client.py` — vendor-specific API wrapper (use `httpx` or whatever
      transport fits)
    - `adapter.py` — `<Vendor>SourceAdapter(diffsync.Adapter)` with
      `load()` walking your vendor's API and emitting DiffSync objects
    - `jobs.py` — `<Vendor>DataSource(nautobot_ssot.jobs.base.DataSource)`

2. Map vendor concepts to our unified model:
    - phone-system extension → `DirectoryNumber`
    - context → `Partition`
    - outbound-route-group → `CallingSearchSpace`
    - device → `Phone`
    - trunk → `Trunk`
    - outbound-route → `RoutePattern`

3. Register the job in `src/nautobot_phones/jobs.py`.

4. Document the vendor in [Compatibility Matrix](../admin/compatibility_matrix.md)
   and add adapter-specific notes to [User Guide](../user/app_overview.md).

## Adding new fields to existing models

Schema changes live in `src/nautobot_phones/models/`. The standard flow:

1. Edit the model
2. `nautobot-server makemigrations nautobot_phones --no-input`
3. Review the generated migration
4. `nautobot-server migrate`
5. Update the matching DiffSync class in `diffsync/models/base.py` to
   include the new field in `_attributes` and as a typed annotation
6. Update the source adapter to populate the field
7. Add a test in `tests/test_models.py` or `tests/test_diffsync_schema.py`

## Adding a new phone device kind

The dispatch table in `CUCMSourceAdapter._PHONE_KINDS_BY_PREFIX` maps CCM
device-name prefixes to `device_kind` values. To add a new kind:

1. Add to `PhoneDeviceKindChoices` in `src/nautobot_phones/choices.py`
2. Add the prefix → kind mapping to `_PHONE_KINDS_BY_PREFIX`
3. Decide whether the device-creation pass should auto-create DCIM
   Devices for it (update `HARDWARE_KINDS` in `devices.py` if so)
4. Add a test in `test_adapter_dispatch.py`

## Adding new RIS reason codes

Update `_RIS_STATUS_REASONS` in `src/nautobot_phones/views.py`. The dict
is also used by `_status_reason_human` — the `test_all_documented_codes_resolve`
test verifies the lookup table stays internally consistent.

## Adding voice port types (e.g. RJ-45 for T1, BRI)

Two CustomFields drive port semantics: `voice_function` and
`physical_connector`. To add a new value:

1. Update the CustomFieldChoice records via a new data migration in
   `src/nautobot_phones/migrations/`
2. Update `_voice_port_metadata()` in `devices.py` to detect the new
   module products that map to the new value
3. Document the addition in this guide
