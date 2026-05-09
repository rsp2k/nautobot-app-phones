# DirectoryNumber

An extension within a partition. The vendor-side identifier callers dial to reach a phone, hunt pilot, or other endpoint.

| Field | Description |
|-------|-------------|
| `extension` | Dialed digits (e.g. `3001`, `12005551212`) |
| `partition` | FK to [Partition](partition.md) |
| `phone_system` | FK to [PhoneSystem](phonesystem.md), denormalized |
| `alerting_name` | Display name shown on the called party |
| `voicemail_profile` | FK to [VoicemailProfile](voicemailprofile.md), nullable |
| `vendor_extras` | JSONField — vendor-specific per-DN config |

**Natural key:** (`partition`, `extension`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [Partition](partition.md). Referenced by [Line](line.md) (button appearances), [AnalogPort](analogport.md) (FXS bindings), [HuntPilot](huntpilot.md), [LineGroupMember](linegroupmember.md), [CallPickupGroupMember](callpickupgroupmember.md), [DIDAssignment](didassignment.md).

::: nautobot_phones.models.DirectoryNumber
    options:
      show_root_heading: false
      heading_level: 2
