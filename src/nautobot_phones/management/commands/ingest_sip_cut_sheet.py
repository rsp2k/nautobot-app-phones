"""Ingest a SIP cut-sheet JSON into Provider / Circuit / SipCircuitProfile /
DIDBlock / DID records.

Idempotent: re-running with the same inputs upserts via ``get_or_create``.
Contiguous DID runs of >= ``--block-threshold`` consecutive numbers land as
``DIDBlock`` rows; smaller runs land as individual ``DID`` rows with their
``circuit`` FK pointed at the same circuit, so a query like
``DID.objects.filter(circuit=c) | DIDBlock.objects.filter(circuit=c)``
returns the entire inventory either way.

Usage (inside the nautobot-web container)::

    nautobot-server ingest_sip_cut_sheet /tmp/cutsheet.json \
        --circuit-cid SPARKLIGHT-BINGHAM-1 \
        --block-threshold 10 \
        --dry-run
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from nautobot.circuits.models import Circuit, CircuitType, Provider
from nautobot.extras.models import Status

from nautobot_phones.models import DID, DIDBlock, SipCircuitProfile


def _detect_runs(sorted_dids: list[str]) -> Iterable[list[str]]:
    """Group consecutive E.164 strings into runs.

    Assumes input is sorted lexicographically AND zero-padded to equal width
    (true for the cut-sheet format). Yields lists of consecutive strings.
    """
    if not sorted_dids:
        return
    current = [sorted_dids[0]]
    for did in sorted_dids[1:]:
        if int(did) == int(current[-1]) + 1:
            current.append(did)
        else:
            yield current
            current = [did]
    yield current


class Command(BaseCommand):
    """Ingest a SIP cut-sheet JSON file."""

    help = "Ingest a SIP cut-sheet JSON into Provider/Circuit/SipCircuitProfile/DIDBlock/DID rows."

    def add_arguments(self, parser) -> None:
        """Define CLI args."""
        parser.add_argument(
            "json_path",
            type=str,
            help="Path (inside the container) to the cut-sheet JSON file.",
        )
        parser.add_argument(
            "--circuit-cid",
            type=str,
            default=None,
            help=(
                "Circuit ID (Nautobot circuits.Circuit.cid). "
                "Default: derived from carrier + customerName "
                "(e.g. 'SPARKLIGHT-BINGHAM-1')."
            ),
        )
        parser.add_argument(
            "--circuit-type-name",
            type=str,
            default="SIP Trunk",
            help="Name of the CircuitType to use (get-or-create). Default: 'SIP Trunk'.",
        )
        parser.add_argument(
            "--block-threshold",
            type=int,
            default=10,
            help=(
                "Runs of N+ consecutive DIDs become DIDBlocks; smaller runs become "
                "individual DID rows. Default: 10."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Roll back at the end so nothing is written. Use to preview counts.",
        )

    def handle(self, *args, **opts) -> None:
        """Execute the ingest."""
        path = Path(opts["json_path"])
        if not path.exists():
            raise CommandError(f"JSON file not found: {path}")
        data = json.loads(path.read_text())

        carrier = data["carrier"]
        account_number = data.get("accountNumber", "")
        dids = sorted(set(data["dids"]))

        # Derive a default CID if not supplied.
        circuit_cid = opts["circuit_cid"]
        if not circuit_cid:
            slug_customer = (
                data.get("customerName", "UNKNOWN").upper().split()[0]
            )
            circuit_cid = f"{carrier.upper()}-{slug_customer}-1"

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Ingesting {len(dids)} DIDs for {carrier} → {circuit_cid}"
        ))
        self.stdout.write(
            f"  account_number={account_number!r}  "
            f"pilot={data.get('pilotNumber')!r}  "
            f"sessions={data.get('sipSessions')}  "
            f"source={data.get('sourceFile')!r}"
        )

        with transaction.atomic():
            # --- Provider
            provider, created = Provider.objects.get_or_create(
                name=carrier,
                defaults={"account": account_number},
            )
            self._log("Provider", provider, created)
            if (
                not created
                and account_number
                and provider.account != account_number
            ):
                self.stdout.write(self.style.WARNING(
                    f"  ! Provider account_number mismatch — DB has "
                    f"{provider.account!r}, cut-sheet has "
                    f"{account_number!r}. Leaving DB unchanged."
                ))

            # --- CircuitType
            ctype, ct_created = CircuitType.objects.get_or_create(
                name=opts["circuit_type_name"],
            )
            self._log("CircuitType", ctype, ct_created)

            # --- Status: prefer 'Active' if it exists for Circuit, else first available
            status = (
                Status.objects.filter(name="Active")
                .filter(content_types__app_label="circuits",
                        content_types__model="circuit")
                .first()
                or Status.objects.get_for_model(Circuit).first()
            )
            if status is None:
                raise CommandError(
                    "No Status is registered for circuits.Circuit — "
                    "Nautobot's seed data may not have run."
                )

            # --- Circuit
            circuit, c_created = Circuit.objects.get_or_create(
                cid=circuit_cid,
                provider=provider,
                defaults={"circuit_type": ctype, "status": status},
            )
            self._log("Circuit", circuit, c_created)

            # --- SipCircuitProfile
            cut_date_raw = data.get("cutSheetReceivedDate")
            cut_date = (
                date.fromisoformat(cut_date_raw)
                if isinstance(cut_date_raw, str) and cut_date_raw
                else None
            )
            profile_defaults = {
                "sip_sessions": data["sipSessions"],
                "pilot_e164": data.get("pilotNumber", ""),
                "oli_clid_policy": data.get("oliClidPolicy", ""),
                "tech_support": data.get("techSupport", ""),
                "cut_sheet_received_date": cut_date,
                "source_doc": data.get("sourceFile", ""),
                "sensitivity": data.get("sensitivityLevel", ""),
            }
            profile, p_created = SipCircuitProfile.objects.get_or_create(
                circuit=circuit,
                defaults=profile_defaults,
            )
            self._log("SipCircuitProfile", profile, p_created)
            if not p_created:
                # Update any fields the cut-sheet specifies that differ.
                dirty = False
                for field, value in profile_defaults.items():
                    if getattr(profile, field) != value:
                        setattr(profile, field, value)
                        dirty = True
                if dirty:
                    profile.save()
                    self.stdout.write("    ↳ refreshed fields from cut-sheet")

            # --- DID inventory: detect runs, fan out into blocks vs singletons
            threshold = opts["block_threshold"]
            runs = list(_detect_runs(dids))
            block_runs = [r for r in runs if len(r) >= threshold]
            singleton_dids = [d for r in runs if len(r) < threshold for d in r]

            self.stdout.write(self.style.MIGRATE_LABEL(
                f"DID inventory: {len(runs)} runs → "
                f"{len(block_runs)} DIDBlocks (>= {threshold}) + "
                f"{len(singleton_dids)} individual DIDs"
            ))

            blocks_created = blocks_existing = 0
            for run in block_runs:
                _, created = DIDBlock.objects.get_or_create(
                    start_e164=run[0],
                    end_e164=run[-1],
                    provider=provider,
                    defaults={
                        "circuit": circuit,
                        "description": f"Imported from {data.get('sourceFile') or 'cut-sheet'}",
                    },
                )
                if created:
                    blocks_created += 1
                else:
                    blocks_existing += 1

            dids_created = dids_existing = 0
            for e164 in singleton_dids:
                _, created = DID.objects.get_or_create(
                    e164=e164,
                    defaults={"circuit": circuit},
                )
                if created:
                    dids_created += 1
                else:
                    dids_existing += 1

            self.stdout.write(self.style.SUCCESS(
                f"DIDBlocks: {blocks_created} new, {blocks_existing} already existed.\n"
                f"DIDs:      {dids_created} new, {dids_existing} already existed."
            ))

            if opts["dry_run"]:
                self.stdout.write(self.style.WARNING(
                    "\n--dry-run: rolling back the transaction. No data persisted."
                ))
                transaction.set_rollback(True)

    def _log(self, label: str, obj, created: bool) -> None:
        """Print a one-line summary of get_or_create result."""
        verb = self.style.SUCCESS("created") if created else self.style.NOTICE("found")
        self.stdout.write(f"  {verb}  {label}: {obj}")
