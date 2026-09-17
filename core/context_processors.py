"""
core.context_processors

Site-wide values every template needs regardless of which app's view
rendered the page -- wired into TEMPLATES["OPTIONS"]["context_processors"]
in config/settings.py so `templates/base.html`'s header can read them
directly, without every view function threading them through by hand.

Two responsibilities:

1. `header_badges` -- the Cart/Wishlist/Compare counts shown next to the
   header icons (functional spec 5.1), plus the product-ID sets templates
   need to render a filled vs. empty heart/compare icon on a product card
   anywhere on the site. All three collections are real, persisted models
   now (see cart.models.Cart, catalog.models.Wishlist, catalog.models.Compare
   and their matching `get_cart`/`get_wishlist`/`get_compare` helpers), so
   every count here is computed from the live DB per BR-CART-02's pattern
   (session-keyed for a guest, account-keyed for a registered customer) --
   the "server-side per request" rule the shell must follow.

   FIXED (TODO.md "Major"): Wishlist and Compare used to have no backing
   model or session storage at all -- catalog.views.wishlist_view /
   compare_view took their product IDs only from a `?ids=` querystring, so
   this processor could only ever report 0/hidden for those two badges.
   Both now have a real Wishlist/Compare model pair mirroring Cart's own
   guest-session-vs-account pattern exactly, so their counts (and id sets)
   are read the same way the cart count already was. This processor does
   a read-only lookup -- it never creates a Wishlist/Compare row just
   because a page was viewed; that only happens the first time a visitor
   actually adds something (see catalog.utils.get_wishlist/get_compare,
   used by the new wishlist_toggle/compare_toggle views).

2. `nav_active_default` -- a best-effort default for which top-level nav
   link should render `.active`, keyed off `request.resolver_match`
   (namespace:url_name) so individual view functions don't all have to
   pass a `nav_active` string by hand. A view can still override it by
   putting its own `nav_active` key in the context it passes to
   `render()` -- Django layers that explicit context on top of
   processor-provided context, so the view's value always wins.

   Note this deliberately does NOT reproduce the reference static
   build's `data-active` values verbatim: the static prototype marks
   several unrelated pages (financing.html, stories.html, test-ride.html,
   login.html, cart.html, account.html, order-success.html, search.html,
   orders.html, checkout.html, insurance.html, wishlist.html) as
   `data-active="shop"`, which doesn't correspond to any real "this page
   is part of the Motorcycles section" relationship -- it reads as a
   copy-paste default rather than an intentional design choice. This
   processor instead maps only the pages that genuinely belong to a
   top-nav section; everything else defaults to "" (no highlighted nav
   item), same as the static build's Login/Register/Terms/Privacy/About
   pages already do.
"""

NAV_ACTIVE_BY_URL_NAME = {
    "content:home": "home",
    "catalog:shop": "shop",
    "catalog:compare": "shop",
    "catalog:accessories": "accessories",
    "catalog:configurator": "configurator",
    "catalog:configurator_model": "configurator",
    "dealers:dealer_list": "dealers",
    # The static test-ride.html ships `data-active="shop"` while service.html
    # ships `data-active="dealers"` -- preserved verbatim from the reference
    # pages rather than normalised, since both are legitimate reads of where
    # each booking flow belongs in the nav.
    "bookings:test_ride": "shop",
    "bookings:test_ride_confirmation": "shop",
    "bookings:service_booking": "dealers",
    "bookings:service_confirmation": "dealers",
    "content:support": "support",
    "support:contact": "support",
    # catalog:product_detail is intentionally absent -- it serves both
    # motorcycles and accessories from one view, so product_detail_view
    # overrides `nav_active` itself based on `product.product_type`.
}


