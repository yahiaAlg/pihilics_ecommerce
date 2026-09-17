"""
content.views

Spec's site-wide Brand & Content pages: Home, About, Stories, the
Support/Help Center (FAQ), and the two static legal pages.
"""

from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from catalog.models import Category, Product, ProductType, Review
from core.models import CompanyInfo
from dealers.models import Dealer
from support.forms import ContactForm
from support.views import handle_contact_submission

from .forms import FAQSearchForm
from .models import (
    AboutPageContent,
    FAQCategory,
    FAQEntry,
    HomeCarouselSlide,
    HomePageContent,
    HomeShowcasePanel,
    LegalDocument,
    NotFoundPageContent,
    Story,
    SupportPageContent,
)
from .utils import merge_company_fields, safe_format

# Explicit mapping (rule 3: never derive a presentation token from a model
# enum by string transform) -- mirrors the reference's `catIcons` object,
# which keyed off the *display label* ("Orders & Delivery"), a fragile match
# that breaks the moment a label's copy changes. Keyed off the enum value
# instead, exactly like bookings_extras.SERVICE_TIER_ICONS.
FAQ_CATEGORY_ICONS = {
    FAQCategory.ORDERS_DELIVERY: "bx-package",
    FAQCategory.BATTERY_CHARGING: "bx-battery-charging",
    FAQCategory.WARRANTY_SERVICE: "bx-shield-alt",
    FAQCategory.TEST_RIDES_PURCHASING: "bx-calendar-check",
}


def home_view(request):
    """Spec Home: featured motorcycles/accessories and the brand story."""
    motorcycles = Product.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True)
    dealer_count = Dealer.objects.filter(is_active=True).count()
    home_content = HomePageContent.get_solo()
    flagship = motorcycles.order_by("-price").first()

    # "Every Angle" detail carousel (landing-page-v1 carousel-section): real
    # admin rows when the admin has uploaded any, otherwise fall back to the
    # flagship's own gallery so a fresh install isn't an empty carousel.
    carousel_slides = list(home_content.carousel_slides.all())
    if not carousel_slides and flagship:
        carousel_slides = [
            {"image": img.image, "caption": flagship.name}
            for img in flagship.images.all()[:6]
        ]

    return render(request, "content/home.html", {
        "home": home_content,
        "testride_body": safe_format(home_content.testride_body, dealer_count=dealer_count),
        # The reference's featuredGrid took `ARKO_DATA.motorcycles.slice(0, 4)`
        # and the .product-grid it fills is a 4-up row, so this is 4, not 3 —
        # a 3-item slice left a visibly short final row.
        "featured_motorcycles": motorcycles.order_by("-rating_cached")[:4],
        "featured_accessories": Product.objects.filter(
            product_type=ProductType.ACCESSORY, is_active=True
        ).order_by("-rating_cached")[:4],
        # The static build hardcoded four .category-card tiles (Enduro/Trail/
        # Adventure/Performance) linking to ?category=<Name>. Category is an
        # admin-editable model precisely so the business can add one without a
        # deploy (BR-CAT-*), so the tiles are driven by it and link by slug.
        "motorcycle_categories": Category.objects.filter(
            product_type=ProductType.MOTORCYCLE, is_active=True
        )[:4],
        # "Flagship" has no model flag; the reference simply hardcoded the RVX.
        # Resolved as the highest-priced active motorcycle, which is the
        # closest real proxy and keeps the section correct if the lineup changes.
        "flagship": flagship,
        # The reference's three testimonials were a hardcoded JS array. Real
        # approved 5-star reviews replace them (spec 15.1).
        "testimonials": Review.objects.filter(
            is_approved=True, rating=5
        ).select_related("product")[:3],
        "dealer_count": dealer_count,
        # landing-page-v1 "09 — CAROUSEL": see carousel_slides comment above.
        "carousel_slides": carousel_slides,
        # landing-page-v1 "05 — HORIZONTAL FEATURES": pure admin content
        # (image + claim), no real-data fallback exists, so this is simply
        # empty until an admin adds rows -- the template guards on it.
        "showcase_panels": home_content.showcase_panels.all(),
    })


