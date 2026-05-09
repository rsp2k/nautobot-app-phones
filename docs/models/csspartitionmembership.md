# CSSPartitionMembership

Through-table joining CallingSearchSpace and Partition. The `priority` column controls evaluation order — lower numbers come first.

| Field | Description |
|-------|-------------|
| `css` | FK to [CallingSearchSpace](callingsearchspace.md) |
| `partition` | FK to [Partition](partition.md) |
| `priority` | Integer — lower numbers evaluated first |

**Natural key:** (`css`, `partition`).

**Base class:** `BaseModel`.

**Relationships:** Pure junction model — no list/detail views of its own; renders as a nested panel on CallingSearchSpace detail.

::: nautobot_phones.models.CSSPartitionMembership
    options:
      show_root_heading: false
      heading_level: 2
