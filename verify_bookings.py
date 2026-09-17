import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from datetime import timedelta
from django.test import Client
from django.utils import timezone
from catalog.models import Product, ProductType
from dealers.models import Dealer
from bookings.models import ServiceTier, TestRideBooking, ServiceBooking, BookingStatus

def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(extra)) if extra else ""))
    assert cond, label

bike = Product.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True).first()
dealer = Dealer.objects.filter(is_active=True).first()
tier = ServiceTier.objects.filter(is_active=True).first()
tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
# A date far enough out that seed_full's own confirmed demo bookings can't
# collide with it -- the seed books tomorrow-morning at one dealer, so using
# `tomorrow` here made a *correct* BR-BK-02 rejection look like a failure.
#
# It also has to be a date *this script* hasn't already claimed on an earlier
# run. These checks post through the real test client against the live
# database, so the valid-POST section below leaves a permanent morning
# booking behind; a fixed offset therefore passed once and then reported a
# correct BR-BK-02 conflict as "redirects (PRG)" failing on every run after.
# Walking forward to the first free morning makes the suite re-runnable
# without restoring the database in between.
def _first_free_date(start_offset=45, limit=400):
    day = timezone.localdate() + timedelta(days=start_offset)
    for _ in range(limit):
        taken = TestRideBooking.objects.filter(
            dealer=dealer, date=day
        ).exclude(status=BookingStatus.CANCELLED).exists()
        if not taken:
            return day.isoformat()
        day += timedelta(days=1)
    raise RuntimeError("no free test-ride date found -- database needs a reseed")


free_date = _first_free_date()
yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()

print("\n=== TEST RIDE: GET ===")
c = Client()
r = c.get("/bookings/test-ride/")
html = r.content.decode()
ok("renders", r.status_code == 200)
ok("real motorcycles in optgroup", bike.name in html)
ok("optgroup DOM preserved", '<optgroup label="Motorcycles">' in html)
ok("real dealers listed", dealer.name in html)
ok("csrf present", "csrfmiddlewaretoken" in html)
ok("real 2-slot choices, not mockup's 7 hourly", "Morning (9:00 - 13:00)" in html and "9:00 AM" not in html)
ok("reference info cards preserved", "30-second battery swap" in html and "testride@pihilics.dz" in html)
ok("no localStorage", "localStorage" not in html)

print("\n=== TEST RIDE: VALIDATION (no PRG on invalid) ===")
before = TestRideBooking.objects.count()
r = c.post("/bookings/test-ride/", {
    "product": bike.pk, "dealer": dealer.pk, "date": yesterday, "time_slot": "morning",
    "first_name": "A", "last_name": "B", "email": "a@b.com", "phone": "+1",
    "license_number": "L1", "waiver_acknowledged": "on"})
ok("past date re-renders with error, no redirect", r.status_code == 200)
ok("error text surfaced", "at least tomorrow" in r.content.decode())
ok("nothing created", TestRideBooking.objects.count() == before)

r = c.post("/bookings/test-ride/", {
    "product": bike.pk, "dealer": dealer.pk, "date": tomorrow, "time_slot": "morning",
    "first_name": "A", "last_name": "B", "email": "a@b.com", "phone": "+1",
    "license_number": "L1"})  # waiver omitted
ok("missing waiver rejected", r.status_code == 200 and TestRideBooking.objects.count() == before)

print("\n=== TEST RIDE: VALID POST -> PRG ===")
r = c.post("/bookings/test-ride/", {
    "product": bike.pk, "dealer": dealer.pk, "date": free_date, "time_slot": "morning",
    "first_name": "Amina", "last_name": "Haddad", "email": "amina@example.com",
    "phone": "+213 555 0199", "license_number": "DZ-99812", "waiver_acknowledged": "on"})
ok("redirects (PRG)", r.status_code == 302, r.get("Location"))
tr = TestRideBooking.objects.order_by("-id").first()
ok("booking created", tr.email == "amina@example.com")
ok("BR-BK-03: starts as requested", tr.status == BookingStatus.REQUESTED, tr.status)
ok("redirect targets its confirmation", r["Location"].endswith(f"/bookings/test-ride/{tr.pk}/confirmation/"))

r = c.get(r["Location"])
html = r.content.decode()
ok("confirmation renders", r.status_code == 200)
ok("shows real bike/dealer/slot", bike.name in html and dealer.name in html and "Morning" in html)
ok("badge uses mapped class not raw enum",
   'order-status-badge processing' in html and 'order-status-badge requested' not in html)
ok("success icon preserved", 'class="success-icon"' in html)

print("\n=== SECURITY: confirmation access control (fix verified) ===")
stranger = Client()
r = stranger.get(f"/bookings/test-ride/{tr.pk}/confirmation/")
ok("stranger gets 403, not the licence number", r.status_code == 403, r.status_code)
ok("creator still allowed", c.get(f"/bookings/test-ride/{tr.pk}/confirmation/").status_code == 200)

