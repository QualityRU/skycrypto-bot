from decimal import Decimal

from settings import DECIMALS


def is_valid_float_digits(value: Decimal, digits: int):
    return abs(value.as_tuple().exponent) <= digits


def validate_amount_precision_right_for_symbol(value: Decimal):
    if not is_valid_float_digits(value, digits=DECIMALS):
        raise ValueError
