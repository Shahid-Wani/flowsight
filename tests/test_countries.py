"""Tests for the static country metadata table used by the geo-map."""

from flowsight.api.countries import country_info, get_country_name


def test_known_country():
    """A known code must resolve to name and centroid coordinates."""
    info = country_info("US")
    assert info["name"] == "United States"
    assert isinstance(info["latitude"], float)
    assert isinstance(info["longitude"], float)
    assert -180 <= info["longitude"] <= 180
    assert -90 <= info["latitude"] <= 90


def test_unknown_country_falls_back_to_code():
    """An unmapped code must fall back to the code itself, not crash."""
    info = country_info("ZZ")
    assert info["name"] == "ZZ"
    assert info["latitude"] is None
    assert info["longitude"] is None


def test_none_and_lowercase_codes():
    """None and lowercase codes must be handled safely."""
    assert country_info(None)["name"] == "Unknown"
    assert country_info("de")["name"] == "Germany"


def test_get_country_name_helper():
    """get_country_name returns the display name for a code."""
    assert get_country_name("DE") == "Germany"
    assert get_country_name("QQ") == "QQ"


def test_table_covers_major_traffic_countries():
    """The table must cover the countries that dominate real traffic."""
    from flowsight.api.countries import COUNTRIES

    major_traffic = [
        "US", "CN", "RU", "DE", "GB", "FR", "NL", "IN", "JP", "KR", "BR", "AU", "CA", "SG",
    ]
    for code in major_traffic:
        assert code in COUNTRIES, f"{code} missing from country table"
