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

    Tunisian convention: comma is decimal separator, dot is thousand separator.
    However, both "149,000 DT" and "149.000 TND" should normalize to 149.000.
    """
    if raw is None:
        return Decimal("0.000")
    text = str(raw).strip()
    if not text:
        return Decimal("0.000")

    for pattern in TND_PATTERNS:
        match = pattern.search(text)
        if match:
            number_str = match.group(1).replace(" ", "")
            if not number_str:
                continue

            has_dot = "." in number_str
            has_comma = "," in number_str

            if has_dot and has_comma:
                # Both separators: last one is decimal, other is thousand
                last_dot = number_str.rfind(".")
                last_comma = number_str.rfind(",")
                if last_dot > last_comma:
                    # Dot is decimal, comma is thousand
                    number_str = number_str.replace(",", "").replace(".", ".")
                else:
                    # Comma is decimal, dot is thousand
                    number_str = number_str.replace(".", "").replace(",", ".")
            elif has_comma:
                # Only comma: treat as decimal separator
                number_str = number_str.replace(",", ".")
            elif has_dot:
                # Only dot: treat as decimal separator (e.g., "149.000 TND")
                number_str = number_str.replace(".", ".")
            else:
                number_str = number_str

            try:
                return Decimal(number_str).quantize(Decimal("0.001"))
            except (InvalidOperation, ValueError):
                continue
    return Decimal("0.000")
