# DIDAssignment

Links a DID to a target — currently DirectoryNumber or Trunk. The target uses a GenericForeignKey so future targets (voicemail box, IVR, etc.) can be added without column proliferation.

| Field | Description |
|-------|-------------|
| `did` | OneToOne FK to [DID](did.md) |
| `target_type` | FK to ContentType |
| `target_id` | UUID |
| `target` | GenericForeignKey resolved from target_type + target_id |
| `assigned_at` | Timestamp |

**Natural key:** OneToOne `did` + GFK target.

**Base class:** `BaseModel`.

**Relationships:** References [DID](did.md) one-to-one; target is typically a [DirectoryNumber](directorynumber.md) or [Trunk](trunk.md).

::: nautobot_phones.models.DIDAssignment
    options:
      show_root_heading: false
      heading_level: 2