def site_identity(request):
    """
    CompanyInfo, available to every template (base.html's footer -- social
    links, brand blurb -- and any page that needs the brand's legal/contact
    identity) without each view threading it through by hand. Views that
    already pass their own `company` in context (about_view, terms_view,
    privacy_view) simply override this with the identical singleton.

    `site_name` is exported alongside it as the one string every template
    uses for the brand (header wordmark, <title>, footer, invoices). It was
    previously the hardcoded literal "ARKO" in ~50 templates; routing it
    through CompanyInfo.trade_name means renaming the business is an admin
    edit, not a find-and-replace across the codebase. It falls back to
    legal_name so the site never renders a blank brand if trade_name is
    cleared.
    """
    from core.models import CompanyInfo

    company = CompanyInfo.get_solo()
    return {
        "company": company,
        "site_name": company.trade_name or company.legal_name,
        "site_tagline": company.tagline,
    }


def header_badges(request):
    cart_count = 0
    wishlist_ids = []
    compare_ids = []

    if request.user.is_authenticated:
        cart = getattr(request.user, "cart", None)
        if cart is not None:
            cart_count = cart.item_count

        wishlist = getattr(request.user, "wishlist", None)
        if wishlist is not None:
            wishlist_ids = wishlist.product_ids

        compare = getattr(request.user, "compare", None)
        if compare is not None:
            compare_ids = compare.product_ids

    elif request.session.session_key:
        from cart.models import Cart
        from catalog.models import Compare, Wishlist

        cart = Cart.objects.filter(
            session_key=request.session.session_key, user__isnull=True
        ).first()
        if cart is not None:
            cart_count = cart.item_count

        wishlist = Wishlist.objects.filter(
            session_key=request.session.session_key, user__isnull=True
        ).first()
        if wishlist is not None:
            wishlist_ids = wishlist.product_ids

        compare = Compare.objects.filter(
            session_key=request.session.session_key, user__isnull=True
        ).first()
        if compare is not None:
            compare_ids = compare.product_ids

    return {
        "header_cart_count": cart_count,
        "header_wishlist_count": len(wishlist_ids),
        "header_compare_count": len(compare_ids),
        # Product-ID sets so a product card anywhere on the site can render
        # a filled vs. empty heart/compare icon without a per-card query.
        "header_wishlist_ids": wishlist_ids,
        "header_compare_ids": compare_ids,
    }


def nav_active_default(request):
    match = getattr(request, "resolver_match", None)
    key = f"{match.namespace}:{match.url_name}" if match and match.namespace else None
    return {"nav_active": NAV_ACTIVE_BY_URL_NAME.get(key, "")}


def mega_menu_catalog(request):
    """
    functional spec 5.1: the "Motorcycles" mega-menu's *By Category* column
    (real, admin-editable `Category` rows, not the static build's fixed
    Enduro/Trail/Adventure/Performance strings -- BR-CAT lets admins add
    categories without a deploy, so the header must reflect whatever
    exists) and *Featured* column (3 direct product links).

    FLAGGED DECISION re: Featured -- static build hardcodes RVX / RVX Pro /
    Performance RS by mock ID; every internal link must be a real
    `{% url %}` to a real `Product.slug`, and `Product` has no explicit
    `is_featured` flag, only `Badge` (best_seller/new/sale/limited).
    Read as "has a merchandising badge", newest first; if fewer than 3
    active motorcycles have a badge, the most-recently-created active
    motorcycles fill the remainder, so the mega-menu always has up to 3
    real links, never a broken slug.
    """
    from catalog.models import Category, Product, ProductType

    motorcycles = Product.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True)
    featured = list(motorcycles.exclude(badge="").order_by("-created_at")[:3])
    if len(featured) < 3:
        fill_ids = [p.pk for p in featured]
        featured += list(motorcycles.exclude(pk__in=fill_ids).order_by("-created_at")[: 3 - len(featured)])

    motorcycle_categories = Category.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True)
    # functional spec 5.3: footer "Shop" column lists Accessories overall
    # plus by-category links (static build: Riding Gear / Chargers / Parts)
    # -- same real-Category reasoning as the mega-menu column above.
    accessory_categories = Category.objects.filter(product_type=ProductType.ACCESSORY, is_active=True)

    return {
        "mega_menu_categories": motorcycle_categories,
        "mega_menu_featured_products": featured,
        "footer_accessory_categories": accessory_categories,
    }
