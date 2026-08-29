"""Per-company document numbering (invoicing spec §6.3).

Each document type owns its own counter and prefix — `INV-IN-00001`,
`TRF-00001`, `INV-SALE-00001`, `INV-RET-00001` — so an admin can reconcile a
type against their existing paper/Excel books without holes from other types.
"""

from __future__ import annotations

from django.db import transaction

from apps.common.models import DOCUMENT_NUMBER_PREFIXES, DocumentSequence

NUMBER_PADDING = 5


def next_document_number(company_id: int, document_type: str) -> str:
    """Draw the next number for `document_type` within `company_id`.

    Must be called inside a transaction: the sequence row is locked for the rest
    of it, which serialises concurrent issues of the same document type.
    """
    if document_type not in DOCUMENT_NUMBER_PREFIXES:
        raise ValueError(f"Unknown document type: {document_type}")

    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("next_document_number() must run inside a transaction")

    # get_or_create first so a brand-new company doesn't race on the INSERT,
    # then re-read under a row lock to serialise the increment itself.
    DocumentSequence.objects.get_or_create(
        company_id=company_id,
        document_type=document_type,
    )
    sequence = DocumentSequence.objects.select_for_update().get(
        company_id=company_id,
        document_type=document_type,
    )
    sequence.last_number += 1
    sequence.save(update_fields=["last_number", "updated_at"])

    prefix = DOCUMENT_NUMBER_PREFIXES[document_type]
    return f"{prefix}-{sequence.last_number:0{NUMBER_PADDING}d}"
