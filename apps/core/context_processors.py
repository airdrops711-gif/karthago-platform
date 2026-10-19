"""Global context processors for Karthago Platform."""
from apps.orders.constants import TUNISIAN_GOVERNORATES


def tunisian_governorates(request):
    """Make the 24 Tunisian governorates available in every template."""
    return {"governorates": TUNISIAN_GOVERNORATES}
