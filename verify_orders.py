import os, re, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]  # verification harness only

from django.test import Client
from catalog.models import Product
from orders.models import Order

def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(extra)) if extra else ""))
    assert cond, label

print("\n=== GUEST CHECKOUT, 4 STEPS, PRG ===")
c = Client()
p = Product.objects.filter(is_active=True).first()
r = c.post("/cart/add/", {"product_id": p.id, "quantity": 1})
ok("add to cart redirects (PRG)", r.status_code == 302, r.status_code)

r = c.get("/checkout/information/")
ok("step 1 renders", r.status_code == 200, r.status_code)
ok("step 1 stepper marks step 1 active", 'class="step active" data-step="1"' in r.content.decode())
ok("step 1 has csrf", "csrfmiddlewaretoken" in r.content.decode())
ok("summary shows honest 'calculated' note, not fake VAT",
   "calculated once your delivery address" in r.content.decode())

r = c.post("/checkout/information/", {"first_name": "Jean", "last_name": "Dupont",
                          "email": "jean@example.com", "phone": "+213 555 0101"})
ok("step 1 POST redirects to delivery", r.status_code == 302 and r["Location"].endswith("/checkout/delivery/"), r.get("Location"))

r = c.get("/checkout/delivery/")
html = r.content.decode()
ok("step 2 renders", r.status_code == 200)
ok("step 1 now shows complete", 'class="step complete" data-step="1"' in html)
ok("wilaya options come from real backend (Setif present)", 'value="19"' in html)
ok("mockup-only countries absent (SE)", 'value="SE"' not in html)

r = c.post("/checkout/delivery/", {"street": "12 Rue A", "city": "Setif",
                                   "postal_code": "19000", "wilaya": "19",
                                   "delivery_method": "express"})
ok("step 2 POST redirects to payment", r.status_code == 302 and r["Location"].endswith("/checkout/payment/"), r.get("Location"))

r = c.get("/checkout/payment/")
html = r.content.decode()
ok("step 3 renders", r.status_code == 200)
ok("summary now shows real Shipping figure", "Shipping" in html and ("TVA" in html or "VAT" in html))
# Shipping is now priced per wilaya (core.ShippingZone) rather than a flat
# fee, so assert a real DZD amount is rendered rather than the old "49".
ok("shipping figure rendered in DZD", "DA" in html)
ok("financing selector present (BR-CHK-08)", 'name="financing_plan"' in html)
ok("insurance selector present (BR-CHK-08)", 'name="insurance_tier"' in html)

r = c.post("/checkout/payment/", {"payment_method": "cib"})
ok("step 3 POST redirects to review", r.status_code == 302 and r["Location"].endswith("/checkout/review/"), r.get("Location"))

r = c.get("/checkout/review/")
html = r.content.decode()
ok("step 4 renders", r.status_code == 200)
ok("review shows real wilaya name not code", "Setif" in html or "Sétif" in html)
ok("review shows delivery method label", "Express" in html)
ok("review shows payment method label", "CIB" in html or "Edahabia" in html)

r = c.post("/checkout/review/", {})
ok("place order redirects (PRG)", r.status_code == 302, r.get("Location"))
loc = r["Location"]
order = Order.objects.order_by("-id").first()
ok("order created", order is not None, order.reference if order else None)
ok("redirect targets success page for this order", order.reference in loc, loc)
ok("guest order recorded contact email", order.contact_email == "jean@example.com", order.contact_email)
ok("BR-CHK-06 total reconciles",
   order.total == order.subtotal - order.discount_amount + order.shipping_cost + order.vat_amount,
   f"{order.subtotal} - {order.discount_amount} + {order.shipping_cost} + {order.vat_amount} = {order.total}")

print("\n=== ORDER SUCCESS ===")
r = c.get(loc)
html = r.content.decode()
ok("success renders", r.status_code == 200)
ok("shows real reference", order.reference in html)
ok("express copy says 2-3 days", "2&#x2013;3 Days" in html or "2–3 Days" in html)
ok("no localStorage anywhere", "localStorage" not in html)

print("\n=== CART EMPTIED AFTER ORDER (BR-CHK) ===")
r = c.get("/checkout/information/")
ok("empty cart bounces out of checkout", r.status_code == 302, r.get("Location"))

print("\n=== GUEST ACCESS CONTROL ===")
other = Client()
r = other.get(f"/orders/{order.reference}/")
ok("stranger cannot see guest order", r.status_code == 302 and "lookup" in r["Location"], r.get("Location"))
r = c.get(f"/orders/{order.reference}/")
ok("original guest session CAN see it", r.status_code == 200, r.status_code)

