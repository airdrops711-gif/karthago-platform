"""Django admin registration for the orders."""
from django.contrib import admin

from .models import (
    Cart,
    Customer,
    Delivery,
    Order,
    OrderEvent,
    OrderItem,
    PayoutSettlement,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product_title",
        "quantity",
        "unit_price",
        "unit_cost",
        "currency",
        "currency_rate",
    )
    can_delete = False


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ("from_status", "to_status", "note", "created_by", "created_at")
    can_delete = False
    ordering = ("-created_at",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "store",
        "status",
        "total_amount",
        "total_cost",
        "margin",
        "platform_cut",
        "vendor_payout",
        "is_settled",
        "created_at",
    )
    list_filter = ("status", "store", "payment_method", "is_settled", "created_at")
    search_fields = ("id", "customer__full_name", "customer__phone")
    autocomplete_fields = ("customer", "store")
    readonly_fields = (
        "created_at",
        "updated_at",
        "platform_cut",
        "vendor_payout",
        "gross_total",
        "supplier_cost",
        "is_delivered",
    )
    inlines = [OrderItemInline, OrderEventInline]

    @admin.display(description="Marge")
    def margin(self, obj):
        return obj.margin


@admin.register(PayoutSettlement)
class PayoutSettlementAdmin(admin.ModelAdmin):
    """The payout batches sent to the vendors."""

    list_display = (
        "reference",
        "store",
        "total_delivered_orders",
        "total_gmv",
        "total_platform_cut",
        "net_payout_to_vendor",
        "payout_method",
        "is_paid",
        "created_at",
    )
    list_filter = ("store", "payout_method", "is_paid", "created_at")
    search_fields = ("reference", "store__name", "store__slug")
    autocomplete_fields = ("store",)
    readonly_fields = ("created_at",)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "governorate", "store", "created_at")
    list_filter = ("governorate", "store")
    search_fields = ("full_name", "phone", "email")
    autocomplete_fields = ("store",)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_title", "quantity", "unit_price", "unit_cost")
    search_fields = ("product_title", "order__id")
    autocomplete_fields = ("order", "product")


@admin.register(OrderEvent)
class OrderEventAdmin(admin.ModelAdmin):
    list_display = ("order", "from_status", "to_status", "created_by", "created_at")
    list_filter = ("to_status",)
    search_fields = ("order__id", "note")
    autocomplete_fields = ("order",)


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("order", "tracking_number", "delivered_at", "paid_on_delivery")
    list_filter = ("paid_on_delivery",)
    autocomplete_fields = ("order",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("session_key", "product", "store", "quantity", "updated_at")
    search_fields = ("session_key", "product__title")
    autocomplete_fields = ("product", "store")
