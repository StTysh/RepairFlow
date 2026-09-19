"""TavilyResearchAdapter: bounded, source-linked contractor discovery
(docs/12). Only ever constructed when settings.tavily_live is True (see
main.py's lifespan) -- FixtureResearchAdapter in executor.py is the
always-available no-credentials default.

This module makes no database call of its own -- it only performs the
network search and maps the response into schema objects. Persistence
happens in executor.py's _apply_research_result, exactly like
MockBookingConnector.book() never touches the caller's transaction either
(docs: "do not hold a DB transaction across any network call").

Docs/12 budgets, applied verbatim:
- POST https://api.tavily.com/search, bearer auth, basic depth, max 5
  results, no synthesized answer.
- Eight-second request budget; one read-only retry on a transient error.
- Bounded excerpts; no crawl/map/follow-up browsing -- search only.
- Tenant name, phone number and repair transcript never enter the query;
  only trade and postal area.
- Normalize duplicate domains into one candidate; never auto-merge
  different companies that happen to share a trading name (a shared name
  across distinct domains stays as separate candidates).
- Unsupported values are null, never guessed -- phone/service_area are
  left None unless the search snippet made an explicit, attributable claim.
- On no results or a provider failure (after the one retry), preserve the
  attempt and return an empty candidate list with a warning; never
  fabricate a result or silently drop the research attempt.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.models import new_uuid
from app.schemas import (
    ContractorCandidate,
    ContractorSearchResult,
    EvidenceRef,
    Provenance,
    ResearchSnapshot,
    SourceType,
    Trade,
    VerificationStatus,
    WebEvidence,
)

_SEARCH_URL = "https://api.tavily.com/search"
_REQUEST_TIMEOUT_SECONDS = 8.0
_MAX_RESULTS = 5
_MAX_EXCERPT_CHARS = 400

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_query(trade: Trade, postcode: str) -> str:
    """No tenant name, phone number or repair transcript ever enters this
    string (docs/12) -- only the trade and postal area."""
    trade_label = trade.value.replace("_", " ").lower()
    return f"{trade_label} contractor {postcode} service area contact"


def _normalized_domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _looks_like_emergency_claim(title: str, excerpt: str) -> bool:
    haystack = f"{title} {excerpt}".lower()
    return "emergency" in haystack


class TavilyResearchAdapter:
    """Drop-in implementation of executor.ResearchAdapter's Protocol,
    calling the real Tavily search API."""

    async def search(self, case_id: str, trade: Trade, postcode: str) -> ContractorSearchResult:
        settings = get_settings()
        query = _build_query(trade, postcode)
        requested_at = _utcnow()

        raw_results: list[dict] = []
        provider_request_id: str | None = None
        warnings: list[str] = []

        last_error: Exception | None = None
        for attempt in range(2):  # one read-only retry on a transient error
            try:
                async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                    response = await client.post(
                        _SEARCH_URL,
                        headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
                        json={
                            "query": query,
                            "search_depth": "basic",
                            "max_results": _MAX_RESULTS,
                            "include_answer": False,
                        },
                    )
                response.raise_for_status()
                data = response.json()
                raw_results = data.get("results", [])[:_MAX_RESULTS]
                provider_request_id = data.get("request_id")
                last_error = None
                break
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning("Tavily search attempt %s failed: %s", attempt + 1, exc)
                continue

        completed_at = _utcnow()

        if last_error is not None:
            # A provider failure must not fabricate a result -- preserve the
            # attempt (empty results) and surface a warning instead.
            warnings.append(f"Tavily request failed after retry: {last_error}")
            return ContractorSearchResult(
                research=ResearchSnapshot(
                    id=new_uuid(), case_id=case_id, query=query, provider="TAVILY",
                    provider_request_id=provider_request_id, requested_at=requested_at,
                    completed_at=completed_at, result_urls=[], results=[], provenance=Provenance.LIVE,
                ),
                candidates=[], warnings=warnings,
            )

        web_evidence: list[WebEvidence] = []
        domain_groups: dict[str, list[dict]] = {}
        for item in raw_results:
            url = item.get("url") or ""
            if not url:
                continue
            excerpt = (item.get("content") or "")[:_MAX_EXCERPT_CHARS]
            web_evidence.append(
                WebEvidence(
                    url=url, title=item.get("title") or url, excerpt=excerpt,
                    retrieved_at=completed_at, provider_score=item.get("score"),
                )
            )
            domain_groups.setdefault(_normalized_domain(url), []).append(item)

        if not raw_results:
            warnings.append("Tavily returned no results for this trade/postcode search.")

        snapshot_id = new_uuid()
        candidates: list[ContractorCandidate] = []
        for domain, items in domain_groups.items():
            if not domain:
                continue
            # Highest-scoring result in the domain group names the candidate.
            best = max(items, key=lambda i: i.get("score") or 0.0)
            evidence = [
                EvidenceRef(
                    source_type=SourceType.WEB, source_id=new_uuid(), locator=item.get("url"),
                    observed_at=completed_at, provenance=Provenance.LIVE,
                )
                for item in items
            ]
            claimed_emergency = None
            for item in items:
                if _looks_like_emergency_claim(item.get("title") or "", item.get("content") or ""):
                    claimed_emergency = True
                    break
            candidates.append(
                ContractorCandidate(
                    id=new_uuid(), case_id=case_id, research_id=snapshot_id,
                    name=best.get("title") or domain, trades=[trade],
                    website=best.get("url"), phone=None, service_area=None,
                    claimed_emergency_service=claimed_emergency, evidence=evidence,
                    verification_status=VerificationStatus.UNVERIFIED,
                )
            )

        snapshot = ResearchSnapshot(
            id=snapshot_id, case_id=case_id, query=query, provider="TAVILY",
            provider_request_id=provider_request_id, requested_at=requested_at, completed_at=completed_at,
            result_urls=[w.url for w in web_evidence], results=web_evidence, provenance=Provenance.LIVE,
        )

        return ContractorSearchResult(research=snapshot, candidates=candidates, warnings=warnings)
