"""Top-level Nav Menu entries for nautobot-app-phones.

Adds a 'Phones' tab to the Nautobot top nav, organized into logical
groups: Systems, Endpoints, Numbers, Routing, Dial Plan.
"""

from nautobot.apps.ui import NavMenuGroup, NavMenuItem, NavMenuTab

menu_items = (
    NavMenuTab(
        name="Phones",
        weight=950,
        # Custom Lucide-style icon shipped under static/nautobot_phones/img/.
        # Nautobot treats any value containing '/' as a static-file URL,
        # otherwise it looks up nautobot-icons/<name>.svg from its built-in set
        # (which doesn't include a phone icon).
        icon="nautobot_phones/img/phone.svg",
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
                    NavMenuItem(
                        link="plugins:nautobot_phones:carrier_list",
                        name="Carriers",
                        permissions=["nautobot_phones.view_carrier"],
                    ),
                ),
            ),
            NavMenuGroup(
                name="Endpoints",
                weight=200,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_phones:phone_list",
                        name="Phones",
                        permissions=["nautobot_phones.view_phone"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:analoggateway_list",
                        name="Analog Gateways",
                        permissions=["nautobot_phones.view_analoggateway"],
                    ),
                ),
            ),
            NavMenuGroup(
                name="Numbers",
                weight=300,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_phones:directorynumber_list",
                        name="Directory Numbers",
                        permissions=["nautobot_phones.view_directorynumber"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:didblock_list",
                        name="DID Blocks",
                        permissions=["nautobot_phones.view_didblock"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:did_list",
                        name="DIDs",
                        permissions=["nautobot_phones.view_did"],
                    ),
                ),
            ),
            NavMenuGroup(
                name="Routing",
                weight=400,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_phones:trunk_list",
                        name="Trunks",
                        permissions=["nautobot_phones.view_trunk"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:routepattern_list",
                        name="Route Patterns",
                        permissions=["nautobot_phones.view_routepattern"],
                    ),
                ),
            ),
            NavMenuGroup(
                name="Dial Plan",
                weight=500,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_phones:partition_list",
                        name="Partitions",
                        permissions=["nautobot_phones.view_partition"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:callingsearchspace_list",
                        name="Calling Search Spaces",
                        permissions=["nautobot_phones.view_callingsearchspace"],
                    ),
                ),
            ),
        ),
    ),
)