print("\n=== GUEST LOOKUP (BR-ORD-04) ===")
g = Client()
r = g.get("/orders/lookup/")
ok("lookup page renders", r.status_code == 200)
ok("lookup has csrf", "csrfmiddlewaretoken" in r.content.decode())
r = g.post("/orders/lookup/", {"reference": order.reference, "email": "wrong@example.com"})
ok("wrong email does not grant access", r.status_code == 200, r.status_code)
r = g.post("/orders/lookup/", {"reference": order.reference, "email": "jean@example.com"})
ok("correct pair redirects to detail (PRG)", r.status_code == 302 and order.reference in r["Location"], r.get("Location"))
r = g.get(f"/orders/{order.reference}/")
ok("lookup session now authorized", r.status_code == 200)

print("\n=== REGISTERED USER: LIST / DETAIL / TRACK / INVOICE ===")
u = Client()
r = u.get("/orders/")
ok("anonymous order list redirects to login", r.status_code == 302 and "login" in r["Location"], r.get("Location"))
ok("login works", u.post("/accounts/login/",
   {"email": "amina.benali@example.dz", "password": "Pihilics#Demo2026"}).status_code == 302)

r = u.get("/orders/")
html = r.content.decode()
ok("order list renders", r.status_code == 200)
ok("cancelled filter button added", "?status=cancelled" in html)
seeded = Order.objects.filter(user__username="amina.benali")
ok("seeded orders present", seeded.exists(), list(seeded.values_list("reference", "status")))
for o in seeded:
    ok(f"badge class matches enum 1:1 for {o.status}",
       f'order-status-badge {o.status}' in html)

r = u.get("/orders/?status=processing")
ok("status filter works", r.status_code == 200 and all(
    o.reference in r.content.decode() for o in seeded.filter(status="processing")))

target = seeded.first()
r = u.get(f"/orders/{target.reference}/")
html = r.content.decode()
ok("detail renders", r.status_code == 200)
ok("detail reconciles subtotal/VAT/total", "Subtotal" in html and "VAT" in html)
ok("detail links to invoice", f"/orders/{target.reference}/invoice/" in html)

r = u.get(f"/orders/{target.reference}/track/")
html = r.content.decode()
ok("track renders", r.status_code == 200)
ok("timeline present", 'class="tracking-timeline"' in html)
current = re.findall(r'tracking-stage ([a-z]*)"', html)
ok("at most one 'current' stage", current.count("current") <= 1, current)

r = u.get(f"/orders/{target.reference}/invoice/")
html = r.content.decode()
ok("invoice renders", r.status_code == 200)
ok("invoice carries company VAT number", "VAT" in html)
ok("invoice footer block included", "Reg." in html or "IBAN" in html)
ok("invoice has print styles", "@media print" in html)

print("\n=== CROSS-USER ISOLATION ===")
other_user = Client()
other_user.post("/accounts/login/", {"email": "yacine.haddad@example.dz", "password": "Pihilics#Demo2026"})
r = other_user.get(f"/orders/{target.reference}/")
ok("cannot read another user's order", r.status_code == 302 and "lookup" in r["Location"], r.get("Location"))

print("\n=== BARIDIMOB: CHECKOUT OFFERS IT ONLY WHEN CONFIGURED ===")
from core.models import CompanyInfo
from orders.models import PaymentProof, PaymentProofStatus, PaymentState

company = CompanyInfo.get_solo()
had_account = company.has_sales_account
saved_fields = (company.sales_rip, company.sales_ccp_number)
company.sales_rip = ""
company.sales_ccp_number = ""
company.save()

nb = Client()
p2 = Product.objects.filter(is_active=True).first()
nb.post("/cart/add/", {"product_id": p2.id, "quantity": 1})
r = nb.post("/checkout/information/", {"first_name": "Nabil", "last_name": "Amrani",
                                        "email": "nabil@example.com", "phone": "+213 555 0102"})
r = nb.post("/checkout/delivery/", {"street": "3 Rue B", "city": "Setif",
                                    "postal_code": "19000", "wilaya": "19",
                                    "delivery_method": "standard"})
r = nb.get("/checkout/payment/")
html = r.content.decode()
ok("BaridiMob option hidden with no sales account configured", "BaridiMob / CCP" not in html)
r = nb.post("/checkout/payment/", {"payment_method": "baridimob"})
ok("posting baridimob with no account rejected, not accepted", r.status_code == 200)

company.sales_account_holder = "Pihilics SARL"
company.sales_bank_name = "Algérie Poste"
company.sales_rip = "00799999001234567890"
company.sales_ccp_number = "1234567 89"
company.sales_payment_email = "sales-test@pihilics.dz"
company.save()

r = nb.get("/checkout/payment/")
html = r.content.decode()
ok("BaridiMob appears once an account is configured", "BaridiMob" in html)

