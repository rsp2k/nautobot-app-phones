"""GenericForeignKey-aware DiffSync base class.

``nautobot_ssot.contrib.NautobotModel`` resolves regular FKs through
natural-key chains (e.g. ``trunk__name``) but doesn't know how to walk
a GenericForeignKey — the ``target_type`` (ContentType) + ``target_id``
(UUID) pair on the ORM model has no schema-level link to a single
related model class.

``GFKNautobotModel`` extends the contrib base with two extension points:

* **Write path** — overrides ``_update_obj_with_parameters`` to pop the
  virtual identifier fields (``target_kind``, ``target_name``) from the
  parameter dict, resolve them to a concrete ContentType + queryset
  lookup, and set ``obj.target_type`` + ``obj.target_id`` directly on
  the ORM instance *before* the framework's ``validated_save()`` runs.

* **Read path** — concrete subclasses pair with a small
  ``_handle_single_parameter`` override on the Nautobot adapter that
  short-circuits ``target_kind`` / ``target_name`` (which aren't real
  ORM fields, so the framework's default ``_meta.get_field()`` lookup
  would raise ``FieldDoesNotExist``). See the adapter for that piece.

Subclasses declare:

* ``_gfk_targets``: ``{kind_string: (app_label, model_name)}`` mapping
  used for ContentType resolution. Constrains what values of
  ``target_kind`` are valid — anything else raises at create time.

* ``_gfk_scope_from``: optional identifier field name (e.g.
  ``"route_group__phone_system__name"``) whose value scopes the target
  lookup. When set, the target queryset is filtered by
  ``phone_system__name=<value>`` to disambiguate names that aren't
  globally unique. ``None`` means the target's ``name`` field is
  globally unique (rare in practice).

* ``_gfk_lookups``: optional ``{kind_string: callable(target_name,
  parameters) -> dict}`` map for kinds whose natural key isn't a
  simple ``name`` field. The callable returns the queryset filter
  to apply (e.g. ``{"partition__name": "...", "extension": "..."}``
  for DirectoryNumber). Kinds NOT in this map use the default
  name-based lookup, optionally scoped by ``_gfk_scope_from``.

* ``_gfk_reads``: complement to ``_gfk_lookups`` for the read path —
  ``{kind_string: callable(target_obj) -> dict[virtual_field, value]}``
  extracts the virtual-identifier values (e.g. ``target_name``,
  ``target_partition__name``) from the ORM target object during
  Nautobot-side adapter load. Kinds NOT in this map fall back to
  ``{"target_name": target.name}``.
"""

from typing import Any, Callable, ClassVar, Optional

from diffsync.exceptions import ObjectCrudException
from django.contrib.contenttypes.models import ContentType
from nautobot_ssot.contrib import NautobotModel

# Type alias for the per-kind lookup signature: receives the
# ``target_name`` identifier value plus the rest of the DiffSync
# parameter dict (so the callable can pull e.g. ``target_partition__name``
# out of the same record). Returns a queryset filter dict that
# uniquely identifies the target ORM object.
GFKLookupFunc = Callable[[str, dict], dict[str, Any]]


