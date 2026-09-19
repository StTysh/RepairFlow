"""Shared hashing and webhook-receipt dedupe helpers.

Webhook uniqueness key (docs/16): (provider, event_type, conversation_id,
event_timestamp, body_sha256). Domain-level dedupe for reports/proposals
lives next to the records it protects (services.py, executor.py); this
module only owns the generic hashing primitive and the receipt ledger.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WebhookReceiptModel, new_uuid


def payload_hash(data: dict | str | bytes) -> str:
    if isinstance(data, bytes):
        raw = data
    elif isinstance(data, str):
        raw = data.encode("utf-8")
    else:
        raw = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def record_webhook_receipt(
    session: AsyncSession, *, provider: str, event_type: str, conversation_id: str | None,
    event_timestamp: str, raw_body: bytes, envelope: dict,
) -> tuple[WebhookReceiptModel, bool]:
    """Returns (receipt, is_new). A duplicate delivery returns the original
    receipt with is_new=False so the caller can ack 200 without reprocessing."""
    body_hash = payload_hash(raw_body)
    existing = (
        await session.execute(
            select(WebhookReceiptModel).where(
                WebhookReceiptModel.provider == provider,
                WebhookReceiptModel.event_type == event_type,
                WebhookReceiptModel.conversation_id == conversation_id,
                WebhookReceiptModel.event_timestamp == event_timestamp,
                WebhookReceiptModel.body_sha256 == body_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    receipt = WebhookReceiptModel(
        id=new_uuid(), provider=provider, event_type=event_type, conversation_id=conversation_id,
        event_timestamp=event_timestamp, body_sha256=body_hash, payload=envelope,
        processing_status="RECEIVED", received_at=datetime.now(timezone.utc),
    )
    session.add(receipt)
    await session.flush()
    return receipt, True
