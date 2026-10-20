"""French number and date formats for the Karthago platform.

Django ships a ``fr`` locale module that uses a comma as the decimal
separator and a non-breaking space as the thousands separator. The
platform stores its prices in millimes (``100.000`` = 100 DT 000) and
has always displayed them with a dot, so the separators are pinned here
to keep every figure identical to the historical rendering, whatever
the language of the visitor.
"""

# Decimal separator symbol (100.000 DT).
DECIMAL_SEPARATOR = "."

# Thousands separator symbol.
THOUSAND_SEPARATOR = ","

# Number of digits in every group of thousands.
NUMBER_GROUPING = 3
