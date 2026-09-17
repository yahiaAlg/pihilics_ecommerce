"""
cart.utils
"""

from django.db import transaction

from .models import Cart, CartItem, PromoCode


def get_cart(request):
    """
    BR-CART-02: a registered customer's cart is keyed to their account; a
    guest's is keyed to their session. Returns the right one for the
    current request, creating it on first use.
    """
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart

    if not request.session.session_key:
        request.session.save()

    cart = Cart.objects.filter(session_key=request.session.session_key, user__isnull=True).first()
    if cart is None:
        cart = Cart.objects.create(session_key=request.session.session_key)
    return cart


def add_item_to_cart(cart, product, quantity=1, selected_color="", selected_size="", selected_upgrades=None):
    """
    BR-CART-01: a line's identity is (product, color, size, sorted selected
    upgrades). Matching identity increments quantity on the existing line;
    any difference creates a new, separate line.
    """
    selected_upgrades = selected_upgrades or []
    probe = CartItem(
        cart=cart,
        product=product,
        selected_color=selected_color,
        selected_size=selected_size,
        selected_upgrades=selected_upgrades,
    )
    options_key = probe.compute_options_key()

    with transaction.atomic():
        existing = cart.items.filter(product=product, options_key=options_key).first()
        if existing:
            existing.quantity += quantity
            existing.full_clean(exclude=["cart", "product", "options_key"])
            existing.save(update_fields=["quantity"])
            return existing

        probe.quantity = quantity
        probe.full_clean(exclude=["options_key"])
        probe.save()
        return probe


CART_PROMO_SESSION_KEY = "cart_promo_code"


def apply_promo_to_session(request, promo_code):
    """BR-CHK-03: applying a code on the Cart page stores it on the session (Cart has no promo_code column)
    so Checkout automatically honors it without the visitor re-entering it."""
    request.session[CART_PROMO_SESSION_KEY] = promo_code.code


def clear_promo_from_session(request):
    request.session.pop(CART_PROMO_SESSION_KEY, None)


def get_applied_promo_code(request):
    """Resolves the session-stored code back into a live PromoCode, dropping it silently if it has since been deactivated."""
    code = request.session.get(CART_PROMO_SESSION_KEY)
    if not code:
        return None
    promo_code = PromoCode.objects.filter(code=code, is_active=True).first()
    if promo_code is None:
        clear_promo_from_session(request)
    return promo_code
