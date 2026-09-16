"""Tests for the enrichment TTL cache."""


class TestTTLCache:
    def test_set_and_get(self):
        from flowsight.enrichment.cache import TTLCache

        cache: TTLCache = TTLCache(ttl=60)
        cache.set("a", {"x": 1})
        assert cache.get("a") == {"x": 1}
        assert len(cache) == 1

    def test_miss_returns_none(self):
        from flowsight.enrichment.cache import TTLCache

        cache: TTLCache = TTLCache(ttl=60)
        assert cache.get("missing") is None

    def test_expiry(self, monkeypatch):
        from flowsight.enrichment import cache as cache_module
        from flowsight.enrichment.cache import TTLCache

        clock = {"now": 1000.0}
        monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock["now"])

        cache: TTLCache = TTLCache(ttl=10)
        cache.set("a", "value")

        clock["now"] = 1005.0
        assert cache.get("a") == "value"

        clock["now"] = 1011.0
        assert cache.get("a") is None
        assert len(cache) == 0  # expired entry was removed

    def test_max_size_evicts_oldest(self):
        from flowsight.enrichment.cache import TTLCache

        cache: TTLCache = TTLCache(ttl=3600, max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)

        assert len(cache) <= 3
        assert cache.get("a") is None  # oldest evicted
        assert cache.get("d") == 4

    def test_clear(self):
        from flowsight.enrichment.cache import TTLCache

        cache: TTLCache = TTLCache(ttl=60)
        cache.set("a", 1)
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None


class TestEnricherCacheWiring:
    def test_geoip_uses_ttl_cache(self):
        from flowsight.enrichment.cache import TTLCache
        from flowsight.enrichment.geoip import GeoIPEnrichment

        enricher = GeoIPEnrichment(db_path="./data/does-not-exist.mmdb")
        assert isinstance(enricher._cache, TTLCache)

    def test_asn_uses_ttl_cache(self):
        from flowsight.enrichment.asn import ASNEnrichment
        from flowsight.enrichment.cache import TTLCache

        enricher = ASNEnrichment(db_path="./data/does-not-exist.mmdb")
        assert isinstance(enricher._cache, TTLCache)

    def test_threat_intel_uses_ttl_cache(self):
        from flowsight.enrichment.cache import TTLCache
        from flowsight.enrichment.threat_intel import ThreatIntelEnrichment

        enricher = ThreatIntelEnrichment()
        assert isinstance(enricher._cache, TTLCache)

    def test_stats_len_works(self):
        from flowsight.enrichment.geoip import GeoIPEnrichment

        enricher = GeoIPEnrichment(db_path="./data/does-not-exist.mmdb")
        assert len(enricher._cache) == 0
