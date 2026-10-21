"""Che PII (email, số điện thoại, số thẻ) trong tài liệu tải lên, trước khi chunk."""

import re
from dataclasses import dataclass

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# 13–19 chữ số, cho phép cách bằng dấu cách hoặc gạch ngang; xác nhận lại bằng Luhn.
CARD_RE = re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])")
# Số Việt Nam: 0xxxxxxxxx hoặc +84/84 xxxxxxxxx, có thể ngăn cách bằng dấu cách, chấm, gạch.
PHONE_RE = re.compile(r"(?<![\w+])(?:\+84|84|0)(?:[ .-]?\d){9}(?!\d)")

EMAIL_MASK = "[EMAIL]"
PHONE_MASK = "[PHONE]"
CARD_MASK = "[CARD]"


@dataclass(frozen=True)
class PiiResult:
    text: str
    emails: int = 0
    phones: int = 0
    cards: int = 0

    @property
    def total(self) -> int:
        return self.emails + self.phones + self.cards


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def mask_pii(text: str) -> PiiResult:
    """Che thẻ trước (dài nhất), rồi email, rồi số điện thoại."""
    cards = 0

    def _card(m: re.Match[str]) -> str:
        nonlocal cards
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            cards += 1
            return CARD_MASK
        return m.group()

    text = CARD_RE.sub(_card, text)
    text, emails = EMAIL_RE.subn(EMAIL_MASK, text)
    text, phones = PHONE_RE.subn(PHONE_MASK, text)
    return PiiResult(text=text, emails=emails, phones=phones, cards=cards)
