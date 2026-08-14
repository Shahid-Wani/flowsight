"""
ASN Enrichment

MaxMind GeoLite2 ASN database integration for IP autonomous system information.
"""

from dataclasses import dataclass
from typing import Any

import maxminddb

from flowsight import get_logger
from flowsight.config import settings

logger = get_logger(__name__)


@dataclass
class ASNInfo:
    """ASN lookup result."""
    autonomous_system_number: int | None = None
    autonomous_system_organization: str | None = None
    network: str | None = None
    isp: str | None = None


class ASNEnrichment:
    """MaxMind GeoLite2 ASN database enrichment for IP addresses."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.enrichment.asn_path
        self._reader: maxminddb.Reader | None = None
        self._cache: dict[str, ASNInfo] = {}
        self._cache_ttl = settings.enrichment.cache_ttl

    def open(self):
        """Open the MaxMind ASN database."""
        try:
            self._reader = maxminddb.open_database(self.db_path)
            logger.info("asn_database_opened", path=self.db_path)
        except FileNotFoundError:
            logger.warning("asn_database_not_found", path=self.db_path)
            self._reader = None
        except Exception as e:
            logger.exception("asn_open_failed", error=str(e))
            self._reader = None

    def close(self):
        """Close the database reader."""
        if self._reader:
            self._reader.close()
            self._reader = None

    def lookup(self, ip: str) -> ASNInfo | None:
        """Look up IP address in ASN database."""
        # Check cache first
        if ip in self._cache:
            return self._cache[ip]

        if not self._reader:
            self.open()
            if not self._reader:
                return None

        try:
            result = self._reader.get(ip)
            if not result:
                return None

            asn = self._parse_result(result)
            self._cache[ip] = asn
            return asn

        except Exception as e:
            logger.debug("asn_lookup_failed", ip=ip, error=str(e))
            return None

    def _parse_result(self, result: dict) -> ASNInfo:
        """Parse MaxMind ASN result into ASNInfo."""
        asn = ASNInfo()

        asn.autonomous_system_number = result.get("autonomous_system_number")
        asn.autonomous_system_organization = result.get("autonomous_system_organization")
        asn.network = result.get("network")
        asn.isp = result.get("isp")

        return asn

    def enrich_flow(self, flow: dict[str, Any]) -> dict[str, Any]:
        """Enrich a flow record with ASN data for src and dst IPs."""
        enriched = flow.copy()

        for ip_field in ("src_ip", "dst_ip"):
            ip = flow.get(ip_field)
            if ip:
                asn = self.lookup(ip)
                if asn:
                    prefix = "src" if ip_field == "src_ip" else "dst"
                    enriched[f"{prefix}_asn"] = asn.autonomous_system_number
                    enriched[f"{prefix}_asn_org"] = asn.autonomous_system_organization
                    enriched[f"{prefix}_asn_network"] = asn.network
                    enriched[f"{prefix}_asn_isp"] = asn.isp

        return enriched

    def clear_cache(self):
        """Clear the lookup cache."""
        self._cache.clear()


# Convenience function
def enrich_asn(flow: dict[str, Any], db_path: str | None = None) -> dict[str, Any]:
    """Enrich a single flow with ASN data."""
    enricher = ASNEnrichment(db_path)
    enricher.open()
    try:
        return enricher.enrich_flow(flow)
    finally:
        enricher.close()