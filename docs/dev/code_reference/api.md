# REST API + GraphQL Reference

The app exposes a full REST API at `/api/plugins/phones/` and registers
GraphQL types for every model. Both surfaces use Nautobot's standard
auth (token + permission classes) — no per-endpoint config required.

## REST API serializers

::: nautobot_phones.api.serializers
    options:
      show_root_heading: false
      members_order: source

## REST API viewsets

::: nautobot_phones.api.views
    options:
      show_root_heading: false
      members_order: source

## GraphQL types

::: nautobot_phones.graphql.types
    options:
      show_root_heading: false
      members_order: source

## URL routing

::: nautobot_phones.api.urls
    options:
      show_root_heading: false

::: nautobot_phones.urls
    options:
      show_root_heading: false
