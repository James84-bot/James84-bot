"""Decimal helpers. Never use float for money, cost or quantity."""

from decimal import ROUND_HALF_UP, Decimal

MONEY_PLACES = Decimal("0.01")
COST_PLACES = Decimal("0.0001")
QTY_PLACES = Decimal("0.001")
ZERO = Decimal("0")


def money(value) -> Decimal:
    return Decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def cost(value) -> Decimal:
    return Decimal(value).quantize(COST_PLACES, rounding=ROUND_HALF_UP)


def qty(value) -> Decimal:
    return Decimal(value).quantize(QTY_PLACES, rounding=ROUND_HALF_UP)
