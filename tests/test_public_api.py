"""Public package surface checks."""

import flairbnb


EXPECTED_EXPORTS = [
    "parse_proxy",
    "get_nested_value",
    "get_api_key",
    "get_listings_from_user",
    "get_host_details",
    "experience_search_by_place_id",
    "get_markets",
    "get_places_ids",
    "fetch_stays_search_hash",
    "get_calendar",
    "search_all",
    "search_all_from_url",
    "search_first_page",
    "get_reviews",
    "get_details",
    "experience_search",
    "get_metadata_from_url",
    "get_price",
]


def test_all_exports_present():
    assert flairbnb.__all__ == EXPECTED_EXPORTS


def test_exports_are_callable():
    for name in EXPECTED_EXPORTS:
        assert callable(getattr(flairbnb, name)), f"{name} should be callable"
