"""
verify_emails

Exercises the notification layer built in core/emails.py and the three
per-app notifications modules. Same shape as the other verify_* scripts:
real models, real signals, real rendered templates -- no mocking of the
notification functions themselves.

The one thing it does swap is the transport. Settings pick smtp when
EMAIL_HOST_PASSWORD is set and console otherwise, and neither is
inspectable: console prints to stdout and smtp would send live mail to real
mailboxes every time anyone ran the suite. This forces Django's locmem
backend for the duration, which captures each message in django.core.mail.outbox
so the recipients, subjects, and body copy can actually be asserted on.

Note this verifies *composition and routing*, not deliverability. Whether
mail.pihilics-product.com accepts the credentials in .env is a separate,
network-dependent check:

    python manage.py shell -c "from django.core.mail import get_connection; get_connection().open()"
"""

import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]
# Must be set before any mail is sent; every send goes through
# django.core.mail.get_connection(), which reads this at call time.
settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

from datetime import timedelta

from django.core import mail
from django.utils import timezone

from bookings.models import BookingStatus, TestRideBooking
from catalog.models import Product, ProductType
from core.models import CompanyInfo
from dealers.models import Dealer
from orders.models import Order, OrderStatus
from support.models import ContactMessage


def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(extra)) if extra else ""))
    assert cond, label


def reset():
    mail.outbox = []


def to_all(message):
    return list(message.to) + list(getattr(message, "cc", []) or [])


company = CompanyInfo.get_solo()
admin_address = settings.ADMIN_NOTIFICATION_EMAIL

print("\n=== CONFIGURATION ===")
ok("admin notification address set", bool(admin_address), admin_address)
ok("admin address is separate from the SMTP login",
   admin_address != settings.EMAIL_HOST_USER, settings.EMAIL_HOST_USER)
ok("a default From is configured", bool(settings.DEFAULT_FROM_EMAIL), settings.DEFAULT_FROM_EMAIL)
ok("SMTP host/port look like the provider's", settings.EMAIL_HOST.endswith("pihilics-product.com")
   and settings.EMAIL_PORT in (465, 587), f"{settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
ok("SSL and TLS are not both on", not (settings.EMAIL_USE_SSL and settings.EMAIL_USE_TLS))

print("\n=== CONTACT FORM (support) ===")
reset()
message = ContactMessage.objects.create(
    name="Yacine Bouzid", email="yacine@example.com",
    subject="Battery question", message="How long does a full charge take?",
)
ok("two emails sent (customer ack + admin alert)", len(mail.outbox) == 2, len(mail.outbox))
recipients = [to_all(m)[0] for m in mail.outbox]
ok("customer acknowledged", "yacine@example.com" in recipients, recipients)
ok("admin alerted", admin_address in recipients, recipients)
admin_mail = next(m for m in mail.outbox if admin_address in to_all(m))
ok("admin alert replies to the customer, not the mailbox",
   list(admin_mail.reply_to or []) == ["yacine@example.com"], admin_mail.reply_to)
ok("admin alert carries the enquiry", "full charge" in admin_mail.body)
ok("HTML alternative attached",
   any(content_type == "text/html" for _, content_type in admin_mail.alternatives))
html = dict((ct, body) for body, ct in admin_mail.alternatives)["text/html"]
ok("branded wrapper rendered", company.trade_name in html and "</html>" in html)
message.delete()

print("\n=== ORDER PLACED ===")
order = Order.objects.exclude(contact_email="").order_by("-pk").first()
ok("a seeded order exists to notify on", order is not None, order and order.reference)
reset()
from orders.notifications import send_order_confirmation, send_order_status_update

send_order_confirmation(order)
ok("two emails sent (receipt + admin alert)", len(mail.outbox) == 2, len(mail.outbox))
customer_mail = next(m for m in mail.outbox if order.contact_email in to_all(m))
ok("receipt goes to the order's contact email", True, order.contact_email)
ok("subject carries the reference", order.reference in customer_mail.subject, customer_mail.subject)
ok("reference uses the PHL- format", order.reference.startswith("PHL-"), order.reference)
receipt_html = dict((ct, body) for body, ct in customer_mail.alternatives)["text/html"]
ok("no euro symbol anywhere in the receipt", "\u20ac" not in receipt_html)
ok("totals render in dinars", "DA" in receipt_html)
ok("plain-text alternative is not empty", len(customer_mail.body.strip()) > 50)

print("\n=== ORDER STATUS CHANGE (admin-driven) ===")
reset()
previous_status = order.status
order.status = OrderStatus.SHIPPED if previous_status != OrderStatus.SHIPPED else OrderStatus.DELIVERED
send_order_status_update(order)
opted_in = getattr(getattr(order.user, "profile", None), "order_notifications_opt_in", True)
if opted_in:
    ok("customer told about the new status", len(mail.outbox) == 1, len(mail.outbox))
    ok("new status named in the subject",
       order.get_status_display() in mail.outbox[0].subject, mail.outbox[0].subject)
else:
    ok("opted-out customer is not emailed", len(mail.outbox) == 0, len(mail.outbox))
order.status = previous_status

print("\n=== TEST-RIDE BOOKING + DEALER APPROVAL ===")
bike = Product.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True).first()
dealer = Dealer.objects.filter(is_active=True).first()
day = timezone.localdate() + timedelta(days=90)
while TestRideBooking.objects.filter(dealer=dealer, date=day).exclude(
        status=BookingStatus.CANCELLED).exists():
    day += timedelta(days=1)

