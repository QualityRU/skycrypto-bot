from decimal import Decimal

from settings import SELLER_COMMISSION
from utils.helpers import get_correct_value


class Math:
    async def crypto_in_currency(self, val_crypto, rate):
        return round(val_crypto * rate)

    async def parse_rate(self, text: str, rate: Decimal, rate_variation: Decimal, digits=4) -> tuple:
        is_percentage = "%" in text
        text = text.strip(".#! %").replace(",", ".").replace(" ", "")

        if is_percentage:
            coefficient = round(Decimal(text) / Decimal("100") + 1, digits)
            new_rate = round(rate * coefficient, 2)
        else:
            coefficient = None
            new_rate = round(Decimal(text), 2)

        variation = new_rate / rate
        rate_variation = rate_variation + Decimal("0.001")
        if Decimal("1") - rate_variation > variation or variation > Decimal("1") + rate_variation:
            raise ValueError("Wrong rate variation")
        return new_rate, coefficient

    async def parse_limits(self, text):
        limits = limit_from, limit_to = tuple(map(int, text.replace(" ", "").split("-")))
        if limit_to < limit_from:
            raise ValueError(f"limit_from {limit_from} is greater then limit_to {limit_to}")
        if limit_to > 1_000_000_000:
            raise ValueError(f"{limit_to} is very big!")
        if limit_from <= 0 or limit_to <= 0:
            raise ValueError("limit must be greater than 0")
        return limits

    async def get_percents_diff_rate(self, rate, lot_rate):
        if not isinstance(lot_rate, Decimal):
            lot_rate = Decimal(lot_rate)
        diff = round(float(get_correct_value(round((lot_rate / rate - Decimal("1")) * Decimal("100"), 2))), 2)
        return diff

    async def get_maximum_limit(self, lot, seller_balance_units):
        max_to_sell = Decimal(str(seller_balance_units)) * Decimal(str(lot["rate"]))
        max_to_sell -= (
            Decimal(str(max_to_sell)) * (1 - Decimal(str(SELLER_COMMISSION))) * Decimal(str(SELLER_COMMISSION))
        )
        if max_to_sell < lot["limit_to"]:
            return int(max_to_sell)
        else:
            return lot["limit_to"]

    async def parse_amount(self, text):
        val = Decimal(text.strip(".#! %").replace(",", ".").replace(" ", ""))
        if val <= 0:
            raise ValueError("Value must be > 0")
        return val

    async def parse_count(self, text):
        cnt = int(text)
        if cnt <= 0:
            raise ValueError(f"Cant parse count from {cnt}")
        elif cnt > 50:
            raise ValueError(f"Wrong count {cnt}")
        return cnt


math = Math()
