"""
accounts.views

Spec 6.17 (Account — a single tabbed page) and 6.18 (Login/Register).
`login_view` calling Django's own `login()` is also what makes
cart.signals.merge_guest_cart_into_account and catalog.signals' Wishlist/
Compare merges fire (they listen on the built-in `user_logged_in`
signal), so BR-CART-03's guest-to-account merge happens automatically
here with no extra call in the merge sense -- but see `_login()` below
for a real bug this uncovered.

BUG FOUND & FIXED (TODO.md): Django's own `login()` calls
`request.session.cycle_key()` for a previously-anonymous session *before*
it sends `user_logged_in` -- a deliberate session-fixation protection, but
it means the guest cart/wishlist/compare rows (keyed to the *old* session
key) become unreachable via `request.session.session_key` by the time any
`user_logged_in` receiver runs, silently turning every guest-to-account
merge into a no-op. Reproduced against a live DB (guest cart/wishlist/
compare all survived, orphaned, under their old session key after login)
before this fix. `_login()` below stashes the pre-rotation session key on
the request as `_pre_login_session_key` right before calling Django's
`login()`; `cart.signals` / `catalog.signals` read that attribute first,
falling back to `request.session.session_key` only for some other login
path that doesn't go through this helper.
"""

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AddressForm, LoginForm, PreferencesForm, ProfileForm, RegisterForm
from .models import Address


def _login(request, user):
    """See module docstring's BUG FOUND & FIXED note -- always use this instead of calling auth_login() directly."""
    request._pre_login_session_key = request.session.session_key
    auth_login(request, user)


def register_view(request):
    """Spec 6.18 Register. Registering logs the customer straight in (no separate confirmation step described)."""
    if request.user.is_authenticated:
        return redirect("accounts:account")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            _login(request, user)
            messages.success(request, f"Welcome to ARKO, {user.first_name}.")
            return redirect("accounts:account")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    """Spec 6.18 Login."""
    if request.user.is_authenticated:
        return redirect("accounts:account")

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            user = form.get_user()
            _login(request, user)
            if not form.cleaned_data.get("remember_me"):
                request.session.set_expiry(0)
            next_url = request.POST.get("next") or request.GET.get("next")
            return redirect(next_url or "accounts:account")
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    if request.method == "POST":
        auth_logout(request)
    return redirect("content:home")


@login_required
def account_view(request):
    """
    Spec 6.17: one page, several tabs — Profile, Garage, Orders,
    Wishlist, Preferences, Addresses. Tab content is all gathered up
    front since the page doesn't reload between tabs.

    CORRECTION (djangofication pass): this view's previous docstring
    claimed "the static build doesn't show [Wishlist] as [an Account
    tab] either" -- that's factually wrong. account.html's reference
    markup has a `data-section="wishlist"` nav item and a `sec-wishlist`
    panel, populated from `ARKO_STORE.getWishlist()`. Restored here,
    backed by the real `catalog.Wishlist` model via `get_wishlist()`
    (same account-scoped collection catalog:wishlist itself reads) --
    not duplicated storage, just the same data shown in a second place,
    matching the reference exactly.
    """
    from catalog.models import Product
    from catalog.utils import get_wishlist

    profile = request.user.profile
    wishlist_ids = get_wishlist(request).product_ids
    return render(request, "accounts/account.html", {
        "profile_form": ProfileForm(instance=profile),
        "preferences_form": PreferencesForm(instance=profile),
        "address_form": AddressForm(),
        "addresses": request.user.addresses.all(),
        "garage_entries": request.user.garage_entries.select_related("product"),
        "recent_orders": request.user.orders.all()[:5],
        "wishlist_products": Product.objects.filter(pk__in=wishlist_ids, is_active=True),
    })


@login_required
def profile_update_view(request):
    if request.method != "POST":
        return redirect("accounts:account")
    form = ProfileForm(request.POST, instance=request.user.profile)
    if form.is_valid():
        form.save()
        messages.success(request, "Your profile has been updated.")
    else:
        messages.error(request, "Please correct the errors below.")
    return redirect("accounts:account")


@login_required
def preferences_update_view(request):
    if request.method != "POST":
        return redirect("accounts:account")
    form = PreferencesForm(request.POST, instance=request.user.profile)
    if form.is_valid():
        form.save()
        messages.success(request, "Your preferences have been saved.")
    else:
        messages.error(request, "Please correct the errors below.")
    return redirect("accounts:account")


@login_required
def address_create_view(request):
    if request.method != "POST":
        return redirect("accounts:account")
    form = AddressForm(request.POST)
    if form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        address.save()
        messages.success(request, "Address added.")
    else:
        messages.error(request, "Please correct the errors below.")
    return redirect("accounts:account")


@login_required
def address_update_view(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method != "POST":
        return redirect("accounts:account")
    form = AddressForm(request.POST, instance=address)
    if form.is_valid():
        form.save()
        messages.success(request, "Address updated.")
    else:
        messages.error(request, "Please correct the errors below.")
    return redirect("accounts:account")


@login_required
def address_delete_view(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        address.delete()
        messages.success(request, "Address removed.")
    return redirect("accounts:account")
