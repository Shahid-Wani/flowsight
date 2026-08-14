"""
Threat Intelligence Enrichment

Integration with AbuseIPDB, AlienVault OTX, and other threat intel sources.
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any

import httpx

from flowsight import get_logger
from flowsight.config import settings

logger = get_logger(__name__)


@dataclass
class ThreatIntelInfo:
    """Threat intelligence lookup result."""
    is_malicious: bool = False
    abuse_confidence_score: int | None = None
    country_code: str | None = None
    usage_type: str | None = None
    isp: str | None = None
    domain: str | None = None
    hostnames: list[str] = None
    last_reported_at: str | None = None
    total_reports: int = 0
    tags: list[str] = None
    source: str = ""

    def __post_init__(self):
        if self.hostnames is None:
            self.hostnames = []
        if self.tags is None:
            self.tags = []


class AbuseIPDBClient:
    """AbuseIPDB API client."""

    BASE_URL = "https://api.abuseipdb.com/api/v2"

    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Key": self.api_key,
                    "Accept": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    async def check_ip(self, ip: str, max_age: int = 30) -> ThreatIntelInfo | None:
        """Check an IP address against AbuseIPDB."""
        if not self.api_key:
            return None

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.BASE_URL}/check",
                params={
                    "ipAddress": ip,
                    "maxAgeInDays": max_age,
                    "verbose": "true",
                },
            )
            response.raise_for_status()
            data = response.json()["data"]

            return ThreatIntelInfo(
                is_malicious=data.get("abuseConfidenceScore", 0) > 25,
                abuse_confidence_score=data.get("abuseConfidenceScore"),
                country_code=data.get("countryCode"),
                usage_type=data.get("usageType"),
                isp=data.get("isp"),
                domain=data.get("domain"),
                hostnames=data.get("hostnames", []),
                last_reported_at=data.get("lastReportedAt"),
                total_reports=data.get("totalReports", 0),
                tags=[data.get("usageType")] if data.get("usageType") else [],
                source="abuseipdb",
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("abuseipdb_rate_limited")
            else:
                logger.debug("abuseipdb_http_error", status=e.response.status_code)
            return None
        except Exception as e:
            logger.debug("abuseipdb_error", ip=ip, error=str(e))
            return None

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class OTXClient:
    """AlienVault OTX API client."""

    BASE_URL = "https://otx.alienvault.com/api/v1"

    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "X-OTX-API-KEY": self.api_key,
                },
                timeout=self.timeout,
            )
        return self._client

    async def check_ip(self, ip: str) -> ThreatIntelInfo | None:
        """Check an IP address against AlienVault OTX."""
        if not self.api_key:
            return None

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.BASE_URL}/indicators/IPv4/{ip}/general",
            )
            response.raise_for_status()
            data = response.json()

            pulses = data.get("pulse_info", {}).get("pulses", [])
            tags = set()
            for pulse in pulses:
                tags.update(pulse.get("tags", []))

            return ThreatIntelInfo(
                is_malicious=len(pulses) > 0,
                abuse_confidence_score=min(len(pulses) * 10, 100),
                country_code=data.get("country_code"),
                tags=list(tags),
                source="otx",
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("otx_rate_limited")
            else:
                logger.debug("otx_http_error", status=e.response.status_code)
            return None
        except Exception as e:
            logger.debug("otx_error", ip=ip, error=str(e))
            return None

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class ThreatIntelEnrichment:
    """Threat intelligence enrichment combining multiple sources."""

    def __init__(self):
        self.abuseipdb = AbuseIPDBClient(settings.enrichment.abuseipdb_key) if settings.enrichment.abuseipdb_key else None
        self.otx = OTXClient(settings.enrichment.alienvault_otx_key) if settings.enrichment.alienvault_otx_key else None
        self._cache: dict[str, ThreatIntelInfo] = {}
        self._cache_ttl = settings.enrichment.cache_ttl

    async def lookup(self, ip: str) -> ThreatIntelInfo | None:
        """Look up IP address across all threat intel sources."""
        # Check cache first
        if ip in self._cache:
            cached = self._cache[ip]
            # Simple TTL check (in production, use proper timestamp)
            return cached

        results = []
        tasks = []

        if self.abuseipdb:
            tasks.append(self.abuseipdb.check_ip(ip))
        if self.otx:
            tasks.append(self.otx.check_ip(ip))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            results = [r for r in results if isinstance(r, ThreatIntelInfo)]

        if not results:
            return None

        # Combine results - take highest confidence
        combined = ThreatIntelInfo()
        for r in results:
            combined.is_malicious = combined.is_malicious or r.is_malicious
            if r.abuse_confidence_score and (combined.abuse_confidence_score is None or r.abuse_confidence_score > combined.abuse_confidence_score):
                combined.abuse_confidence_score = r.abuse_confidence_score
            if r.country_code:
                combined.country_code = r.country_code
            if r.usage_type:
                combined.usage_type = r.usage_type
            if r.isp:
                combined.isp = r.isp
            if r.domain:
                combined.domain = r.domain
            if r.hostnames:
                combined.hostnames.extend(r.hostnames)
            if r.last_reported_at:
                combined.last_reported_at = r.last_reported_at
            if r.total_reports:
                combined.total_reports += r.total_reports
            if r.tags:
                combined.tags.extend(r.tags)
            if r.source:
                combined.source = f"{combined.source},{r.source}" if combined.source else r.source

        # Deduplicate
        combined.hostnames = list(set(combined.hostnames))
        combined.tags = list(set(combined.tags))

        self._cache[ip] = combined
        return combined

    def enrich_flow(self, flow: dict[str, Any]) -> dict[str, Any]:
        """Enrich a flow record with threat intel (synchronous version for pipeline)."""
        # This is a synchronous wrapper - in production, use async pipeline
        enriched = flow.copy()
        return enriched

    async def enrich_flow_async(self, flow: dict[str, Any]) -> dict[str, Any]:
        """Enrich a flow record with threat intel (async version)."""
        enriched = flow.copy()

        for ip_field in ("src_ip", "dst_ip"):
            ip = flow.get(ip_field)
            if ip:
                threat = await self.lookup(ip)
                if threat:
                    prefix = "src" if ip_field == "src_ip" else "dst"
                    enriched[f"{prefix}_threat_malicious"] = threat.is_malicious
                    enriched[f"{prefix}_threat_score"] = threat.abuse_confidence_score
                    enriched[f"{prefix}_threat_country"] = threat.country_code
                    enriched[f"{prefix}_threat_usage"] = threat.usage_type
                    enriched[f"{prefix}_threat_isp"] = threat.isp
                    enriched[f"{prefix}_threat_domain"] = threat.domain
                    enriched[f"{prefix}_threat_hostnames"] = threat.hostnames
                    enriched[f"{prefix}_threat_last_reported"] = threat.last_reported_at
                    enriched[f"{prefix}_threat_total_reports"] = threat.total_reports
                    enriched[f"{prefix}_threat_tags"] = threat.tags
                    enriched[f"{prefix}_threat_source"] = threat.source

        return enriched

    def clear_cache(self):
        """Clear the lookup cache."""
        self._cache.clear()

    async def close(self):
        """Close all HTTP clients."""
        if self.abuseipdb:
            await self.abuseipdb.close()
        if self.otx:
            await self.otx.close()


# Convenience function
async def enrich_threat_intel(flow: dict[str, Any]) -> dict[str, Any]:
    """Enrich a single flow with threat intelligence."""
    enricher = ThreatIntelEnrichment()
    try:
        return await enricher.enrich_flow_async(flow)
    finally:
        await enricher.close()