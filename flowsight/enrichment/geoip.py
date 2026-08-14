"""
GeoIP Enrichment

MaxMind GeoLite2 database integration for IP geolocation.
"""

import logging
from dataclasses import dataclass
from typing import Any

import maxminddb

from flowsight import get_logger
from flowsight.config import settings

logger = get_logger(__name__)


@dataclass
class GeoIPInfo:
    """GeoIP lookup result."""
    country_code: str | None = None
    country_name: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    isp: str | None = None
    organization: str | None = None
    is_eu: bool = False
    is_anonymous: bool = False
    is_hosting: bool = False


class GeoIPEnrichment:
    """MaxMind GeoLite2 database enrichment for IP addresses."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.enrichment.geoip_path
        self._reader: maxminddb.Reader | None = None
        self._cache: dict[str, GeoIPInfo] = {}
        self._cache_ttl = settings.enrichment.cache_ttl

    def open(self):
        """Open the MaxMind database."""
        try:
            self._reader = maxminddb.open_database(self.db_path)
            logger.info("geoip_database_opened", path=self.db_path)
        except FileNotFoundError:
            logger.warning("geoip_database_not_found", path=self.db_path)
            self._reader = None
        except Exception as e:
            logger.exception("geoip_open_failed", error=str(e))
            self._reader = None

    def close(self):
        """Close the database reader."""
        if self._reader:
            self._reader.close()
            self._reader = None

    def lookup(self, ip: str) -> GeoIPInfo | None:
        """Look up IP address in GeoIP database."""
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

            geoip = self._parse_result(result)
            self._cache[ip] = geoip
            return geoip

        except Exception as e:
            logger.debug("geoip_lookup_failed", ip=ip, error=str(e))
            return None

    def _parse_result(self, result: dict) -> GeoIPInfo:
        """Parse MaxMind result into GeoIPInfo."""
        geoip = GeoIPInfo()

        # Country
        if "country" in result:
            geoip.country_code = result["country"].get("iso_code")
            geoip.country_name = result["country"].get("names", {}).get("en")
            geoip.is_eu = result["country"].get("is_in_european_union", False)

        # Region/Subdivision
        if "subdivisions" in result and result["subdivisions"]:
            sub = result["subdivisions"][0]
            geoip.region_code = sub.get("iso_code")
            geoip.region_name = sub.get("names", {}).get("en")

        # City
        if "city" in result:
            geoip.city = result["city"].get("names", {}).get("en")

        # Location
        if "location" in result:
            loc = result["location"]
            geoip.latitude = loc.get("latitude")
            geoip.longitude = loc.get("longitude")
            geoip.timezone = loc.get("time_zone")

        # Traits (anonymous proxy, hosting provider, etc.)
        if "traits" in result:
            traits = result["traits"]
            geoip.is_anonymous = traits.get("is_anonymous_proxy", False)
            geoip.is_hosting = traits.get("is_hosting_provider", False)

        return geoip

    def enrich_flow(self, flow: dict[str, Any]) -> dict[str, Any]:
        """Enrich a flow record with GeoIP data for src and dst IPs."""
        enriched = flow.copy()

        for ip_field in ("src_ip", "dst_ip"):
            ip = flow.get(ip_field)
            if ip:
                geoip = self.lookup(ip)
                if geoip:
                    prefix = "src" if ip_field == "src_ip" else "dst"
                    enriched[f"{prefix}_country_code"] = geoip.country_code
                    enriched[f"{prefix}_country_name"] = geoip.country_name
                    enriched[f"{prefix}_region_code"] = geoip.region_code
                    enriched[f"{prefix}_region_name"] = geoip.region_name
                    enriched[f"{prefix}_city"] = geoip.city
                    enriched[f"{prefix}_latitude"] = geoip.latitude
                    enriched[f"{prefix}_longitude"] = geoip.longitude
                    enriched[f"{prefix}_timezone"] = geoip.timezone
                    enriched[f"{prefix}_is_eu"] = geoip.is_eu
                    enriched[f"{prefix}_is_anonymous"] = geoip.is_anonymous
                    enriched[f"{prefix}_is_hosting"] = geoip.is_hosting

        return enriched

    def clear_cache(self):
        """Clear the lookup cache."""
        self._cache.clear()


# Convenience function
def enrich_geoip(flow: dict[str, Any], db_path: str | None = None) -> dict[str, Any]:
    """Enrich a single flow with GeoIP data."""
    enricher = GeoIPEnrichment(db_path)
    enricher.open()
    try:
        return enricher.enrich_flow(flow)
    finally:
        enricher.close()