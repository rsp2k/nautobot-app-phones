# Uninstall

## Remove from Nautobot

1. Remove `"nautobot_phones"` from the `PLUGINS` list in
   `nautobot_config.py`.

2. Restart Nautobot.

3. Uninstall the package:
   ```bash
   pip uninstall nautobot-app-phones
   ```

## Drop the database tables (optional)

If you want to fully remove the app's data (this is **irreversible**):

```bash
nautobot-server migrate nautobot_phones zero
```

This walks every migration backwards, dropping all `nautobot_phones_*`
tables. Standard Django migrate-to-zero flow.

The CustomFields the app installed on `dcim.Interface` (`voice_function`,
`physical_connector`) are also removed — but if you've populated them on
non-app-managed Interfaces (e.g. operator-tagged ports), those values are
lost. Export first if you want to preserve them.

## What stays behind

By default, **dcim.Device records auto-created for Phones stay in DCIM**
even after uninstall. The CustomFields and the linkage data go away with
the migrate-to-zero, but the Device records themselves are first-class
Nautobot objects and outlive the app. Decide per-customer whether to
clean those up before or after uninstall.
