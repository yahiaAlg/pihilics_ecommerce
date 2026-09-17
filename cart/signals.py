"""
cart.signals

BR-CART-03: "On login, a guest's session cart is merged into the customer's
account cart (matching lines combine by quantity; distinct lines are
appended)." Implemented on Django's built-in ``user_logged_in`` signal so it
fires uniformly regardless of which view performs the login (standard
Django auth login view, or a custom one built in a later phase).

BUG FOUND & FIXED (TODO.md): Django's `login()` rotates a previously-
anonymous session's key (`cycle_key()`, a session-fixation protection)
*before* sending `user_logged_in`, so `request.session.session_key` at
signal time is already the *new* key -- the guest cart, keyed to the old
one, was silently orphaned instead of merged. accounts.views._login()
stashes the pre-rotation key as `request._pre_login_session_key` right
before calling Django's `login()`; this receiver reads that first and
only falls back to `request.session.session_key` for some other login
path that doesn't go through that helper (in which case there's nothing
better to do than the old, technically-still-buggy behavior).
"""

from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.dispatch import receiver

from .models import Cart


@receiver(user_logged_in)
def merge_guest_cart_into_account(sender, request, user, **kwargs):
    """
    Merge the guest session's Cart (if any) into the user's persistent
    account Cart, then discard the now-empty guest cart.

    Line identity for merge purposes is (product, options_key) — the same
    identity CartItem itself enforces (BR-CART-01) — so this only ever
    combines truly-identical lines and appends everything else.
    """
    session_key = getattr(request, "_pre_login_session_key", None) or request.session.session_key
    if not session_key:
        return

    guest_cart = (
        Cart.objects.filter(session_key=session_key, user__isnull=True)
        .prefetch_related("items")
        .first()
    )
    if guest_cart is None or not guest_cart.items.exists():
        return

    with transaction.atomic():
        account_cart, _ = Cart.objects.get_or_create(user=user)

        for guest_item in guest_cart.items.all():
            existing_item = account_cart.items.filter(
                product_id=guest_item.product_id, options_key=guest_item.options_key
            ).first()
            if existing_item:
                existing_item.quantity += guest_item.quantity
                existing_item.save(update_fields=["quantity"])
            else:
                guest_item.pk = None
                guest_item.cart = account_cart
                guest_item.save()

        guest_cart.delete()
