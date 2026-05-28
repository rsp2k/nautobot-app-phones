"""Per-model ``delete_policy`` dispatch — Phase 6 of the v1 plan.

A vanilla DiffSync delete pass writes "vendor record disappeared" all
the way down to a hard ORM delete. That's the right default for most
synced data, but it's the wrong default for two real operator scenarios:

1. **Partial-coverage source adapters.** If the FreePBX adapter doesn't
   yet model CallPickupGroups, a sync would otherwise delete every
   pickup group from Nautobot just because the source returned none.
   Operators want ``"callpickupgroup": "ignore"`` to leave those records
   alone until the adapter catches up.

2. **Audit trail for orphaned records.** Sometimes a vendor record really
   IS gone, but the operator wants to investigate before the row
   disappears from Nautobot (especially for Phones — physical hardware
   doesn't vanish without a reason). ``"phone": "flag"`` adds the
   ``phones-orphaned`` Tag and writes ``_orphaned_at`` to vendor_extras
   so the record is filterable + the timestamp survives across runs,
   but the record itself stays put.

The policy lives on ``PhoneSystem.delete_policy`` (JSONField) as a
``{model_name: action}`` dict. ``model_name`` is the DiffSync model's
``_modelname`` (snake_case); ``action`` is one of ``delete`` (default),
``ignore``, ``flag``. Missing entries default to ``delete`` — same
behavior as before this stage, so empty policy = backward-compatible.

This module ships:

* ``DeletePolicy`` — the three action constants
* ``PolicyAwareNautobotModel`` — base class whose ``delete()`` consults
  ``self.adapter.delete_policy``
* ``ORPHANED_TAG_NAME`` — the canonical tag string + a helper to
  ``get_or_create`` it with the right content-types attached
"""

from datetime import datetime, timezone
from typing import ClassVar

from nautobot_ssot.contrib import NautobotModel


ORPHANED_TAG_NAME = "phones-orphaned"


class DeletePolicy:
    """Action constants used by the per-model policy dict."""

    DELETE = "delete"  # default — hard delete the ORM record
    IGNORE = "ignore"  # log + skip; record stays in Nautobot
    FLAG = "flag"      # add orphaned Tag + _orphaned_at timestamp; keep record

    ALL = frozenset({DELETE, IGNORE, FLAG})


def _get_or_create_orphaned_tag(model_class) -> "Tag":  # noqa: F821 -- lazy import
    """Return the ``phones-orphaned`` Tag, creating it if absent.

    Lazily creates with the requesting model's ContentType already
    attached, so the first flag on each model class self-bootstraps
    the tag's allowed content types. Subsequent flags on other model
    classes extend the content-types list (Tag is M2M to ContentType
    via TagsTaggableManagerEX in Nautobot).
    """
    from django.contrib.contenttypes.models import ContentType
    from nautobot.extras.models import Tag

    tag, _ = Tag.objects.get_or_create(
        name=ORPHANED_TAG_NAME,
        defaults={
            "description": (
                "Source record disappeared but the Nautobot record was "
                "preserved per PhoneSystem.delete_policy. See vendor_extras"
                "['_orphaned_at'] for the timestamp."
            ),
        },
    )
    ct = ContentType.objects.get_for_model(model_class)
    if ct not in tag.content_types.all():
        tag.content_types.add(ct)
    return tag


