"""Unit tests for search URL helpers."""

from flairbnb.search import url_to_raw_params


def test_url_to_raw_params_basic():
    url = (
        "https://www.airbnb.com/s/homes"
        "?checkin=2026-02-09&checkout=2026-02-16"
        "&ne_lat=49.76537&ne_lng=6.56057"
        "&sw_lat=49.31155&sw_lng=6.03263"
        "&zoom=10&price_min=154&price_max=700"
    )
    params = url_to_raw_params(url)
    by_name = {p["filterName"]: p["filterValues"] for p in params}

    assert by_name["checkin"] == ["2026-02-09"]
    assert by_name["checkout"] == ["2026-02-16"]
    assert by_name["zoomLevel"] == ["10"] or by_name.get("zoom_level") == ["10"]
    assert "priceFilterNumNights" in by_name
    assert by_name["priceFilterNumNights"] == ["7"]