reset()
booking = TestRideBooking.objects.create(
    product=bike, dealer=dealer, date=day, time_slot="morning",
    first_name="Nadia", last_name="Cherif", email="nadia@example.com",
    phone="+213 555 0142", license_number="DZ-44120", waiver_acknowledged=True,
)
ok("two emails sent on request (customer + admin)", len(mail.outbox) == 2, len(mail.outbox))
booking_recipients = [to_all(m)[0] for m in mail.outbox]
ok("rider acknowledged", "nadia@example.com" in booking_recipients, booking_recipients)
ok("admin alerted", admin_address in booking_recipients, booking_recipients)
admin_booking_mail = next(m for m in mail.outbox if admin_address in to_all(m))
ok("admin alert names the dealer", dealer.name in admin_booking_mail.subject, admin_booking_mail.subject)

reset()
booking.status = BookingStatus.CONFIRMED
booking.save()
ok("approval emails the rider", len(mail.outbox) == 1, len(mail.outbox))
ok("approval names the new status",
   booking.get_status_display() in mail.outbox[0].subject, mail.outbox[0].subject)
ok("approval goes only to the rider, not the admin",
   admin_address not in to_all(mail.outbox[0]))

reset()
booking.status = BookingStatus.CANCELLED
booking.save()
ok("cancellation also notifies", len(mail.outbox) == 1, len(mail.outbox))

reset()
booking.save()  # no status change
ok("a save with no status change sends nothing", len(mail.outbox) == 0, len(mail.outbox))

booking.delete()

print("\n=== BARIDIMOB PAYMENT CYCLE ===")
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from orders.models import Order, PaymentMethod, PaymentProof, PaymentProofStatus, PaymentState

company.sales_rip = "00799999001234567890"
company.sales_ccp_number = "1234567 89"
company.sales_payment_email = "sales-verify@pihilics.dz"
company.save()

bike_for_mail = Product.objects.filter(is_active=True).first()
reset()
bm_order = Order.objects.create(
    guest_email="karim@example.com", guest_name="Karim Yahia",
    contact_first_name="Karim", contact_last_name="Yahia",
    contact_email="karim@example.com", contact_phone="+213 555 0177",
    delivery_street="1 Rue Test", delivery_city="Setif", delivery_postal_code="19000",
    delivery_wilaya="19", payment_method=PaymentMethod.BARIDIMOB,
    subtotal=Decimal("40000.00"), shipping_cost=Decimal("1000.00"),
    vat_amount=Decimal("7600.00"), total=Decimal("48600.00"),
)
ok("BaridiMob order starts AWAITING_PROOF", bm_order.payment_state == PaymentState.AWAITING_PROOF)
# Placing any order already sends the standard receipt + admin alert
# (send_order_confirmation, unconditional on payment method) — BaridiMob
# adds a third, the payment instructions. Three, not one, is correct here.
ok("placing it sends receipt + admin alert + payment instructions", len(mail.outbox) == 3, len(mail.outbox))
instructions_mail = next(m for m in mail.outbox if "Payment Instructions" in m.subject)
ok("instructions go to the customer", "karim@example.com" in to_all(instructions_mail))
instructions_html = dict((ct, body) for body, ct in instructions_mail.alternatives)["text/html"]
ok("the configured RIP appears in the email", "00799999001234567890" in instructions_html)
ok("the order reference appears as the transfer reference", bm_order.reference in instructions_html)

