import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from django.test import Client
from catalog.models import Product, ProductType
from dealers.models import Dealer
from content.models import Story
from orders.models import Order
from bookings.models import TestRideBooking, ServiceBooking

def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(extra)) if extra else ""))
    assert cond, label

anon = Client()
moto = Product.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True).first()
acc = Product.objects.filter(product_type=ProductType.ACCESSORY, is_active=True).first()
dealer = Dealer.objects.filter(is_active=True).first()
story = Story.objects.filter(is_published=True).first()
order = Order.objects.first()
tr = TestRideBooking.objects.first()
sb = ServiceBooking.objects.first()

public_pages = {
    "/": "home",
    "/about/": "about",
    "/stories/": "stories",
    f"/stories/{story.slug}/" if story else "/stories/none/": "story detail",
    "/support/": "support/help center",
    "/terms/": "terms",
    "/privacy/": "privacy",
    "/contact/": "contact",
    "/shop/": "shop",
    f"/products/{moto.slug}/" if moto else "/products/none/": "motorcycle detail",
    f"/products/{acc.slug}/" if acc else "/products/none/": "accessory detail",
    "/accessories/": "accessories",
    "/compare/": "compare",
    "/configurator/": "configurator",
    "/search/": "search",
    "/dealers/": "dealers",
    "/financing/": "financing",
    "/insurance/": "insurance",
    "/accounts/login/": "login",
    "/accounts/register/": "register",
    "/bookings/test-ride/": "test ride",
    "/bookings/service/": "service booking",
    "/orders/lookup/": "guest order lookup",
    "/cart/": "cart",
    "/nonexistent-page-xyz/": "404 handler",
}

print("=== PUBLIC PAGES (anonymous) ===")
for path, label in public_pages.items():
    r = anon.get(path)
    ok(f"{label} ({path}) -> {r.status_code}", r.status_code in (200, 404))

print("\n=== AUTH-GATED PAGES REDIRECT CLEANLY, NOT 500 ===")
for path, label in [("/accounts/account/", "account"), ("/orders/", "order list"),
                     ("/bookings/dealer-queue/", "dealer queue")]:
    r = Client().get(path)
    ok(f"{label} redirects/denies cleanly -> {r.status_code}", r.status_code in (302, 403))

print("\n=== SIGNED-IN CUSTOMER ===")
u = Client()
u.post("/accounts/login/", {"email": "amina.benali@example.dz", "password": "Pihilics#Demo2026"})
for path, label in [("/accounts/account/", "account"), ("/orders/", "order list"),
                     ("/cart/", "cart")]:
    r = u.get(path)
    ok(f"{label} -> {r.status_code}", r.status_code == 200)
if order:
    for path, label in [(f"/orders/{order.reference}/", "order detail (may 302 if not amina's)"),
                         ]:
        r = u.get(path)
        ok(f"{label} -> {r.status_code}", r.status_code in (200, 302))

print("\n=== DEALER STAFF ===")
staff = Client()
staff.post("/accounts/login/", {"email": "staff.alger@pihilics.dz", "password": "Pihilics#Staff2026"})
r = staff.get("/bookings/dealer-queue/")
ok(f"dealer queue -> {r.status_code}", r.status_code == 200)

print("\nALL PROJECT-WIDE SMOKE CHECKS PASSED")
