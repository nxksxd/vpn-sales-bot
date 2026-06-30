"""Balance top-up use cases."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import LabeledPrice

from bot.utils.validators import validate_topup_amount


@dataclass(frozen=True)
class TopupInvoice:
    title: str
    description: str
    payload: str
    currency: str
    prices: list[LabeledPrice]


class BalanceService:
    @staticmethod
    def parse_topup_amount(value: str) -> int | None:
        """Validate and normalize a Telegram Stars top-up amount."""
        return validate_topup_amount(value)

    @staticmethod
    def build_topup_invoice(amount: int) -> TopupInvoice:
        """Build Telegram Stars invoice data for a validated top-up amount."""
        if validate_topup_amount(str(amount)) is None:
            raise ValueError("invalid top-up amount")

        return TopupInvoice(
            title="Пополнение баланса",
            description=f"Пополнение баланса на {amount} Stars",
            payload=f"topup:v1:{amount}",
            currency="XTR",
            prices=[LabeledPrice(label="Stars", amount=amount)],
        )
