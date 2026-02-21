from __future__ import annotations

from decimal import Decimal

import pytest

from src.utils_money import parse_aoxpo, parse_decimal_ptbr


def test_parse_aoxpo_valid():
    assert parse_aoxpo("2000 x 0001") == ("2000", "0001")
    assert parse_aoxpo("2000X0001") == ("2000", "0001")
    assert parse_aoxpo("  2000   x   0001  ") == ("2000", "0001")


def test_parse_aoxpo_invalid():
    with pytest.raises(ValueError):
        parse_aoxpo("2000-0001")
    with pytest.raises(ValueError):
        parse_aoxpo("")
    with pytest.raises(ValueError):
        parse_aoxpo(None)  # type: ignore[arg-type]


def test_parse_decimal_ptbr():
    assert parse_decimal_ptbr("216.456,82") == Decimal("216456.82")
    assert parse_decimal_ptbr("0,00") == Decimal("0.00")
    assert parse_decimal_ptbr(10.5) == Decimal("10.5")
    assert parse_decimal_ptbr(Decimal("2.30")) == Decimal("2.30")