class GFKNautobotModel(NautobotModel):
    """DiffSync model base for ORM models with a single GenericForeignKey ``target``."""

    # Mapping of ``target_kind`` string → ``(app_label, model_name)`` for
    # ContentType resolution. Subclasses MUST override.
    _gfk_targets: ClassVar[dict[str, tuple[str, str]]] = {}

    # Identifier field whose value scopes the GFK target queryset by
    # ``phone_system__name``. ``None`` disables scoping. Only consulted
    # when the default name-based lookup is in use (i.e. the kind is
    # not in ``_gfk_lookups``).
    _gfk_scope_from: ClassVar[Optional[str]] = None

    # Optional per-kind lookup override for targets whose natural key
    # isn't a single ``name`` field. Each callable receives
    # (target_name, parameters) and returns a queryset filter dict.
    # Kinds NOT in this map fall back to ``{"name": target_name}``
    # scoped by ``_gfk_scope_from``.
    _gfk_lookups: ClassVar[dict[str, GFKLookupFunc]] = {}

    # Optional per-kind extractor for the read path. Each callable
    # receives the ORM target object and returns a dict of virtual
    # field values to populate on the DiffSync record. Kinds NOT in
    # this map fall back to ``{"target_name": target.name}``.
    _gfk_reads: ClassVar[dict[str, Callable[[Any], dict[str, Any]]]] = {}

    @classmethod
    def _extract_gfk_virtual_field(cls, database_object, parameter_name) -> Any:
        """Compute the value of a virtual GFK field from the ORM object.

        ``target_kind`` is always derived from the ContentType. Other
        ``target_*`` fields are pulled from the per-kind extractor
        registered in ``_gfk_reads`` — or, as a fallback, from
        ``target.name`` (which covers the common case where the GFK
        target's natural key IS its name field).

        Returns an empty string for missing/unresolvable values to
        keep DiffSync's diff stable; raising here would crash the
        whole adapter load over one bad row.
        """
        if parameter_name == "target_kind":
            return database_object.target_type.model
        target = database_object.target
        if target is None:
            return ""
        kind = database_object.target_type.model
        if kind in cls._gfk_reads:
            return cls._gfk_reads[kind](target).get(parameter_name, "")
        if parameter_name == "target_name":
            return getattr(target, "name", "")
        return ""

    @classmethod
    def _update_obj_with_parameters(cls, obj, parameters, adapter):
        """Resolve GFK virtual fields then delegate to the framework.

        The framework's ``_update_obj_with_parameters`` stages FK lookups,
        resolves them, and calls ``validated_save()``. Our overlay runs
        BEFORE that path so ``target_type`` + ``target_id`` are set on
        the ORM instance by the time ``validated_save()`` enforces NOT
        NULL on those columns.
        """
        target_kind = parameters.pop("target_kind", None)
        target_name = parameters.pop("target_name", None)

        if target_kind is not None and target_name is not None:
            ct, target_id = cls._resolve_gfk_target(
                target_kind, target_name, parameters,
            )
            obj.target_type = ct
            obj.target_id = target_id

        super()._update_obj_with_parameters(obj, parameters, adapter)

    @classmethod
    def _resolve_gfk_target(cls, target_kind, target_name, parameters):
        """Look up ContentType + target object ID for (kind, name).

        ``parameters`` is the still-intact attrs/ids dict from the caller —
        we read the scope identifier from it without mutating, since
        ``_update_obj_with_parameters`` still needs the rest of the chain
        to set the parent FK.
        """
        try:
            app_label, model_name = cls._gfk_targets[target_kind]
        except KeyError as e:
            raise ObjectCrudException(
                f"Unknown GFK target kind {target_kind!r}; "
                f"expected one of {sorted(cls._gfk_targets)}"
            ) from e

        try:
            ct = ContentType.objects.get(app_label=app_label, model=model_name)
        except ContentType.DoesNotExist as e:
            raise ObjectCrudException(
                f"ContentType not found for {app_label}.{model_name}"
            ) from e

        target_model = ct.model_class()
        # Per-kind lookup override wins; otherwise default to name-based
        # lookup, optionally scoped by ``_gfk_scope_from``.
        if target_kind in cls._gfk_lookups:
            lookup: dict = cls._gfk_lookups[target_kind](target_name, parameters)
        else:
            lookup = {"name": target_name}
            if cls._gfk_scope_from:
                scope_value = parameters.get(cls._gfk_scope_from)
                if scope_value:
                    lookup["phone_system__name"] = scope_value

        try:
            target = target_model.objects.get(**lookup)
        except target_model.DoesNotExist as e:
            raise ObjectCrudException(
                f"GFK target lookup failed: "
                f"{target_model.__name__}.objects.get({lookup})"
            ) from e
        except target_model.MultipleObjectsReturned as e:
            raise ObjectCrudException(
                f"GFK target lookup ambiguous: "
                f"{target_model.__name__}.objects.get({lookup}) returned >1"
            ) from e

        return ct, target.id
