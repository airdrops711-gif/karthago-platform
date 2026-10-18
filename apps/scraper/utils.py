"""Currency and text normalizers for Tunisian prices."""
import re
from decimal import Decimal, InvalidOperation


TND_PATTERNS = [
    re.compile(r"([\d\s\.,]+)\s*(?:DT|TND|د\.ت)", re.IGNORECASE),
    re.compile(r"(?:DT|TND|د\.ت)\s*([\d\s\.,]+)", re.IGNORECASE),
    re.compile(r"([\d\s\.,]+)"),
]


def normalize_tunisian_price(raw):
    """Normalize unstructured Tunisian price strings into Decimal (3 decimals).

    Handles: "149,000 DT", "149.000 TND", "149 DT", "149,000 د.ت"
    """
    if raw is None:
        return Decimal("0.000")
    text = str(raw).strip()
    if not text:
        return Decimal("0.000")

    for pattern in TND_PATTERNS:
        match = pattern.search(text)
        if match:
            number_str = match.group(1)
            number_str = number_str.replace(" ", "").replace(".", "")
            number_str = number_str.replace(",", ".")
            try:
                return Decimal(number_str).quantize(Decimal("0.001"))
            except (InvalidOperation, ValueError):
                continue
    return Decimal("0.000")
