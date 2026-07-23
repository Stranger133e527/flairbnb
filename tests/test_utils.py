"""Unit tests for flairbnb.utils."""

import flairbnb


def test_get_nested_value_found():
    data = {"a": {"b": {"c": 42}}}
    assert flairbnb.get_nested_value(data, "a.b.c") == 42


def test_get_nested_value_missing_returns_default():
    data = {"a": {"b": 1}}
    assert flairbnb.get_nested_value(data, "a.x.y", default="missing") == "missing"


def test_get_nested_value_none_returns_default():
    data = {"a": None}
    assert flairbnb.get_nested_value(data, "a.b", default=0) == 0


def test_parse_proxy():
    url = flairbnb.parse_proxy("1.2.3.4", "8080", "user", "p@ss")
    assert url == "http://user:p%40ss@1.2.3.4:8080"


def test_remove_space():
    from flairbnb.utils import remove_space

    assert remove_space("  hello   world  ") == "hello world"


def test_parse_price_symbol():
    from flairbnb.utils import parse_price_symbol

    amount, currency = parse_price_symbol("$1,234.50")
    assert amount == 1234.50
    assert "$" in currency


def test_parse_price_symbol_negative():
    from flairbnb.utils import parse_price_symbol

    amount, _ = parse_price_symbol("-100 USD")
    assert amount == -100.0


def test_parse_price_symbol_empty():
    from flairbnb.utils import parse_price_symbol

    amount, currency = parse_price_symbol("N/A")
    assert amount == 0
    assert currency == ""
