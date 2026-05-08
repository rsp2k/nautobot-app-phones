# Nautobot Phones

A Nautobot app that mirrors a multi-site campus phone system into Nautobot
as a queryable inventory: phones, DIDs, trunks, ATAs, analog gateways,
dial-plan structure (partitions, CSSes, route patterns, translation
patterns), and the relationships between them.

!!! warning "Pre-alpha"
    Currently single-vendor (Cisco UCM via AXL 15.x). Use at your own risk;
    no backwards-compatibility promises until v1.

## Why this app

Cisco Unified Communications Manager (CCM) is the authoritative source for
call-routing config. Nautobot is where the rest of your network lives
(DCIM, IPAM, cabling, sites, racks). This app makes Nautobot a queryable
**read-only mirror** of CCM, so you can answer questions like:

- "Show me every Webex Windows install below build 46.4." (live load IDs)
- "Which phones are at site BH01 and registered against pub vs sub?"
- "What FXS port on which gateway serves DN 3875?"
- "Which translation patterns block calls from spammer numbers?"
- "What's the patch-panel cable to receptionist Jane's analog phone?"

…without RDP'ing into 1000+ phones or scraping CCM admin pages.

## Documentation

- [User Guide](user/app_overview.md) — what's synced, how to read it, common queries
- [Administrator Guide](admin/install.md) — installation, configuration, upgrade
- [Developer Guide](dev/contributing.md) — extending, contributing, architecture

## Quick links

- **Source**: [git.supported.systems/nautobot-app-phones](https://git.supported.systems/nautobot-app-phones)
- **Issue tracker**: same repo
- **Author**: Ryan Malloy &lt;ryan@supported.systems&gt;
- **License**: Apache 2.0
