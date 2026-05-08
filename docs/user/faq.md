# FAQ

## Why "mirror" instead of authoritative?

CCM is the authoritative source for call-routing config. Nautobot is where
the rest of the network lives (DCIM, IPAM, cabling). This app makes
Nautobot a queryable read-only view of CCM, not a way to push changes
back. If you want bidirectional sync, you'd need a Job that calls AXL
write operations — not in scope for v1.

## Why is the first sync slow?

Two reasons:

1. **Per-phone `getPhone` enrichment** is gated by `enrich_phone_lines`.
   Each call costs ~200-400ms; with 1000 phones that's 5-7 minutes.
   This populates Lines, SpeedDials, BusyLampFields, PhoneServiceUrls,
   and per-line fields (max calls, busy trigger, MWI policy).

2. **Per-gateway `getGateway` enrichment** for analog gateways. Cheap
   per call but rare — one per gateway.

Subsequent syncs without these flags are cheap (single bulk listX calls
for each model).

## Why are my softphones missing the Voice / PC ports?

Softphones (CSF/TCT/BOT/CSK device kinds) don't get DCIM `dcim.Device`
records auto-created — they're software endpoints with no physical
ports or cabling. The `enrich_phone_devices` pass explicitly skips
them. Their Phone record exists; it just doesn't have a Device link.

## Why is `live_login_user` different from `owner_user_id`?

- `owner_user_id` is the AXL-configured *assigned* user.
- `live_login_user` is the user *currently signed in* (from RisPort70).

For shared phones (huddle rooms, lobbies), they often differ. For
individual desk phones they should match — when they don't, it's a
flag that someone's using a phone they don't own.

## Why does my AnalogGateway show 89 ports but the chassis has 144?

Each AnalogPort record is created from a CCM AN4-prefix Phone record.
If a port exists on the chassis but isn't programmed into CCM as an
AN4 phone (e.g. it's configured for SIP via voice-port directly), no
AnalogPort record gets created. Common in mixed-mode gateways.

## Why is my `voice-port 1/0/0` description out of date?

The DN binding shown in interface description comes from CCM data at
sync time. Re-run the sync with `enrich_phone_devices=True` to pick up
DN reassignments.

## Why does an AN4 phone have no DN?

Some CCM clusters create AN4 device records without a Line/DN binding
("ghost records"). They're often artifacts of failed provisioning that
nobody cleaned up. Filter:

```
/plugins/phones/analog-ports/?directory_number__isnull=True
```

…to find candidates for cleanup.

## Why does the LAB cluster have so many BLF templates but no BLFs?

Phone Button Templates allocate button slots; operators have to program
each BLF separately. Templates promising "1LN 3BLF" don't auto-fill the
3 BLF slots. The mismatch is visible:

```python
# Phones with BLF-template but zero BLFs configured
from nautobot_phones.models import Phone
for p in Phone.objects.filter(phone_button_template__icontains='BLF'):
    if p.busy_lamp_fields.count() == 0:
        print(p.device_name)
```

## Can I add a vendor besides Cisco UCM?

Yes — the model graph is vendor-agnostic. Add an adapter under
`integrations/<vendor>/` that subclasses `diffsync.Adapter` and emits
the same DiffSync model objects. See [Extending](../dev/extending.md).

## Why aren't FXS / FXO native Interface types?

Nautobot's core `InterfaceTypeChoices` doesn't include voice port types.
We surface them as **CustomFields** on `dcim.Interface` (`voice_function`
+ `physical_connector`). The interface `type` is set to `Other`. An
upstream proposal to Nautobot to add these as native choices may happen
in the future.
