# PhoneSystem

The cluster root. One record per CCM cluster, FreePBX install, or other
phone system being mirrored.

| Field | Description |
|-------|-------------|
| `name` | Unique identifier (operator-chosen, e.g. `LAB-CCM`) |
| `vendor` | `cisco_ucm` / `freepbx` / `asterisk` |
| `version` | Free-form version string (e.g. `15.0.1`, `17.0.21`) |
| `hostname` | FQDN or full URL of the publisher / admin endpoint |
| `secrets_group` | FK to `extras.SecretsGroup` (HTTP USERNAME + PASSWORD slots; FreePBX adds DATABASE for trunks DB-direct) |
| `location` | FK to `dcim.Location` (nullable) |
| `delete_policy` | JSONField — per-model delete policy (`flag` / `delete` / `ignore`) |
| `last_synced_at` | DateTime of last successful sync |
| `vendor_extras` | JSONField — long-tail vendor config not modeled as columns |

**Natural key:** `name` (cluster-wide unique).

**Base class:** `PrimaryModel`.

**Relationships:** Parent of [Partition](partition.md),
[CallingSearchSpace](callingsearchspace.md), [Trunk](trunk.md),
[Phone](phone.md), [DeviceProfile](deviceprofile.md), and most other
records (denormalized FK on records that don't already inherit it via
their partition).

::: nautobot_phones.models.PhoneSystem
    options:
      show_root_heading: false
      heading_level: 2
