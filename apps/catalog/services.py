"""Catalog business services."""
from decimal import Decimal
from .models import Product


def compute_retail_price(raw_cost, markup_percent, fixed_margin_fee):
    """Retail Price = (Source Cost * (1 + Markup% / 100)) + Fixed Margin Fee."""
    cost = raw_cost or Decimal("0")
    markup = markup_percent or Decimal("0")
    fixed = fixed_margin_fee or Decimal("0")
    return (cost * (1 + markup / Decimal("100"))) + fixed


def update_product_pricing(product):
    """Recompute and persist retail price for a product."""
    product.retail_price = compute_retail_price(
        product.raw_cost, product.markup_percent, product.fixed_margin_fee
    )
    product.save(update_fields=["retail_price", "updated_at"])
    return product.retail_price
