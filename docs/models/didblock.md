# DIDBlock

An E.164 number range delivered by a carrier (Nautobot's `circuits.Provider`). Validated for digits-only endpoints, equal lengths, start ≤ end. Individual DIDs are NOT materialized until they're assigned — see [DID](did.md).

For inventory attached to a specific carrier circuit (e.g. a SIP trunk), point `circuit` at the [Circuit](https://docs.nautobot.com/projects/core/en/latest/user-guide/core-data-model/circuits/circuit/) that delivers it. The companion [SipCircuitProfile](sipcircuitprofile.md) extends that Circuit with SIP-specific attributes (session count, pilot, etc.).

| Field | Description |
|-------|-------------|
| `start_e164` | First E.164 number in range (digits only, zero-padded to a fixed length) |
| `end_e164` | Last E.164 number in range (same length as `start_e164`) |
| `provider` | FK to `circuits.Provider` — the carrier |
| `circuit` | FK to `circuits.Circuit`, nullable — the specific delivery (e.g. a SIP trunk) |
| `location` | FK to `dcim.Location`, nullable |
| `phone_system` | FK to [PhoneSystem](phonesystem.md), nullable |
| `description` | Free-form description |
| `size` | Computed property — `int(end) - int(start) + 1` |

**Natural key:** (`start_e164`, `end_e164`, `provider`).

**Base class:** `PrimaryModel`.

**Relationships:** Parent of [DID](did.md) records that have been materialized. Belongs to a `circuits.Provider`; optionally attached to a `circuits.Circuit` (which may carry a [SipCircuitProfile](sipcircuitprofile.md)).

::: nautobot_phones.models.DIDBlock
    options:
      show_root_heading: false
      heading_level: 2
