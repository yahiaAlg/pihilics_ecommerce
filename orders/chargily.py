"""
orders.chargily

Thin wrapper around the `chargily-pay` SDK for CIB/Edahabia card payments.
Kept as its own module (rather than inlined into views/signals) so it's the
one place that knows about Chargily's specific request/response shapes --
everything else in the app talks to it only through create_checkout_for_order
and verify_webhook_signature.

Why a real gateway is needed at all: there is no way to accept a CIB or
Edahabia card directly. Both card families clear through SATIM (Algeria's
domestic interbank switch), and a merchant has no way to reach SATIM without
either months of direct bank onboarding or a payment gateway that has
already done that onboarding and rents out the connection through an API --
which is exactly what Chargily is, and the only reason this module exists.

Test and live are two entirely separate environments (base URL *and* key
pair, not a single flag) -- see settings.CHARGILY_API_URL /
CHARGILY_KEY / CHARGILY_SECRET. That split is Chargily's own design, kept
deliberately: it's much harder to *accidentally* charge a real card if
doing so requires actively swapping both the URL and the keys.

What "CIB and Edahabia" means for the checkout we create: Chargily's own
hosted page offers `edahabia`, `cib`, and `chargily_app` (its own in-app QR
wallet) as payment methods, and which of those are actually enabled is a
Dashboard setting on the Chargily account, not something this integration
controls per-request -- passing `payment_method` on Checkout forces the
page to skip straight to one specific method, which isn't what we want when
offering both, so it's deliberately left unset here. To restrict the
account to CIB + Edahabia only (excluding chargily_app), disable it under
Developers Corner in the Chargily dashboard.
"""

import hashlib
import hmac
import logging
from decimal import ROUND_HALF_UP

from django.conf import settings

from chargily_pay import ChargilyClient
from chargily_pay.entity import Checkout

from .models import PaymentState

logger = logging.getLogger("orders.chargily")

# checkout.<event> -> the PaymentState an order should move to. Mirrors
# Chargily's own Checkout.status values 1:1 except `pending`/`processing`,
# which we fold into our own PENDING (a customer mid-payment on Chargily's
# page and a checkout that hasn't been touched yet are both, from our side,
# simply "not resolved").
WEBHOOK_EVENT_STATES = {
    "checkout.paid": PaymentState.CONFIRMED,
    "checkout.failed": PaymentState.FAILED,
    "checkout.canceled": PaymentState.CANCELED,
    "checkout.expired": PaymentState.EXPIRED,
}


class ChargilyError(Exception):
    """
    Raised by create_checkout_for_order on any failure to reach Chargily or
    get back a usable response -- network error, non-2xx, or a malformed
    body missing the fields we need. Callers (the placement view, the
    retry view) catch this specifically so a Chargily outage degrades to
    "show a retry button" rather than a 500 that loses the order.
    """


def get_client():
    """
    A fresh client per call rather than a module-level singleton: this
    keeps the module import-safe with no configured keys at all (a bare
    checkout of this project, or any test that never touches Chargily),
    and it means changing settings mid-process -- exactly what the verify
    suite does, pointing this at a fake key/URL pair -- takes effect
    immediately rather than being frozen at import time.
    """
    return ChargilyClient(
        key=settings.CHARGILY_KEY,
        secret=settings.CHARGILY_SECRET,
        url=settings.CHARGILY_API_URL,
    )


def _amount_in_dzd(order):
    """
    Chargily's `amount` is a plain integer count of whole DZD -- unlike
    Stripe's "smallest currency unit" cents, there is no implicit x100
    scaling. Order.total is a Decimal with 2 decimal places (the schema
    supports centimes even though Algerian retail practice rarely prices
    in them), so this rounds to the nearest whole dinar rather than
    truncating -- ROUND_HALF_UP so a .50 order total rounds up rather than
    silently discounting the customer by half a dinar.
    """
    return int(order.total.to_integral_value(rounding=ROUND_HALF_UP))


def _return_url(order, outcome):
    """
    Where Chargily sends the browser back to -- always our own
    order_payment page, distinguished only by a `from` query param so the
    view can show a transient "confirming your payment" / "that didn't go
    through" banner. This is UX only: the query param never changes
    payment_state, which only the webhook is trusted to set (Part I of the
    integration guide is explicit that the redirect and the webhook are
    not the same signal, and only one of them is proof).
    """
    from django.urls import reverse

    path = reverse("orders:order_payment", args=[order.reference])
    return f"{settings.SITE_URL}{path}?from=chargily_{outcome}"


def create_checkout_for_order(order):
    """
    Creates a Chargily Checkout for `order` and stores the id/url on it.

    Raises ChargilyError rather than letting requests' own exceptions
    (ConnectionError, HTTPError, ...) or a malformed-response KeyError
    escape -- every caller needs exactly one exception type to catch to
    know "the checkout could not be created, show a retry option," not a
    grab-bag of transport-layer exception classes.
    """
    try:
        response = get_client().create_checkout(
            Checkout(
                amount=_amount_in_dzd(order),
                currency="dzd",
                success_url=_return_url(order, "success"),
                failure_url=_return_url(order, "failure"),
                webhook_endpoint=f"{settings.SITE_URL}/payments/chargily/webhook/",
                description=f"Pihilics order {order.reference}",
                locale="fr",
                metadata=[{"order_reference": order.reference}],
            )
        )
        checkout_id = response["id"]
        checkout_url = response["checkout_url"]
    except Exception as exc:  # noqa: BLE001 -- collapsing every transport/shape error into one type
        logger.warning("Chargily checkout creation failed for order %s: %s", order.reference, exc)
        raise ChargilyError(str(exc)) from exc

    order.chargily_checkout_id = checkout_id
    order.chargily_checkout_url = checkout_url
    order.payment_state = PaymentState.PENDING
    order.save(update_fields=["chargily_checkout_id", "chargily_checkout_url", "payment_state"])
    return checkout_url


def verify_webhook_signature(payload, signature):
    """
    Recomputes the HMAC-SHA256 of the raw webhook body with our secret key
    and compares it to the `signature` header, using hmac.compare_digest
    (not `==`) to avoid a timing side-channel.

    `payload` must be the exact raw bytes Chargily sent -- request.body,
    read before anything parses it into request.POST or similar. Signing
    is over those exact bytes, so re-serializing a parsed dict first
    (different whitespace/key order) silently breaks verification; this is
    the single most common integration bug with any HMAC-signed webhook,
    Chargily included.
    """
    if not signature or not settings.CHARGILY_SECRET:
        return False
    computed = hmac.new(settings.CHARGILY_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, computed)
