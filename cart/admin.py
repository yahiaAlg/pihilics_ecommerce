"""
cart.admin

Carts are largely a live, derived view of a shopping session rather than a
record to author by hand — the admin here is read-mostly (helpful for
support/debugging a customer's cart) except for `PromoCode`, which is a
genuine business record Store Admins manage directly.
"""

from django.contrib import admin

from .models import Cart, CartItem, PromoCode


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "quantity", "selected_color", "selected_size", "unit_price", "line_total")
    readonly_fields = ("unit_price", "line_total")
    autocomplete_fields = ("product",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "item_count", "subtotal", "updated_at")
    search_fields = ("user__username", "user__email", "session_key")
    readonly_fields = ("created_at", "updated_at")
    inlines = [CartItemInline]


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_percent", "valid_from", "valid_until", "min_order_value", "is_active")
    list_filter = ("is_active",)
    list_editable = ("is_active",)
    search_fields = ("code",)
