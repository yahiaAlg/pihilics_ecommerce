"""
verify_chargily

Exercises orders/chargily.py and the CIB/Edahabia checkout flow end to
end: placement -> redirect to Chargily -> webhook -> mail, plus the
failure/retry paths.

Everything that would otherwise be a real HTTP call to pay.chargily.net is
monkeypatched at orders.chargily.get_client -- this environment's network
allowlist doesn't include Chargily's domain anyway (same situation as
mail.pihilics-product.com in verify_emails.py), and even with it allowed,
a verify script has no business making real API calls against a real
merchant account on every run. What IS real: the Django views, the model
transitions, the signal-driven mail, and the webhook's own HMAC
verification -- only the one network boundary is faked.
"""

import hashlib
import hmac
import json
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings

settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
settings.CHARGILY_SECRET = "verify-test-secret"
settings.CHARGILY_KEY = "test_pk_verify"

from decimal import Decimal

from django.core import mail
from django.test import Client

import orders.chargily as chargily
from catalog.models import Product
from orders.models import Order, PaymentMethod, PaymentState


def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(extra)) if extra else ""))
    assert cond, label


def reset_mail():
    mail.outbox = []


def to_all(message):
    return list(message.to) + list(getattr(message, "cc", []) or [])


class FakeChargilyClient:
    """
    Stands in for chargily_pay.ChargilyClient. `create_checkout` returns a
    response shaped like the real API's (id + checkout_url), recording
    every call it received so tests can assert on what we actually sent
    (amount, success_url, ...) without a real request ever leaving this
    process. `fail` flips it into "Chargily is unreachable" mode, for
    exercising create_checkout_for_order's own error handling.
    """

    calls = []
    fail = False
    _counter = 0

    @classmethod
    def create_checkout(cls, checkout):
        cls.calls.append(checkout)
        if cls.fail:
            raise ConnectionError("simulated: Chargily unreachable")
        cls._counter += 1
        return {
            "id": f"fake-checkout-{cls._counter}",
            "checkout_url": f"https://pay.chargily.dz/test/checkouts/fake-checkout-{cls._counter}/pay",
            "amount": checkout.amount,
            "status": "pending",
        }

    @classmethod
    def reset(cls):
        cls.calls = []
        cls.fail = False
        cls._counter = 0


chargily.get_client = lambda: FakeChargilyClient


