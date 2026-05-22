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
                        link="plugins:nautobot_phones:sipcircuitprofile_list",
                        name="SIP Circuit Profiles",
                        permissions=["nautobot_phones.view_sipcircuitprofile"],
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
                    NavMenuItem(
                        link="plugins:nautobot_phones:didassignment_list",
                        name="DID Assignments",
                        permissions=["nautobot_phones.view_didassignment"],
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
                        link="plugins:nautobot_phones:routelist_list",
                        name="Route Lists",
                        permissions=["nautobot_phones.view_routelist"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:routegroup_list",
                        name="Route Groups",
                        permissions=["nautobot_phones.view_routegroup"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:routepattern_list",
                        name="Route Patterns",
                        permissions=["nautobot_phones.view_routepattern"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:translationpattern_list",
                        name="Translation Patterns",
                        permissions=["nautobot_phones.view_translationpattern"],
                    ),
                ),
            ),
            NavMenuGroup(
                name="Features",
                weight=425,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_phones:deviceprofile_list",
                        name="Device Profiles",
                        permissions=["nautobot_phones.view_deviceprofile"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:voicemailprofile_list",
                        name="Voicemail Profiles",
                        permissions=["nautobot_phones.view_voicemailprofile"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:callpickupgroup_list",
                        name="Call Pickup Groups",
                        permissions=["nautobot_phones.view_callpickupgroup"],
                    ),
                ),
            ),
            NavMenuGroup(
                name="Hunt",
                weight=450,
                items=(
                    NavMenuItem(
                        link="plugins:nautobot_phones:huntpilot_list",
                        name="Hunt Pilots",
                        permissions=["nautobot_phones.view_huntpilot"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:huntlist_list",
                        name="Hunt Lists",
                        permissions=["nautobot_phones.view_huntlist"],
                    ),
                    NavMenuItem(
                        link="plugins:nautobot_phones:linegroup_list",
                        name="Line Groups",
                        permissions=["nautobot_phones.view_linegroup"],
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
