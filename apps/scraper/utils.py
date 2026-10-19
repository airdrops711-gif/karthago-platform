"""Currency and text normalizers for Tunisian prices."""
import re
from decimal import Decimal, InvalidOperation


TND_PATTERNS = [
    re.compile(r"([\d\s\.,]+)\s*(?:DT|TND|د\.ت)", re.IGNORECASE),
    re.compile(r"(?:DT|TND|د\.ت)\s*([\d\s\.,]+)", re.IGNORECASE),
    re.compile(r"([\d\s\.,]+)"),
]

# Currency symbols that prefix or suffix a bare amount.
CURRENCY_SYMBOLS = ("$", "€", "£", "¥", "₹", "ر.س", "ج.م")

# Words that may sit between the currency marker and the number,
# e.g. "Price Now $39.99 Was $52.00" -> we want the first amount.
PRICE_NOISE_WORDS = (
    r"(?:price|now|was|from|to|only|just|save|off|deal|was|est|سعر|prix)"
)


def _strip_price_noise(text):
    """Reduce a price label to its first bare amount.

    "Price Now $39.99 Was $52.00" -> "39.99"
    "Price $84.28" -> "84.28"
    "84,000 DT" -> "84,000 DT"
    """
    # Prefer an amount immediately attached to a currency symbol.
    symbol_re = "(?:" + "|".join(re.escape(s) for s in CURRENCY_SYMBOLS) + ")"
    match = re.search(
        rf"{symbol_re}\s*(\d[\d\s\.,]*)", text
    ) or re.search(
        rf"(\d[\d\s\.,]*)\s*{symbol_re}", text
    )
    if match:
        return match.group(1).strip()

    # Otherwise drop leading noise words and keep the first amount.
    cleaned = re.sub(
        rf"^[\s\.,]*(?:{PRICE_NOISE_WORDS})[\s\.,:]*", "", text, flags=re.IGNORECASE
    )
    match = re.search(r"(\d[\d\s\.,]*)", cleaned)
    if match:
        return match.group(1).strip()
    return text


def normalize_tunisian_price(raw):
    """Normalize unstructured Tunisian price strings into Decimal (3 decimals).

    Handles: "149,000 DT", "149.000 TND", "149 DT", "149,000 د.ت", "$84.28"

    Tunisian convention: comma is decimal separator, dot is thousand separator.
    However, both "149,000 DT" and "149.000 TND" should normalize to 149.000.
    """
    if raw is None:
        return Decimal("0.000")
    text = str(raw).strip()
    if not text:
        return Decimal("0.000")

    # Drop label noise ("Price", "Now", "Was") and keep the first amount.
    text = _strip_price_noise(text)
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
