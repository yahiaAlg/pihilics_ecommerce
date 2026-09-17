"""
cart.views

Spec 6.8 (Cart page) and 7.3 (Promo codes). Mutating endpoints
(add/update/remove/promo) follow the Post-Redirect-Get pattern for a plain
form submission, but respond with JsonResponse instead when the request is
AJAX (`X-Requested-With: XMLHttpRequest`) — the one explicitly allowed
AJAX use case here is "live cart totals" (spec Key Requirements), which
covers exactly this: the cart panel recalculating without a full reload as
the visitor changes a quantity or applies a code.
"""

from decimal import Decimal

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from catalog.templatetags.catalog_extras import _currency_affixes
from orders.utils import calculate_discount, calculate_shipping_cost

from .forms import AddToCartForm, CartItemUpdateForm, PromoCodeForm
from .models import CartItem
from .utils import (
    add_item_to_cart,
    apply_promo_to_session,
    clear_promo_from_session,
    get_applied_promo_code,
    get_cart,
)


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _cart_summary(cart, request):
    """Spec 6.8.2: subtotal, a shipping estimate (BR-CHK-02, standard rate — the
    Express surcharge only applies once a delivery method is chosen at Checkout),
    any applied discount, and the resulting total. No VAT line here — VAT depends
    on the delivery destination, which isn't known until Checkout (BR-CHK-04)."""
    subtotal = cart.subtotal
    promo_code = get_applied_promo_code(request)
    discount_amount = calculate_discount(subtotal, promo_code)
    shipping_cost = calculate_shipping_cost(subtotal, delivery_method="standard")
    total = subtotal - discount_amount + shipping_cost
    return {
        "item_count": cart.item_count,
        "subtotal": str(subtotal),
        "discount_amount": str(discount_amount),
        "shipping_cost": str(shipping_cost),
        "free_shipping": shipping_cost == 0,
        "total": str(total),
        "promo_code": promo_code.code if promo_code else None,
    }


def _option_rows(item):
    """
    Template-presentation helper for cart.html's `.item-meta` line, mirroring
    the static build's inline optHTML construction ('Color: X' + one row per
    priced upgrade). Kept in the view (not duplicated as template logic) per
    the djangofication brief's rule 4 — the actual currency formatting still
    happens in the template via the shared `arko_price` filter; this only
    decides *which* rows exist and pre-parses each upgrade's price_delta
    (stored as a str in the JSONField, see CartItem.unit_price) into a
    Decimal the template can cleanly test for truthiness/format.
    """
    rows = []
    if item.selected_color:
        rows.append({"label": f"Color: {item.selected_color}", "price": None})
    for upgrade in item.selected_upgrades or []:
        price = Decimal(str(upgrade.get("price_delta", 0)))
        rows.append({"label": upgrade.get("option", ""), "price": price or None})
    return rows


def cart_detail_view(request):
    cart = get_cart(request)
    items = list(cart.items.select_related("product", "product__category"))
    for item in items:
        item.option_rows = _option_rows(item)
    prefix, suffix = _currency_affixes()
    return render(request, "cart/cart.html", {
        "cart": cart,
        "items": items,
        "summary": _cart_summary(cart, request),
        "promo_form": PromoCodeForm(),
        "update_forms": {item.pk: CartItemUpdateForm(initial={"quantity": item.quantity}) for item in items},
        # Same server-sourced affixes financing.html's calculator uses, so
        # the AJAX-updated qty/summary figures below match the initial
        # server-rendered `|price` amounts instead of a hardcoded "€".
        "currency_affixes": {"prefix": prefix, "suffix": suffix},
    })


@require_POST
def add_to_cart_view(request):
    """Spec 6.8 entry points: product card, product detail, Quick View, Configurator all post here."""
    cart = get_cart(request)
    form = AddToCartForm(request.POST)
    if form.is_valid():
        product = form.get_product()
        item = add_item_to_cart(
            cart, product,
            quantity=form.cleaned_data["quantity"],
            selected_color=form.cleaned_data.get("color", ""),
            selected_size=form.cleaned_data.get("size", ""),
            selected_upgrades=form.get_selected_upgrades(),
        )
        if _is_ajax(request):
            return JsonResponse({"ok": True, "item_id": item.pk, "summary": _cart_summary(cart, request)})
        messages.success(request, f'Added "{product.name}" to your cart.')
        return redirect(request.POST.get("next") or "cart:cart_detail")

    if _is_ajax(request):
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    # BUG FOUND & FIXED (this session): this used to only surface
    # form.non_field_errors() as messages, so a field-level validation
    # failure (e.g. AddToCartForm.clean()'s "Please select a color" on a
    # product with colors) silently redirected with no toast and nothing
    # added to the cart -- the shopper got no feedback at all. Every error
    # (field-level and non-field) is now shown.
    for field_errors in form.errors.values():
        for error in field_errors:
            messages.error(request, error)
    return redirect(request.POST.get("next") or "cart:cart_detail")


@require_POST
def update_cart_item_view(request, item_id):
    cart = get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    form = CartItemUpdateForm(request.POST)
    if form.is_valid():
        item.quantity = form.cleaned_data["quantity"]
        item.save(update_fields=["quantity"])
        if _is_ajax(request):
            return JsonResponse({"ok": True, "summary": _cart_summary(cart, request)})
    elif _is_ajax(request):
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    return redirect("cart:cart_detail")


@require_POST
def remove_cart_item_view(request, item_id):
    cart = get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    product_name = item.product.name
    item.delete()
    if _is_ajax(request):
        return JsonResponse({"ok": True, "summary": _cart_summary(cart, request)})
    messages.success(request, f'Removed "{product_name}" from your cart.')
    return redirect("cart:cart_detail")


@require_POST
def clear_cart_view(request):
    """
    PRG POST endpoint for the Cart page's "Clear Cart" button. No equivalent
    existed anywhere in the pre-existing backend (only per-item remove) —
    this is the real, server-side version of the static build's clearCart()
    bulk removal, following the exact precedent catalog.views.compare_clear_view
    set in Step 2 for the same class of "one user-facing bulk action" gap.
    """
    cart = get_cart(request)
    cart.items.all().delete()
    messages.success(request, "Cart cleared.")
    return redirect("cart:cart_detail")


@require_POST
def apply_promo_view(request):
    cart = get_cart(request)
    form = PromoCodeForm(request.POST, cart=cart)
    if form.is_valid():
        apply_promo_to_session(request, form.get_promo_code())
        if _is_ajax(request):
            return JsonResponse({"ok": True, "summary": _cart_summary(cart, request)})
        messages.success(request, f'Promo code "{form.cleaned_data["code"]}" applied.')
    else:
        if _is_ajax(request):
            return JsonResponse({"ok": False, "errors": form.errors}, status=400)
        messages.error(request, "Invalid promo code.")
    return redirect("cart:cart_detail")


@require_POST
def remove_promo_view(request):
    cart = get_cart(request)
    clear_promo_from_session(request)
    if _is_ajax(request):
        return JsonResponse({"ok": True, "summary": _cart_summary(cart, request)})
    return redirect("cart:cart_detail")


def cart_totals_json(request):
    """AJAX (allowed use case: "live cart totals"). GET-only recompute, used to refresh the summary panel."""
    cart = get_cart(request)
    return JsonResponse(_cart_summary(cart, request))
