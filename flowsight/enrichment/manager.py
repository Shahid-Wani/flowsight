"""
Enrichment Manager

Coordinates all enrichment sources (GeoIP, ASN, Threat Intel) for flow processing.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from flowsight import get_logger
from flowsight.config import settings
from flowsight.enrichment.geoip import GeoIPEnrichment
from flowsight.enrichment.asn import ASNEnrichment
from flowsight.enrichment.threat_intel import ThreatIntelEnrichment

logger = get_logger(__name__)


@dataclass
class EnrichmentConfig:
    """Configuration for enrichment pipeline."""
    geoip_enabled: bool = True
    asn_enabled: bool = True
    threat_intel_enabled: bool = True
    geoip_path: str | None = None
    asn_path: str | None = None


class EnrichmentManager:
    """Manages all enrichment sources and processes flows through them."""

    def __init__(self, config: EnrichmentConfig | None = None):
        self.config = config or EnrichmentConfig()
        self.geoip: GeoIPEnrichment | None = None
        self.asn: ASNEnrichment | None = None
        self.threat_intel: ThreatIntelEnrichment | None = None
        self._initialized = False

    async def initialize(self):
        """Initialize all enrichment sources."""
        if self._initialized:
            return

        if self.config.geoip_enabled:
            self.geoip = GeoIPEnrichment(self.config.geoip_path)
            self.geoip.open()

        if self.config.asn_enabled:
            self.asn = ASNEnrichment(self.config.asn_path)
            self.asn.open()

        if self.config.threat_intel_enabled:
            self.threat_intel = ThreatIntelEnrichment()

        self._initialized = True
        logger.info("enrichment_manager_initialized",
                   geoip=self.config.geoip_enabled,
                   asn=self.config.asn_enabled,
                   threat_intel=self.config.threat_intel_enabled)

    def enrich_flow_sync(self, flow: dict[str, Any]) -> dict[str, Any]:
        """Enrich a flow synchronously (GeoIP + ASN only)."""
        if not self._initialized:
            # Auto-initialize synchronously
            if self.config.geoip_enabled and not self.geoip:
                self.geoip = GeoIPEnrichment(self.config.geoip_path)
                self.geoip.open()
            if self.config.asn_enabled and not self.asn:
                self.asn = ASNEnrichment(self.config.asn_path)
                self.asn.open()

        enriched = flow.copy()

        # Apply GeoIP enrichment
        if self.geoip:
            enriched = self.geoip.enrich_flow(enriched)

        # Apply ASN enrichment
        if self.asn:
            enriched = self.asn.enrich_flow(enriched)

        return enriched

    async def enrich_flow_async(self, flow: dict[str, Any]) -> dict[str, Any]:
        """Enrich a flow asynchronously (all sources including threat intel)."""
        await self.initialize()

        # Start with sync enrichments
        enriched = self.enrich_flow_sync(flow)

        # Apply threat intelligence enrichment
        if self.threat_intel:
            enriched = await self.threat_intel.enrich_flow_async(enriched)

        return enriched

    async def enrich_batch_async(self, flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich a batch of flows concurrently."""
        await self.initialize()

        # Process in parallel
        tasks = [self.enrich_flow_async(flow) for flow in flows]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        enriched = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.exception("enrichment_failed", flow_index=i, error=str(result))
                enriched.append(flows[i])  # Return original on failure
            else:
                enriched.append(result)

        return enriched

    def get_stats(self) -> dict[str, Any]:
        """Get enrichment cache statistics."""
        stats = {}
        if self.geoip:
            stats["geoip_cache_size"] = len(self.geoip._cache)
        if self.asn:
            stats["asn_cache_size"] = len(self.asn._cache)
        if self.threat_intel:
            stats["threat_intel_cache_size"] = len(self.threat_intel._cache)
        return stats

    def clear_caches(self):
        """Clear all enrichment caches."""
        if self.geoip:
            self.geoip.clear_cache()
        if self.asn:
            self.asn.clear_cache()
        if self.threat_intel:
            self.threat_intel.clear_cache()

    async def close(self):
        """Close all enrichment sources."""
        if self.threat_intel:
            await self.threat_intel.close()
        if self.geoip:
            self.geoip.close()
        if self.asn:
            self.asn.close()
        self._initialized = False


# Global enrichment manager instance
_enrichment_manager: EnrichmentManager | None = None


async def get_enrichment_manager() -> EnrichmentManager:
    """Get or create the global enrichment manager."""
    global _enrichment_manager
    if _enrichment_manager is None:
        _enrichment_manager = EnrichmentManager()
        await _enrichment_manager.initialize()
    return _enrichment_manager


async def enrich_flow(flow: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to enrich a single flow."""
    manager = await get_enrichment_manager()
    return await manager.enrich_flow_async(flow)


async def enrich_batch(flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convenience function to enrich a batch of flows."""
    manager = await get_enrichment_manager()
    return await manager.enrich_batch_async(flows)