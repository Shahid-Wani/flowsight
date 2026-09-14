"""Static country metadata for the geo-map.

Maps ISO-3166 alpha-2 codes to display names and approximate country
centroids. Dependency-free fallback: unknown codes resolve to the code
itself with null coordinates (the frontend table renders the flag from
the code regardless).
"""

from typing import Any

# alpha-2 -> (name, latitude, longitude) — approximate centroids
COUNTRIES: dict[str, tuple[str, float, float]] = {
    "AD": ("Andorra", 42.5, 1.6),
    "AE": ("United Arab Emirates", 24.0, 54.0),
    "AR": ("Argentina", -38.4, -63.6),
    "AT": ("Austria", 47.5, 14.6),
    "AU": ("Australia", -25.3, 133.8),
    "AZ": ("Azerbaijan", 40.1, 47.6),
    "BA": ("Bosnia and Herzegovina", 43.9, 17.7),
    "BE": ("Belgium", 50.5, 4.5),
    "BG": ("Bulgaria", 42.7, 25.5),
    "BR": ("Brazil", -14.2, -51.9),
    "BY": ("Belarus", 53.7, 27.9),
    "CA": ("Canada", 56.1, -106.3),
    "CH": ("Switzerland", 46.8, 8.2),
    "CL": ("Chile", -35.7, -71.5),
    "CN": ("China", 35.9, 104.2),
    "CO": ("Colombia", 4.6, -74.3),
    "CZ": ("Czech Republic", 49.8, 15.5),
    "DE": ("Germany", 51.2, 10.5),
    "DK": ("Denmark", 56.3, 9.5),
    "EE": ("Estonia", 58.6, 25.0),
    "EG": ("Egypt", 26.8, 30.8),
    "ES": ("Spain", 40.5, -3.7),
    "FI": ("Finland", 61.9, 25.7),
    "FR": ("France", 46.2, 2.2),
    "GB": ("United Kingdom", 55.4, -3.4),
    "GR": ("Greece", 39.1, 21.8),
    "HK": ("Hong Kong", 22.3, 114.2),
    "HR": ("Croatia", 45.1, 15.2),
    "HU": ("Hungary", 47.2, 19.5),
    "ID": ("Indonesia", -0.8, 113.9),
    "IE": ("Ireland", 53.4, -8.2),
    "IL": ("Israel", 31.0, 34.9),
    "IN": ("India", 20.6, 79.0),
    "IQ": ("Iraq", 33.2, 43.7),
    "IR": ("Iran", 32.4, 53.7),
    "IS": ("Iceland", 64.9, -19.0),
    "IT": ("Italy", 41.9, 12.6),
    "JP": ("Japan", 36.2, 138.3),
    "KE": ("Kenya", -0.0, 37.9),
    "KR": ("South Korea", 35.9, 127.8),
    "KW": ("Kuwait", 29.3, 47.5),
    "KZ": ("Kazakhstan", 48.0, 66.9),
    "LT": ("Lithuania", 55.2, 23.9),
    "LU": ("Luxembourg", 49.8, 6.1),
    "LV": ("Latvia", 56.9, 24.6),
    "LY": ("Libya", 26.3, 17.2),
    "MA": ("Morocco", 31.8, -7.1),
    "MD": ("Moldova", 47.4, 28.4),
    "MK": ("North Macedonia", 41.6, 21.7),
    "MM": ("Myanmar", 21.9, 95.9),
    "MN": ("Mongolia", 46.9, 103.8),
    "MT": ("Malta", 35.9, 14.4),
    "MX": ("Mexico", 23.6, -102.6),
    "MY": ("Malaysia", 4.2, 101.9),
    "NG": ("Nigeria", 9.1, 8.7),
    "NL": ("Netherlands", 52.1, 5.3),
    "NO": ("Norway", 60.5, 8.5),
    "NZ": ("New Zealand", -40.9, 174.9),
    "PE": ("Peru", -9.2, -75.0),
    "PH": ("Philippines", 12.9, 121.8),
    "PK": ("Pakistan", 30.4, 69.3),
    "PL": ("Poland", 51.9, 19.1),
    "PT": ("Portugal", 39.4, -8.2),
    "QA": ("Qatar", 25.4, 51.2),
    "RO": ("Romania", 45.9, 25.0),
    "RS": ("Serbia", 44.0, 21.0),
    "RU": ("Russia", 61.5, 105.3),
    "SA": ("Saudi Arabia", 23.9, 45.1),
    "SE": ("Sweden", 60.1, 18.6),
    "SG": ("Singapore", 1.35, 103.8),
    "SI": ("Slovenia", 46.2, 14.9),
    "SK": ("Slovakia", 48.7, 19.7),
    "TH": ("Thailand", 15.9, 101.0),
    "TN": ("Tunisia", 33.9, 9.5),
    "TR": ("Turkey", 38.96, 35.2),
    "TW": ("Taiwan", 23.7, 121.0),
    "UA": ("Ukraine", 48.4, 31.2),
    "US": ("United States", 37.1, -95.7),
    "UY": ("Uruguay", -32.5, -55.8),
    "VE": ("Venezuela", 6.4, -66.6),
    "VN": ("Vietnam", 14.1, 108.3),
    "ZA": ("South Africa", -30.6, 22.9),
}


def country_info(code: str | None) -> dict[str, Any]:
    """Resolve a country code to display name and centroid coordinates.

    Unknown or missing codes fall back to the code itself (or
    "Unknown" for None) with null coordinates.
    """
    if not code:
        return {"name": "Unknown", "latitude": None, "longitude": None}
    normalized = code.strip().upper()
    if normalized in COUNTRIES:
        name, latitude, longitude = COUNTRIES[normalized]
        return {"name": name, "latitude": latitude, "longitude": longitude}
    return {"name": normalized, "latitude": None, "longitude": None}


def get_country_name(code: str | None) -> str:
    """Return the display name for a country code."""
    return country_info(code)["name"]
