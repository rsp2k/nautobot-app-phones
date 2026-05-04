"""Top-level Nav Menu entries for nautobot-app-phones.

Adds a 'Phones' tab to the Nautobot top nav, with grouped submenu
items per model. Discovered by Nautobot via the `menu_items` module
attribute.
"""

from nautobot.apps.ui import NavMenuGroup, NavMenuItem, NavMenuTab

menu_items = (
    NavMenuTab(
        name="Phones",
        weight=950,
        groups=(
            NavMenuGroup(
                name="Systems",
                weight=100,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_phones:phonesystem_list",
                        name="Phone Systems",
                        permissions=["nautobot_phones.view_phonesystem"],
                    ),
                ),
            ),
        ),
    ),
)
