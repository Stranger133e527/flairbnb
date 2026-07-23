"""
Live Airbnb integration tests.

Run with:  pytest -m integration
Skip with: pytest -m "not integration"
"""

from datetime import date, timedelta

import pytest

import flairbnb

pytestmark = pytest.mark.integration

# Stable-ish public listing used in upstream examples
ROOM_ID = "21734211"
ROOM_URL = f"https://www.airbnb.com/rooms/{ROOM_ID}"
HOST_ID = "656454528"
TIMEOUT = 45


def _future_range(nights: int = 3, days_ahead: int = 60):
    check_in = date.today() + timedelta(days=days_ahead)
    check_out = check_in + timedelta(days=nights)
    return check_in, check_out


def test_get_api_key():
    key = flairbnb.get_api_key("")
    assert isinstance(key, str)
    assert len(key) > 10


def test_fetch_stays_search_hash():
    h = flairbnb.fetch_stays_search_hash(timeout=TIMEOUT)
    assert isinstance(h, str)
    assert len(h) >= 32


def test_get_details():
    data = flairbnb.get_details(
        room_url=ROOM_URL,
        currency="USD",
        adults=2,
        language="en",
        timeout=TIMEOUT,
    )
    assert isinstance(data, dict)
    assert "host" in data
    assert "reviews" in data
    assert "calendar" in data


def test_get_calendar():
    cal = flairbnb.get_calendar(room_id=ROOM_ID, timeout=TIMEOUT)
    assert cal is not None


def test_get_reviews():
    reviews = flairbnb.get_reviews(ROOM_URL, language="en", timeout=TIMEOUT)
    assert reviews is not None


def test_get_price():
    check_in, check_out = _future_range()
    try:
        data = flairbnb.get_price(
            room_id=ROOM_ID,
            check_in=check_in,
            check_out=check_out,
            timeout=TIMEOUT,
        )
    except Exception as exc:
        # Listing may be unavailable for chosen dates
        pytest.skip(f"price unavailable: {exc}")
    assert isinstance(data, dict)


def test_search_first_page():
    check_in, check_out = _future_range()
    results = flairbnb.search_first_page(
        check_in=check_in.isoformat(),
        check_out=check_out.isoformat(),
        ne_lat=40.8,
        ne_long=-73.9,
        sw_lat=40.7,
        sw_long=-74.05,
        zoom_value=12,
        price_min=0,
        price_max=0,
        currency="USD",
        language="en",
        timeout=TIMEOUT,
    )
    assert isinstance(results, (list, tuple, dict))


def test_get_markets_and_places():
    api_key = flairbnb.get_api_key("")
    markets_data = flairbnb.get_markets("USD", "en", api_key, "", timeout=TIMEOUT)
    markets = flairbnb.get_nested_value(markets_data, "user_markets", [])
    assert isinstance(markets, list)
    assert len(markets) > 0

    config_token = flairbnb.get_nested_value(markets[0], "satori_parameters", "")
    country_code = flairbnb.get_nested_value(markets[0], "country_code", "")
    places = flairbnb.get_places_ids(
        country_code,
        "New York",
        "USD",
        "en",
        config_token,
        api_key,
        "",
        timeout=TIMEOUT,
    )
    assert isinstance(places, list)
    assert len(places) > 0


def test_get_listings_from_user():
    api_key = flairbnb.get_api_key("")
    listings = flairbnb.get_listings_from_user(int(HOST_ID), api_key, "", timeout=TIMEOUT)
    assert listings is not None


def test_get_host_details():
    api_key = flairbnb.get_api_key("")
    details = flairbnb.get_host_details(api_key, None, HOST_ID, "en", "", timeout=TIMEOUT)
    assert details is not None