class PolicyAwareNautobotModel(NautobotModel):
    """DiffSync model base whose ``delete()`` honors ``adapter.delete_policy``.

    Policy lookup chain:

    1. ``self.adapter.delete_policy.get(self._modelname, "delete")``
    2. Action one of ``delete``/``ignore``/``flag``
    3. Unknown actions fall back to ``delete`` with a warning log
       (defensive against typos in the JSONField — better to delete
       than to silently leave records when the operator clearly
       intended SOMETHING non-default).

    ``delete`` is the default so an empty policy dict preserves the
    pre-Phase-6 behavior exactly.
    """

    # Class attribute so subclasses can opt out of policy if needed
    # (e.g. through-tables where flagging makes no sense — the FK
    # would cascade-protect the parent anyway).
    _supports_delete_policy: ClassVar[bool] = True

    def delete(self):
        """Dispatch delete via ``self.adapter.delete_policy``."""
        if not self._supports_delete_policy:
            return super().delete()

        policy_map = getattr(self.adapter, "delete_policy", {}) or {}
        action = policy_map.get(self._modelname, DeletePolicy.DELETE)

        if action == DeletePolicy.IGNORE:
            return self._policy_ignore(action)
        if action == DeletePolicy.FLAG:
            return self._policy_flag(action)
        if action != DeletePolicy.DELETE:
            self._policy_log_unknown(action)
        # Default — delete the ORM record and the DiffSync representation.
        return super().delete()

    # -- Per-action handlers ---------------------------------------------

    def _policy_ignore(self, action: str):
        """Log + tell DiffSync the record is gone from its store, but
        leave the ORM row alone. Returns the DiffSyncModel.delete()
        result (which removes the record from the in-memory store),
        without touching the database."""
        logger = self._get_logger()
        if logger:
            logger.info(
                f"delete_policy[{self._modelname}]={action!r} — skipping ORM "
                f"delete for {self.get_unique_id()}",
            )
        # Skip the framework's ORM delete; advance the DiffSync state only.
        from diffsync import DiffSyncModel
        return DiffSyncModel.delete(self)

    def _policy_flag(self, action: str):
        """Add the ``phones-orphaned`` Tag + write ``_orphaned_at`` into
        ``vendor_extras`` JSON. Record itself is preserved.

        Idempotent: a record already flagged keeps the original
        ``_orphaned_at`` (don't bump on every sync). Re-syncing a
        previously-flagged record into a live state is a separate
        flow (would need to clear the tag + key).
        """
        logger = self._get_logger()
        obj = None
        try:
            obj = self.get_from_db()
        except Exception as exc:  # noqa: BLE001 - log + fall back to default
            if logger:
                logger.warning(
                    f"delete_policy[{self._modelname}]={action!r} — couldn't "
                    f"resolve ORM record for {self.get_unique_id()}: {exc}",
                )
            from diffsync import DiffSyncModel
            return DiffSyncModel.delete(self)

        # Only models with a ``vendor_extras`` field can carry the
        # ``_orphaned_at`` marker. Models without it just get the Tag
        # (queryable via Tag membership instead).
        ve_field = getattr(obj, "vendor_extras", None)
        if ve_field is not None and isinstance(ve_field, dict):
            if "_orphaned_at" not in ve_field:
                ve_field["_orphaned_at"] = datetime.now(timezone.utc).isoformat()
        # Tag the record. Only models that support tagging (PrimaryModel-
        # based) can carry tags; defensive hasattr check.
        if hasattr(obj, "tags"):
            try:
                tag = _get_or_create_orphaned_tag(type(obj))
                obj.tags.add(tag)
            except Exception as exc:  # noqa: BLE001 — log + continue
                if logger:
                    logger.warning(
                        f"delete_policy[{self._modelname}]=flag — couldn't add "
                        f"{ORPHANED_TAG_NAME} tag to {self.get_unique_id()}: {exc}",
                    )
        try:
            obj.save()
        except Exception as exc:  # noqa: BLE001
            if logger:
                logger.warning(
                    f"delete_policy[{self._modelname}]=flag — save failed for "
                    f"{self.get_unique_id()}: {exc}",
                )
        if logger:
            logger.info(
                f"delete_policy[{self._modelname}]={action!r} — flagged "
                f"{self.get_unique_id()} (vendor record gone, ORM record preserved)",
            )
        from diffsync import DiffSyncModel
        return DiffSyncModel.delete(self)

    def _policy_log_unknown(self, action: str) -> None:
        logger = self._get_logger()
        if logger:
            logger.warning(
                f"Unknown delete_policy action {action!r} for "
                f"{self._modelname}; falling back to 'delete'. "
                f"Valid actions: {sorted(DeletePolicy.ALL)}.",
            )

    def _get_logger(self):
        """Return the Job logger if the adapter has one; otherwise None.

        DiffSync flows can run standalone (e.g. tests) without a Job
        attached — log calls are best-effort in that case.
        """
        adapter = getattr(self, "adapter", None)
        job = getattr(adapter, "job", None)
        return getattr(job, "logger", None) if job else None
