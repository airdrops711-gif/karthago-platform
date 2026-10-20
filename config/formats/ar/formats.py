"""Arabic number and date formats for the Karthago platform.

Same rule as the French module: the prices are stored in millimes and
must always be rendered with a dot as the decimal separator and a
comma as the thousands separator, whatever the language of the visitor.
"""

# Decimal separator symbol (100.000 DT).
DECIMAL_SEPARATOR = "."

# Thousands separator symbol.
THOUSAND_SEPARATOR = ","

# Number of digits in every group of thousands.
NUMBER_GROUPING = 3
