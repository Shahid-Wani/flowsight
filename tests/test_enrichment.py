"""Tests for enrichment source behavior with missing databases."""

import logging

from flowsight import setup_logging


def test_geoip_missing_db_warns_once(caplog):
    """Repeated lookups with a missing DB must warn only once, not per lookup."""
    from flowsight.enrichment.geoip import GeoIPEnrichment

    setup_logging()
    enrichment = GeoIPEnrichment(db_path="./data/does-not-exist.mmdb")
    with caplog.at_level(logging.WARNING):
        assert enrichment.lookup("1.2.3.4") is None
        assert enrichment.lookup("5.6.7.8") is None
        assert enrichment.lookup("9.9.9.9") is None

    warnings = [r for r in caplog.records if "geoip_database_not_found" in r.getMessage()]
    assert len(warnings) == 1, f"expected exactly one warning, got {len(warnings)}"


def test_asn_missing_db_warns_once(caplog):
    """Repeated lookups with a missing ASN DB must warn only once."""
    from flowsight.enrichment.asn import ASNEnrichment

    setup_logging()
    enrichment = ASNEnrichment(db_path="./data/does-not-exist.mmdb")
    with caplog.at_level(logging.WARNING):
        assert enrichment.lookup("1.2.3.4") is None
        assert enrichment.lookup("5.6.7.8") is None

    warnings = [r for r in caplog.records if "asn_database_not_found" in r.getMessage()]
    assert len(warnings) == 1, f"expected exactly one warning, got {len(warnings)}"


def test_missing_db_enrichment_returns_flow_unchanged():
    """Enrichment with no databases must return the flow unchanged."""
    from flowsight.enrichment.geoip import GeoIPEnrichment

    enrichment = GeoIPEnrichment(db_path="./data/does-not-exist.mmdb")
    flow = {"src_ip": "1.2.3.4", "dst_ip": "5.6.7.8", "bytes": 100}
    enriched = enrichment.enrich_flow(flow)

    assert enriched == flow
