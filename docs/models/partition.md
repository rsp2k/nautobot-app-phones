# Partition

A routing namespace. Maps to CCM Partition or FreePBX context. DirectoryNumbers, RoutePatterns, and TranslationPatterns belong to a Partition.

| Field | Description |
|-------|-------------|
| `name` | Partition name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `description` | Free-form description |

**Natural key:** (`phone_system`, `name`).

**Base class:** `OrganizationalModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Parent of [DirectoryNumber](directorynumber.md), [RoutePattern](routepattern.md), [TranslationPattern](translationpattern.md). Referenced by [CallingSearchSpace](callingsearchspace.md) via [CSSPartitionMembership](csspartitionmembership.md).

::: nautobot_phones.models.Partition
    options:
      show_root_heading: false
      heading_level: 2