print("\n=== BR-BK-02 slot conflict ===")
tr.status = BookingStatus.CONFIRMED
tr.save(update_fields=["status"])
c2 = Client()
r = c2.post("/bookings/test-ride/", {
    "product": bike.pk, "dealer": dealer.pk, "date": free_date, "time_slot": "morning",
    "first_name": "X", "last_name": "Y", "email": "x@y.com", "phone": "+1",
    "license_number": "L9", "waiver_acknowledged": "on"})
ok("conflicting slot rejected in-form (no 500)", r.status_code == 200)
ok("conflict message shown", "already has a booking" in r.content.decode())

print("\n=== SERVICE: GET ===")
s = Client()
r = s.get("/bookings/service/")
html = r.content.decode()
ok("renders", r.status_code == 200)
ok("page-local .svc-* style block carried over", ".svc-type.active" in html and ".svc-layout" in html)
ok("tier cards from real DB rows", tier.get_name_display() in html and "DA" in html)
ok("explicit icon mapping applied", "bx-wrench" in html and "bx-battery-charging" in html and "bx-buildings" in html)
ok("hidden tier input present", 'id="svcTierInput"' in html)
ok("garage selector hidden for guests", 'name="garage_entry"' not in html)
ok("csrf present", "csrfmiddlewaretoken" in html)

print("\n=== SERVICE: VALID POST -> PRG ===")
r = s.post("/bookings/service/", {
    "service_tier": tier.pk, "product": bike.pk, "dealer": dealer.pk,
    "date": free_date, "time_slot": "afternoon",
    "contact_first_name": "Karim", "contact_last_name": "Benali",
    "contact_email": "karim@example.com", "contact_phone": "+213 555 0177"})
ok("redirects (PRG)", r.status_code == 302, r.get("Location"))
sb = ServiceBooking.objects.order_by("-id").first()
ok("booking created with tier", sb.service_tier_id == tier.pk)
ok("starts as requested", sb.status == BookingStatus.REQUESTED)
r = s.get(r["Location"])
html = r.content.decode()
ok("confirmation renders with price", r.status_code == 200 and "DA" in html)
ok("stranger blocked", Client().get(f"/bookings/service/{sb.pk}/confirmation/").status_code == 403)

print("\n=== GARAGE PRE-SELECT (spec 6.13 entry point) ===")
u = Client()
u.post("/accounts/login/", {"email": "amina.benali@example.dz", "password": "Pihilics#Demo2026"})
r = u.get("/bookings/service/")
html = r.content.decode()
from django.contrib.auth import get_user_model
amina = get_user_model().objects.get(username="amina.benali")
entries = amina.garage_entries.all()
if entries.exists():
    ok("garage selector shown to owner", 'name="garage_entry"' in html)
    e = entries.first()
    r = u.get(f"/bookings/service/?garage_entry={e.pk}")
    ok("garage_entry pre-selects its bike", f'value="{e.product.pk}" selected' in r.content.decode())
else:
    print("  SKIP  amina has no garage entries in seed")
ok("contact prefilled for signed-in user", "amina.benali@example.dz" in html)

print("\n=== DEALER QUEUE (BR-BK-03/04) ===")
r = Client().get("/bookings/dealer-queue/")
ok("anonymous redirected to login", r.status_code == 302 and "login" in r["Location"])
r = u.get("/bookings/dealer-queue/")
ok("plain customer forbidden", r.status_code == 403, r.status_code)

staff = Client()
staff.post("/accounts/login/", {"email": "staff.alger@pihilics.dz", "password": "Pihilics#Staff2026"})
r = staff.get("/bookings/dealer-queue/")
ok("dealer staff allowed", r.status_code == 200, r.status_code)
html = r.content.decode()
ok("queue uses mapped badge classes", "order-status-badge" in html)
ok("every action form has csrf", html.count("csrfmiddlewaretoken") >= 1)

from accounts.models import UserProfile
staff_dealer = UserProfile.objects.get(user__username="staff.alger").dealer
own = TestRideBooking.objects.filter(dealer=staff_dealer, status=BookingStatus.REQUESTED).first()
if own:
    r = staff.post(f"/bookings/dealer-queue/test_ride/{own.pk}/status/", {"status": "confirmed"})
    own.refresh_from_db()
    ok("confirm transitions + redirects (PRG)", r.status_code == 302 and own.status == BookingStatus.CONFIRMED)
foreign = TestRideBooking.objects.exclude(dealer=staff_dealer).first()
if foreign:
    r = staff.post(f"/bookings/dealer-queue/test_ride/{foreign.pk}/status/", {"status": "cancelled"})
    foreign.refresh_from_db()
    ok("BR-BK-04: cannot touch another dealer's booking",
       r.status_code == 404 and foreign.status != BookingStatus.CANCELLED, r.status_code)
else:
    print("  SKIP  no foreign-dealer booking to test against")

print("\nALL BOOKINGS-APP CHECKS PASSED")
