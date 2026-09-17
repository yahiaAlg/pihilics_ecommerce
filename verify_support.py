import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from django.test import Client
from content.models import FAQEntry, FAQCategory
from support.models import ContactMessage, ContactDepartment
from core.models import CompanyInfo

def ok(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(extra)) if extra else ""))
    assert cond, label

c = Client()
company = CompanyInfo.get_solo()

print("\n=== HELP CENTER (content:support) ===")
r = c.get("/support/")
html = r.content.decode()
ok("renders", r.status_code == 200)
ok("category cards from real counts", all(
    f"{FAQEntry.objects.filter(is_active=True, category=cat).count()} article" in html
    for cat in FAQCategory.values))
ok("explicit icon mapping applied", "bx-package" in html and "bx-battery-charging" in html
   and "bx-shield-alt" in html and "bx-calendar-check" in html)
ok("category anchors present", 'id="cat-orders_delivery"' in html)
ok("category cards link to anchors", 'href="#cat-' in html)
sample = FAQEntry.objects.filter(is_active=True).first()
ok("real FAQ content rendered server-side", sample.question in html)
ok("csrf present on embedded contact form", "csrfmiddlewaretoken" in html)
ok("embedded form gained a Name field (model requires it)", 'name="name"' in html)
ok("embedded form defaults department to support", 'name="department" value="support"' in html)
ok("no ARKO_DATA / mock JS left", "ARKO_DATA" not in html and "renderFAQ(" not in html)

print("\n=== HELP CENTER: server-side ?q= filter (GET, matches AJAX) ===")
r = c.get(f"/support/?q={sample.question.split()[0]}")
ok("query param filters entries", sample.question in r.content.decode())
r = c.get("/support/?q=zzz_no_such_faq_zzz")
ok("no-match shows empty state", "No results found" in r.content.decode())

print("\n=== HELP CENTER: FAQ search-as-you-type AJAX endpoint ===")
r = c.get(f"/support/faq-search/?q={sample.question.split()[0]}")
ok("json 200", r.status_code == 200)
data = r.json()
ok("matches the same entry the server-rendered filter found",
   any(sample.question == item["question"] for cat in data["categories"] for item in cat["items"]))
r = c.get("/support/faq-search/?q=")
ok("empty query returns all active categories", len(r.json()["categories"]) == len(
    [v for v in FAQCategory.values if FAQEntry.objects.filter(is_active=True, category=v).exists()]))

print("\n=== HELP CENTER: embedded contact form -> PRG ===")
before = ContactMessage.objects.count()
r = c.post("/support/", {"name": "Amina K.", "email": "amina@example.com",
                          "subject": "Battery question", "message": "How long does a swap take?",
                          "department": "support"})
ok("redirects (PRG)", r.status_code == 302, r.get("Location"))
msg = ContactMessage.objects.order_by("-id").first()
ok("message persisted (not the old toast-only no-op)", ContactMessage.objects.count() == before + 1)
ok("department defaulted correctly", msg.department == ContactDepartment.SUPPORT, msg.department)
ok("name captured", msg.name == "Amina K.")

r = c.post("/support/", {"email": "bad@example.com", "subject": "x", "message": "y", "department": "support"})
ok("missing required name re-renders 200 with error, no redirect", r.status_code == 200)
ok("no message created on invalid submission", ContactMessage.objects.count() == before + 1)

print("\n=== DEDICATED CONTACT PAGE (support:contact) ===")
r = c.get("/contact/")
html = r.content.decode()
ok("renders", r.status_code == 200)
ok("page-local .contact-layout/.dept-tab styles carried over",
   ".contact-layout" in html and ".dept-tab.active" in html)
ok("csrf present", "csrfmiddlewaretoken" in html)
ok("real department choices rendered (Sales/Support/Press/Partnerships)",
   all(label in html for label in ["Sales", "Support", "Press", "Partnerships"]))
ok("mockup's non-existent General tab NOT rendered as a real dept option",
   'data-dept="general"' not in html)
ok("defaults to Support tab active (model default), not General",
   '<div class="dept-tab active" data-dept="support">' in html)
ok("single Full Name field, not split First/Last", 'name="name"' in html
   and 'placeholder="John"' not in html)
ok("company legal name from CompanyInfo", company.legal_name in html)
ok("company VAT number from CompanyInfo", company.vat_number in html)
ok("stale hardcoded VAT ID gone", "DE346782901" not in html or company.vat_number == "DE346782901")
ok("department mailboxes kept literal", "sales@pihilics.dz" in html and "press@pihilics.dz" in html)

print("\n=== DEDICATED CONTACT PAGE: valid POST -> PRG ===")
before = ContactMessage.objects.count()
r = c.post("/contact/", {"name": "Klaus R.", "email": "klaus@example.com",
                          "subject": "Press inquiry", "message": "Requesting a press kit.",
                          "department": "press"})
ok("redirects (PRG)", r.status_code == 302, r.get("Location"))
msg = ContactMessage.objects.order_by("-id").first()
ok("message persisted with chosen department", msg.department == ContactDepartment.PRESS, msg.department)
ok("name captured as single field", msg.name == "Klaus R.")

print("\n=== SHARED HANDLER: identical persistence from both entry points ===")
ok("both pages write the same ContactMessage model", ContactMessage.objects.count() == before + 1)

print("\nALL SUPPORT-APP CHECKS PASSED")