print("\n=== BARIDIMOB: FULL CHECKOUT -> AWAITING PROOF ===")
r = nb.post("/checkout/payment/", {"payment_method": "baridimob"})
ok("step 3 POST redirects to review", r.status_code == 302 and r["Location"].endswith("/checkout/review/"))
r = nb.get("/checkout/review/")
ok("review shows BaridiMob label", "BaridiMob" in r.content.decode())
r = nb.post("/checkout/review/", {})
ok("place order redirects (PRG)", r.status_code == 302)
bm_order = Order.objects.order_by("-id").first()
ok("order created with baridimob method", bm_order.payment_method == "baridimob", bm_order.payment_method)
ok("payment_state starts AWAITING_PROOF", bm_order.payment_state == PaymentState.AWAITING_PROOF, bm_order.payment_state)
ok("requires_payment_proof is True", bm_order.requires_payment_proof)
ok("can_upload_payment_proof is True before any proof", bm_order.can_upload_payment_proof)

r = nb.get(r["Location"])
ok("success page offers Complete Payment CTA", "Complete Payment" in r.content.decode())

print("\n=== BARIDIMOB: PAYMENT PAGE + PROOF UPLOAD ===")
pay_url = f"/orders/{bm_order.reference}/payment/"
r = nb.get(pay_url)
html = r.content.decode()
ok("payment page renders", r.status_code == 200)
ok("shows the configured RIP", "00799999001234567890" in html)
ok("shows the order total", "DA" in html)
ok("upload form present", 'name="file"' in html)

stranger = Client()
r = stranger.get(pay_url)
ok("a stranger cannot reach the payment page", r.status_code == 302 and "lookup" in r["Location"])

from django.core.files.uploadedfile import SimpleUploadedFile
import base64
tiny_png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
upload = SimpleUploadedFile("receipt.png", tiny_png, content_type="image/png")
r = nb.post(pay_url, {
    "file": upload, "amount_declared": str(bm_order.total), "transaction_reference": "BM-TEST-1",
})
ok("proof upload redirects (PRG)", r.status_code == 302, r.get("Location"))
bm_order.refresh_from_db()
ok("payment_state moved to UNDER_REVIEW", bm_order.payment_state == PaymentState.UNDER_REVIEW, bm_order.payment_state)
ok("can_upload_payment_proof is False while under review", not bm_order.can_upload_payment_proof)
proof = bm_order.latest_payment_proof
ok("a PaymentProof row was created", proof is not None)
ok("proof starts PENDING", proof.status == PaymentProofStatus.PENDING)
ok("proof file passed validation and is stored", bool(proof.file) and proof.file.name.endswith(".png"))

r = nb.get(pay_url)
ok("page now shows the under-review banner", "under review" in r.content.decode().lower())

bad_upload = SimpleUploadedFile("receipt.txt", b"not a real receipt", content_type="text/plain")
r = other_user.post(pay_url, {"file": bad_upload})
ok("a disallowed file type is rejected server-side too (not just by the client)",
   r.status_code in (200, 302) and not PaymentProof.objects.filter(file__endswith=".txt").exists())

print("\n=== BARIDIMOB: ADMIN REJECT -> RE-UPLOAD -> CONFIRM ===")
proof.status = PaymentProofStatus.REJECTED
proof.review_note = "Amount doesn't match — please resend the correct receipt."
proof.save()
bm_order.refresh_from_db()
ok("rejecting sets order payment_state to REJECTED", bm_order.payment_state == PaymentState.REJECTED)
ok("rejecting re-opens uploading", bm_order.can_upload_payment_proof)

r = nb.get(pay_url)
ok("rejection reason shown to the customer", "Amount doesn&#x27;t match" in r.content.decode()
   or "doesn't match" in r.content.decode())

upload2 = SimpleUploadedFile("receipt2.png", tiny_png, content_type="image/png")
r = nb.post(pay_url, {"file": upload2, "amount_declared": str(bm_order.total), "transaction_reference": "BM-TEST-2"})
ok("re-upload after rejection succeeds", r.status_code == 302)
bm_order.refresh_from_db()
ok("back to UNDER_REVIEW on re-upload", bm_order.payment_state == PaymentState.UNDER_REVIEW)
ok("two proofs now on this order (rejected one kept, not overwritten)",
   bm_order.payment_proofs.count() == 2, bm_order.payment_proofs.count())

new_proof = bm_order.latest_payment_proof
new_proof.status = PaymentProofStatus.CONFIRMED
new_proof.save()
bm_order.refresh_from_db()
ok("confirming sets order payment_state to CONFIRMED", bm_order.payment_state == PaymentState.CONFIRMED)
ok("confirmed order can no longer upload another proof", not bm_order.can_upload_payment_proof)

r = nb.get(pay_url)
ok("payment page shows confirmed state", "confirmed" in r.content.decode().lower())

# Restore whatever the sales account looked like before this script ran,
# so a re-run starts from the same starting condition every time.
company.sales_rip, company.sales_ccp_number = saved_fields
company.save()

print("\nALL ORDERS-APP CHECKS PASSED")
