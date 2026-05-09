# CallPickupGroup

An extension that picks up ringing peers — both CCM and FreePBX implement this with the same shape. A user dials the group's pickup pattern (e.g. `*8`) and the system answers whichever member-DN is currently ringing.

| Field | Description |
|-------|-------------|
| `name` | Group name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `pattern` | Extension/digits dialed to invoke pickup |
| `partition` | FK to [Partition](partition.md), nullable |
| `description` | Free-form |
| `vendor_extras` | JSONField |
| `members` | M2M through [CallPickupGroupMember](callpickupgroupmember.md) |

**Natural key:** (`phone_system`, `name`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Members are [DirectoryNumbers](directorynumber.md).

::: nautobot_phones.models.CallPickupGroup
    options:
      show_root_heading: false
      heading_level: 2
