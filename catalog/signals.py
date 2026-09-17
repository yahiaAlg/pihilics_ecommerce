"""
catalog.signals

TODO.md "Major" fix: Wishlist and Compare are now real, persisted,
session-vs-account collections (see models.py), so they need the same
guest-to-account merge-on-login behavior cart.signals already implements
for Cart (BR-CART-03). Two separate receivers, mirroring
cart.signals.merge_guest_cart_into_account's shape rather than one generic
helper, since the two collections differ slightly (Compare enforces the
4-model cap from spec 6.6 while merging; Wishlist doesn't cap).

BUG FOUND & FIXED (TODO.md, same root cause as cart.signals): Django's
`login()` rotates a previously-anonymous session's key *before* sending
`user_logged_in`, so reading `request.session.session_key` here would
silently never find the guest Wishlist/Compare row (it's keyed to the
now-discarded old session key). Both receivers below read
`request._pre_login_session_key` first -- set by accounts.views._login()
right before it calls Django's `login()` -- falling back to
`request.session.session_key` only for some other login path that
doesn't go through that helper.
"""

from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.dispatch import receiver

from .models import Compare, Wishlist


@receiver(user_logged_in)
def merge_guest_wishlist_into_account(sender, request, user, **kwargs):
    """Merge the guest session's Wishlist (if any) into the user's account Wishlist, then discard the guest one."""
    session_key = getattr(request, "_pre_login_session_key", None) or request.session.session_key
    if not session_key:
        return

    guest_wishlist = (
        Wishlist.objects.filter(session_key=session_key, user__isnull=True).prefetch_related("items").first()
    )
    if guest_wishlist is None or not guest_wishlist.items.exists():
        return

    with transaction.atomic():
        account_wishlist, _ = Wishlist.objects.get_or_create(user=user)
        existing_product_ids = set(account_wishlist.items.values_list("product_id", flat=True))
        for guest_item in guest_wishlist.items.all():
            if guest_item.product_id not in existing_product_ids:
                guest_item.pk = None
                guest_item.wishlist = account_wishlist
                guest_item.save()
        guest_wishlist.delete()


@receiver(user_logged_in)
def merge_guest_compare_into_account(sender, request, user, **kwargs):
    """Same merge as above for Compare, respecting the 4-model cap (spec 6.6) once merged into the account list."""
    session_key = getattr(request, "_pre_login_session_key", None) or request.session.session_key
    if not session_key:
        return

    guest_compare = (
        Compare.objects.filter(session_key=session_key, user__isnull=True).prefetch_related("items").first()
    )
    if guest_compare is None or not guest_compare.items.exists():
        return

    with transaction.atomic():
        account_compare, _ = Compare.objects.get_or_create(user=user)
        existing_product_ids = set(account_compare.items.values_list("product_id", flat=True))
        slots_left = 4 - account_compare.items.count()
        for guest_item in guest_compare.items.all():
            if slots_left <= 0:
                break
            if guest_item.product_id not in existing_product_ids:
                guest_item.pk = None
                guest_item.compare = account_compare
                guest_item.save()
                slots_left -= 1
        guest_compare.delete()
