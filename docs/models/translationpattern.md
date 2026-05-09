# TranslationPattern

A digit-translation pattern applied before route-pattern matching. Matches a dialed number, applies digit transformations (prefix/strip/mask), and re-routes the call through the dial plan.

| Field | Description |
|-------|-------------|
| `pattern` | Dialed-digit pattern |
| `partition` | FK to [Partition](partition.md) |
| `css` | FK to [CallingSearchSpace](callingsearchspace.md) |
| `description` | Free-form |
| `calling_party_transformation_mask` | Calling-party rewrite mask |
| `calling_party_prefix_digits` | Prefix to prepend to caller-ID |
| `digit_discard_instruction` | PreDot / NoDigits / etc. |
| `called_party_transformation_mask` | Called-party rewrite mask |
| `prefix_digits_out` | Prefix to prepend to dialed digits |

**Natural key:** (`partition`, `pattern`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [Partition](partition.md). Distinct from [RoutePattern](routepattern.md) — translation patterns rewrite digits and let the dial plan re-evaluate, no direct destination.

::: nautobot_phones.models.TranslationPattern
    options:
      show_root_heading: false
      heading_level: 2