reset()
tiny_png = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02\x00\x00\x00\x0bIDATx\x9cc\x64"
    b"\xf8\x0f\x00\x01\x05\x01\x00\x9c\x63\x8e\x66\x00\x00\x00\x00IEND\xaeB`\x82"
)
proof = PaymentProof.objects.create(
    order=bm_order,
    file=SimpleUploadedFile("receipt.png", tiny_png, content_type="image/png"),
    amount_declared=bm_order.total,
    transaction_reference="BM-VERIFY-1",
)
ok("uploading emails customer + admin (with attachment)", len(mail.outbox) == 2, len(mail.outbox))
proof_recipients = [to_all(m)[0] for m in mail.outbox]
ok("customer acknowledged", "karim@example.com" in proof_recipients)
ok("admin alerted", admin_address in proof_recipients)
admin_proof_mail = next(m for m in mail.outbox if admin_address in to_all(m))
ok("admin alert carries the receipt as an attachment", len(admin_proof_mail.attachments) == 1,
   [a[0] for a in admin_proof_mail.attachments])
ok("attached filename matches what the customer sent", admin_proof_mail.attachments[0][0] == "receipt.png")
bm_order.refresh_from_db()
ok("order moved to UNDER_REVIEW", bm_order.payment_state == PaymentState.UNDER_REVIEW)

reset()
proof.status = PaymentProofStatus.REJECTED
proof.review_note = "Amount doesn't match our records — please resend."
proof.save()
ok("rejection emails only the customer", len(mail.outbox) == 1, len(mail.outbox))
# The plain-text alternative is derived from the HTML via strip_tags, which
# doesn't unescape entities -- Django auto-escapes the apostrophe in
# "doesn't" to &#x27; there, so check the actual HTML the customer's mail
# client renders, not the plain-text fallback.
rejection_html = dict((ct, body) for body, ct in mail.outbox[0].alternatives)["text/html"]
ok("rejection reason is included verbatim", "doesn&#x27;t match our records" in rejection_html
   or "doesn't match our records" in rejection_html)
bm_order.refresh_from_db()
ok("order state follows the rejection", bm_order.payment_state == PaymentState.REJECTED)
ok("re-upload is allowed again after rejection", bm_order.can_upload_payment_proof)

reset()
proof2 = PaymentProof.objects.create(
    order=bm_order,
    file=SimpleUploadedFile("receipt2.png", tiny_png, content_type="image/png"),
    amount_declared=bm_order.total,
)
reset()  # the upload above sent its own pair; only the confirmation below matters here
proof2.status = PaymentProofStatus.CONFIRMED
proof2.save()
ok("confirmation emails only the customer", len(mail.outbox) == 1, len(mail.outbox))
ok("confirmation subject names the order", bm_order.reference in mail.outbox[0].subject)
bm_order.refresh_from_db()
ok("order state follows the confirmation", bm_order.payment_state == PaymentState.CONFIRMED)
ok("a confirmed order cannot upload again", not bm_order.can_upload_payment_proof)

reset()
proof2.save()  # no status change
ok("re-saving a proof with no status change sends nothing", len(mail.outbox) == 0, len(mail.outbox))

bm_order.delete()
company.sales_rip = ""
company.sales_ccp_number = ""
company.sales_payment_email = ""
company.save()

print("\n=== FAILURE ISOLATION ===")
reset()
settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
settings.EMAIL_HOST = "127.0.0.1"
settings.EMAIL_PORT = 1  # nothing listens here
settings.EMAIL_USE_SSL = False
settings.EMAIL_TIMEOUT = 2
crashed = False
try:
    # A dead mail server must never take checkout down with it -- core.emails
    # swallows transport errors by design. This asserts that contract holds.
    ContactMessage.objects.create(
        name="Transport Down", email="down@example.com",
        subject="Unreachable SMTP", message="This should not raise.",
    ).delete()
except Exception as exc:  # noqa: BLE001 -- the point is that nothing escapes
    crashed = True
    print("     raised:", type(exc).__name__, exc)
ok("an unreachable SMTP server does not break the request", not crashed)

print("\nAll email checks passed.")
