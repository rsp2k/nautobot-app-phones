# CallingSearchSpace

An ordered collection of Partitions. When a call is placed, the call agent walks the CSS in order, evaluating reachable route patterns from each partition. Order matters for first-match semantics.

| Field | Description |
|-------|-------------|
| `name` | CSS name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `description` | Free-form description |
| `partitions` | M2M through [CSSPartitionMembership](csspartitionmembership.md) |

**Natural key:** (`phone_system`, `name`).

**Base class:** `OrganizationalModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Members are [Partition](partition.md) records via [CSSPartitionMembership](csspartitionmembership.md).

::: nautobot_phones.models.CallingSearchSpace
    options:
      show_root_heading: false
      heading_level: 2