def sign(payload_bytes):
    return hmac.new(settings.CHARGILY_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()


def webhook_payload(event_type, checkout_id, amount=48600, status="paid"):
    body = json.dumps({
        "id": "evt_" + checkout_id,
        "entity": "event",
        "livemode": False,
        "type": event_type,
        "data": {
            "id": checkout_id, "entity": "checkout", "amount": amount,
            "status": status, "success_url": "https://pihilics.dz/x", "url": "https://pay.chargily.dz/x",
        },
        "created_at": 1703578418,
    }).encode()
    return body


print("\n=== AMOUNT CONVERSION ===")
class FakeTotal:
    def __init__(self, value):
        self.total = Decimal(value)

ok("whole dinar amount unchanged", chargily._amount_in_dzd(FakeTotal("48600.00")) == 48600)
ok("fractional dinar rounds half-up", chargily._amount_in_dzd(FakeTotal("100.50")) == 101)
ok("fractional dinar rounds down when < .5", chargily._amount_in_dzd(FakeTotal("100.49")) == 100)

print("\n=== SIGNATURE VERIFICATION ===")
body = webhook_payload("checkout.paid", "abc123")
good_sig = sign(body)
ok("correct signature verifies", chargily.verify_webhook_signature(body, good_sig))
ok("wrong signature fails", not chargily.verify_webhook_signature(body, "0" * 64))
ok("missing signature fails", not chargily.verify_webhook_signature(body, ""))
ok("tampered body fails the original signature", not chargily.verify_webhook_signature(body + b" ", good_sig))

print("\n=== PLACE A CIB ORDER -> REDIRECT STRAIGHT TO CHARGILY ===")
FakeChargilyClient.reset()
reset_mail()
c = Client()
p = Product.objects.filter(is_active=True).first()
c.post("/cart/add/", {"product_id": p.id, "quantity": 1})
c.post("/checkout/information/", {"first_name": "Sami", "last_name": "Kaci",
                                   "email": "sami@example.com", "phone": "+213 555 0199"})
c.post("/checkout/delivery/", {"street": "9 Rue C", "city": "Setif", "postal_code": "19000",
                                "wilaya": "19", "delivery_method": "standard"})
c.post("/checkout/payment/", {"payment_method": "cib"})
r = c.post("/checkout/review/", {})
ok("placement redirects (302)", r.status_code == 302)
ok("redirected straight to Chargily's own checkout_url, not our success page",
   r["Location"].startswith("https://pay.chargily.dz/"), r["Location"])

order = Order.objects.filter(payment_method=PaymentMethod.CIB).order_by("-id").first()
ok("order exists with payment_method cib", order is not None)
ok("payment_state is PENDING", order.payment_state == PaymentState.PENDING, order.payment_state)
ok("chargily_checkout_id stored", bool(order.chargily_checkout_id))
ok("chargily_checkout_url matches the redirect target", order.chargily_checkout_url == r["Location"])
ok("exactly one Chargily API call made", len(FakeChargilyClient.calls) == 1, len(FakeChargilyClient.calls))
sent = FakeChargilyClient.calls[0]
ok("amount sent as a whole-DZD integer", sent.amount == chargily._amount_in_dzd(order), sent.amount)
ok("currency is dzd", sent.currency == "dzd")
ok("success/failure urls point back at order_payment", "/payment/?from=chargily_" in sent.success_url
   and "/payment/?from=chargily_" in sent.failure_url)
ok("webhook_endpoint points at our fixed webhook route", sent.webhook_endpoint.endswith("/payments/chargily/webhook/"))
ok("no payment_method forced on the Checkout (both CIB and Edahabia stay selectable)",
   sent.payment_method is None)
ok("placing the order still sent the standard receipt + admin alert (2 emails)",
   len(mail.outbox) == 2, len(mail.outbox))

print("\n=== ORDER_PAYMENT PAGE FOR A LIVE PENDING CHECKOUT ===")
pay_url = f"/orders/{order.reference}/payment/"
r = c.get(pay_url)
ok("page renders", r.status_code == 200)
html = r.content.decode()
ok("offers to resume the live checkout rather than recreate one",
   "Continue to Payment" in html and order.chargily_checkout_url in html)
ok("shows the amount to pay", "DA" in html)

stranger = Client()
r = stranger.get(pay_url)
ok("a stranger cannot reach the payment page", r.status_code == 302 and "lookup" in r["Location"])

print("\n=== WEBHOOK: checkout.paid CONFIRMS THE ORDER ===")
reset_mail()
body = webhook_payload("checkout.paid", order.chargily_checkout_id)
r = c.post("/payments/chargily/webhook/", data=body, content_type="application/json",
           headers={"signature": sign(body)})
ok("webhook returns 200", r.status_code == 200, r.status_code)
order.refresh_from_db()
ok("order flips to CONFIRMED", order.payment_state == PaymentState.CONFIRMED, order.payment_state)
ok("confirmation emails only the customer", len(mail.outbox) == 1, len(mail.outbox))
ok("confirmation goes to the order's contact email", "sami@example.com" in to_all(mail.outbox[0]))
confirmed_html = dict((ct, b) for b, ct in mail.outbox[0].alternatives)["text/html"]
ok("confirmation email uses card wording, not transfer wording", "card payment" in confirmed_html.lower())

reset_mail()
r = c.post("/payments/chargily/webhook/", data=body, content_type="application/json",
           headers={"signature": sign(body)})
ok("re-delivering the same webhook event is a 200 no-op", r.status_code == 200)
ok("no duplicate confirmation email on webhook retry", len(mail.outbox) == 0, len(mail.outbox))

print("\n=== WEBHOOK SECURITY ===")
r = c.post("/payments/chargily/webhook/", data=body, content_type="application/json",
           headers={"signature": "0" * 64})
ok("bad signature is rejected (403)", r.status_code == 403, r.status_code)

unknown_body = webhook_payload("checkout.paid", "checkout-does-not-exist")
r = c.post("/payments/chargily/webhook/", data=unknown_body, content_type="application/json",
           headers={"signature": sign(unknown_body)})
ok("unknown checkout id still returns 200 (no retry storm)", r.status_code == 200, r.status_code)

r = c.get("/payments/chargily/webhook/")
ok("GET is rejected (POST-only)", r.status_code == 405, r.status_code)

print("\n=== WEBHOOK: FAILED / CANCELED / EXPIRED ARE RECOVERABLE ===")
for event_type, expected_state in (
    ("checkout.failed", PaymentState.FAILED),
    ("checkout.canceled", PaymentState.CANCELED),
    ("checkout.expired", PaymentState.EXPIRED),
):
    FakeChargilyClient.reset()
    reset_mail()
    c2 = Client()
    c2.post("/cart/add/", {"product_id": p.id, "quantity": 1})
    c2.post("/checkout/information/", {"first_name": "Rania", "last_name": "Bensalem",
                                        "email": "rania@example.com", "phone": "+213 555 0155"})
    c2.post("/checkout/delivery/", {"street": "2 Rue D", "city": "Setif", "postal_code": "19000",
                                     "wilaya": "19", "delivery_method": "standard"})
    c2.post("/checkout/payment/", {"payment_method": "cib"})
    c2.post("/checkout/review/", {})
    order2 = Order.objects.filter(payment_method=PaymentMethod.CIB).order_by("-id").first()

    reset_mail()
    body2 = webhook_payload(event_type, order2.chargily_checkout_id)
    r = c2.post("/payments/chargily/webhook/", data=body2, content_type="application/json",
                headers={"signature": sign(body2)})
    order2.refresh_from_db()
    ok(f"{event_type} moves order to {expected_state}", order2.payment_state == expected_state,
       order2.payment_state)
    ok(f"{event_type} emails the customer a retry-framed notice", len(mail.outbox) == 1, len(mail.outbox))
    ok(f"{event_type} leaves the order retryable", order2.can_retry_card_payment)

    r = c2.get(f"/orders/{order2.reference}/payment/")
    ok(f"payment page after {event_type} offers Try Payment Again",
       "Try Payment Again" in r.content.decode())

print("\n=== RETRY: A NEW CHECKOUT IS CREATED ON DEMAND ===")
FakeChargilyClient.reset()
r = c2.post(f"/orders/{order2.reference}/payment/", {})
ok("retry POST redirects to a fresh Chargily checkout", r.status_code == 302
   and r["Location"].startswith("https://pay.chargily.dz/"))
order2.refresh_from_db()
ok("payment_state back to PENDING", order2.payment_state == PaymentState.PENDING)
ok("exactly one new API call made for the retry", len(FakeChargilyClient.calls) == 1)

print("\n=== PLACEMENT-TIME FAILURE DEGRADES GRACEFULLY ===")
FakeChargilyClient.reset()
FakeChargilyClient.fail = True
reset_mail()
c3 = Client()
c3.post("/cart/add/", {"product_id": p.id, "quantity": 1})
c3.post("/checkout/information/", {"first_name": "Nour", "last_name": "Zerrouki",
                                    "email": "nour@example.com", "phone": "+213 555 0166"})
c3.post("/checkout/delivery/", {"street": "5 Rue E", "city": "Setif", "postal_code": "19000",
                                 "wilaya": "19", "delivery_method": "standard"})
c3.post("/checkout/payment/", {"payment_method": "cib"})
r = c3.post("/checkout/review/", {})
ok("order is still created even though Chargily is unreachable", r.status_code == 302)
order3 = Order.objects.filter(contact_email="nour@example.com").order_by("-id").first()
ok("falls back to the success page, not a 500", r["Location"].endswith(f"/orders/{order3.reference}/success/"))
ok("payment_state is PENDING with no checkout_url yet", order3.payment_state == PaymentState.PENDING
   and not order3.chargily_checkout_url)
ok("can_retry_card_payment is True", order3.can_retry_card_payment)
ok("can_resume_card_checkout is False (nothing to resume)", not order3.can_resume_card_checkout)

r = c3.get(r["Location"])
ok("success page shows a Complete Payment CTA for the stalled CIB order", "Complete Payment" in r.content.decode())
ok("success page says Total Due, not Total Paid", "Total Due" in r.content.decode())

FakeChargilyClient.fail = False
r = c3.post(f"/orders/{order3.reference}/payment/", {})
ok("retrying from the payment page now succeeds", r.status_code == 302
   and r["Location"].startswith("https://pay.chargily.dz/"))
order3.refresh_from_db()
ok("order3 now has a live checkout", bool(order3.chargily_checkout_url))

print("\nALL CHARGILY CHECKS PASSED")