def about_view(request):
    return render(request, "content/about.html", {
        "company": CompanyInfo.get_solo(),
        "about": AboutPageContent.get_solo(),
        # The reference hardcoded "12 Motorcycle Models" and "8 EU Dealers" in
        # its By-the-Numbers row. Both have a real source, so they are counted
        # rather than asserted. The other two stats ("15K+ Riders Worldwide",
        # "0g CO2 Per Km") have no backing model, so they're admin copy on
        # AboutPageContent instead.
        "motorcycle_count": Product.objects.filter(
            product_type=ProductType.MOTORCYCLE, is_active=True
        ).count(),
        "dealer_count": Dealer.objects.filter(is_active=True).count(),
        # Stands in for the reference's hardcoded Pexels hero/workshop photos,
        # used only when the admin hasn't uploaded an explicit hero/mission
        # image on AboutPageContent.
        "hero_product": Product.objects.filter(
            product_type=ProductType.MOTORCYCLE, is_active=True
        ).order_by("-price").first(),
    })


def story_list_view(request):
    published = Story.objects.filter(is_published=True)
    return render(request, "content/story_list.html", {
        # The reference's .blog-featured panel was a hardcoded article. The
        # newest published Story takes its place, and is excluded from the grid
        # below so it isn't shown twice (the reference's demo data never
        # overlapped, so this case simply never arose there).
        "featured_story": published.first(),
        "stories": published[1:],
    })


def story_detail_view(request, slug):
    story = get_object_or_404(Story, slug=slug, is_published=True)
    return render(request, "content/story_detail.html", {"story": story})


def support_view(request):
    """
    Spec 6.20: a live FAQ search plus a contact form embedded at the
    bottom of the page. Submitting the contact form here behaves exactly
    like support.views.contact_view — see that module's shared handler.
    """
    if request.method == "POST":
        contact_form = handle_contact_submission(request)
        if contact_form is None:
            return redirect("content:support")
    else:
        contact_form = None

    contact_form = contact_form or ContactForm()

    search_form = FAQSearchForm(request.GET or None)
    entries = FAQEntry.objects.filter(is_active=True)
    query = ""
    if search_form.is_valid() and search_form.cleaned_data["q"]:
        query = search_form.cleaned_data["q"]
        entries = entries.filter(
            Q(question__icontains=query) | Q(answer__icontains=query) | Q(category__icontains=query)
        )

    # The reference's four .support-cat cards ("N articles", clicking scrolls
    # to that category) were built from ARKO_DATA.faq client-side. Built the
    # same shape server-side instead: real per-category counts, and an
    # explicit icon per category (not a name-munge — see FAQ_CATEGORY_ICONS).
    categories = [
        {
            "value": value,
            "label": label,
            "icon": FAQ_CATEGORY_ICONS.get(value, "bx-help-circle"),
            "count": FAQEntry.objects.filter(is_active=True, category=value).count(),
        }
        for value, label in FAQCategory.choices
    ]

    return render(request, "content/support.html", {
        "search_form": search_form,
        "contact_form": contact_form,
        "entries": entries,
        "query": query,
        "categories": categories,
        "support": SupportPageContent.get_solo(),
    })


def faq_search_json(request):
    """
    AJAX (allowed use case: search-as-you-type — spec 6.20's live FAQ filter
    is the same category of interaction as catalog.views.search_suggest_json,
    just over FAQEntry instead of Product). Mirrors that endpoint's shape:
    tiny, read-only, matches the same three fields support_view's own GET
    filtering already uses, so live-typed results and a full-page reload of
    the same query never disagree.
    """
    query = request.GET.get("q", "").strip()
    entries = FAQEntry.objects.filter(is_active=True)
    if query:
        entries = entries.filter(
            Q(question__icontains=query) | Q(answer__icontains=query) | Q(category__icontains=query)
        )
    by_category = {}
    for entry in entries:
        by_category.setdefault(entry.category, []).append({"question": entry.question, "answer": entry.answer})
    return JsonResponse({
        "categories": [
            {"value": value, "label": label, "items": by_category[value]}
            for value, label in FAQCategory.choices if value in by_category
        ]
    })


def _legal_document_view(request, template_name, slug):
    company = CompanyInfo.get_solo()
    document = get_object_or_404(LegalDocument, slug=slug)
    return render(request, template_name, {
        "company": company,
        "document": document,
        "document_body": merge_company_fields(document.body, company),
    })


def terms_view(request):
    return _legal_document_view(request, "content/terms.html", "terms")


def privacy_view(request):
    return _legal_document_view(request, "content/privacy.html", "privacy")


def page_not_found_view(request, exception):
    """Custom 404 handler (wired as `handler404` in the URLConf phase)."""
    return render(request, "content/404.html", {"not_found": NotFoundPageContent.get_solo()}, status=404)
