"""Unit tests for flairbnb.standardize helpers."""

from flairbnb.standardize import decode_listing_id, encode_room_id


def test_encode_room_id():
    encoded = encode_room_id("12345", prefix="StayListing")
    assert decode_listing_id(encoded) == 12345


def test_decode_listing_id_empty():
    assert decode_listing_id("") == 0


def test_decode_listing_id_invalid():
    assert decode_listing_id("not-valid-base64!!!") == 0
