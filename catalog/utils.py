"""
catalog.utils
"""

import re

from django.db.models import Avg, Count, DecimalField, Q
from django.db.models.functions import Coalesce

from .models import Compare, Product, ProductType, Wishlist


def get_publish_blockers(product):
    """
    Checks BR-CAT-06 (name, category, price, at least one image) and, for
    motorcycles, BR-CAT-04 (each Variant Group needs a default option).
    Intended for the Forms/Admin phase to gate activating a Product.
    Returns a list of human-readable blocker strings; an empty list means
    the product is ready to publish.
    """
    blockers = []

    if not product.name:
        blockers.append("Product needs a name.")
    if not product.category_id:
        blockers.append("Product needs a category.")
    if product.price is None:
        blockers.append("Product needs a price.")
    if not product.images.exists():
        blockers.append("Product needs at least one image.")

    if product.product_type == ProductType.MOTORCYCLE:
        for group in product.variant_groups.all():
            if not group.has_default_option():
                blockers.append(f'Variant group "{group.name}" needs at least one default option.')

    return blockers


def annotate_average_rating(queryset):
    """Spec 6.4: mean of approved reviews, falling back to rating_cached — as a DB annotation for sorting."""
    return queryset.annotate(
        avg_rating=Coalesce(
            Avg("reviews__rating", filter=Q(reviews__is_approved=True)),
            "rating_cached",
            output_field=DecimalField(max_digits=4, decimal_places=2),
        )
    )


def _spec_number(product, key):
    """Extracts the leading numeric value from a freeform ProductSpec (e.g. "180 km" -> 180.0)."""
    spec = next((s for s in product.specs.all() if s.key.strip().lower() == key.lower()), None)
    if not spec:
        return None
    match = re.match(r"[\d.]+", spec.value.strip())
    return float(match.group()) if match else None


def filter_and_sort_products(queryset, *, category_slugs=None, max_price=None, min_range_km=None,
                              availability=None, colors=None, in_stock_only=False, sort="featured"):
    """
    Shared filter/sort engine for Shop (spec 6.1) and Accessories (spec
    6.2) — "functionally a smaller mirror" of each other, so one function
    serves both (accessories simply never pass min_range_km/colors).

    `availability_status` (BR-CAT: "derived, never stored") and the Range
    spec (a freeform ProductSpec value like "180 km", not a numeric
    column) can't be filtered/sorted in the database, so those two steps
    run in Python after the DB-level filters below have narrowed the set —
    acceptable at this catalog's scale (up to 500 products, BRD 6).
    """
    if category_slugs:
        queryset = queryset.filter(category__slug__in=category_slugs)
    if max_price is not None:
        queryset = queryset.filter(price__lte=max_price)
    if in_stock_only:
        queryset = queryset.filter(stock_quantity__gt=0)

    queryset = annotate_average_rating(queryset).prefetch_related("specs", "colors")
    products = list(queryset)

    if availability:
        # "In Stock" also covers Low Stock (still purchasable, just a
        # merchandising signal); products matching neither checked state
        # (e.g. Out of Stock, when neither box is checked) drop out.
        expanded = set(availability)
        if "in_stock" in expanded:
            expanded.add("low_stock")
        products = [p for p in products if p.availability_status in expanded]

    if colors:
        products = [p for p in products if {c.name for c in p.colors.all()} & set(colors)]

    if min_range_km is not None:
        products = [
            p for p in products
            if (val := _spec_number(p, "Range")) is not None and val >= min_range_km
        ]

    sort_key = {
        "price_asc": lambda p: p.price,
        "price_desc": lambda p: -p.price,
        "top_rated": lambda p: -float(p.avg_rating or 0),
        "longest_range": lambda p: -(_spec_number(p, "Range") or 0),
    }.get(sort)
    if sort_key:
        products.sort(key=sort_key)
    # "featured" (default, spec 6.1 step 3): preserve Product.Meta ordering (-created_at).

    return products


def rating_breakdown(product):
    """
    Spec 6.4: "a breakdown bar chart shows, for each star value from 5
    down to 1, what share of reviews fall into that bucket." Returns
    {5: {"count": int, "percent": int}, ..., 1: {...}}.
    """
    approved = product.reviews.filter(is_approved=True)
    total = approved.count()
    counts = {star: 0 for star in range(1, 6)}
    for row in approved.values("rating").annotate(count=Count("id")):
        counts[row["rating"]] = row["count"]
    return {
        star: {"count": counts[star], "percent": round(counts[star] / total * 100) if total else 0}
        for star in range(5, 0, -1)
    }


RECENTLY_VIEWED_SESSION_KEY = "recently_viewed_product_ids"
RECENTLY_VIEWED_MAX = 8


def record_recently_viewed(request, product_id):
    """
    Spec 3.2/6.3: "silently records up to the last 8 distinct products a
    visitor has opened a detail page for... most recent first, no
    duplicates." Unlike Wishlist/Compare (now real models -- see TODO.md),
    Chapter 11 treats this one specifically as fine to keep session-only
    with no dedicated model, even for a registered customer -- it's a
    browsing-history convenience, not a saved collection, so it isn't
    expected to follow the customer across devices. The session is the
    natural server-side equivalent of the prototype's localStorage here.
    """
    ids = request.session.get(RECENTLY_VIEWED_SESSION_KEY, [])
    ids = [pid for pid in ids if pid != product_id]
    ids.insert(0, product_id)
    request.session[RECENTLY_VIEWED_SESSION_KEY] = ids[:RECENTLY_VIEWED_MAX]


def get_recently_viewed(request, exclude_id=None):
    ids = request.session.get(RECENTLY_VIEWED_SESSION_KEY, [])
    if exclude_id is not None:
        ids = [pid for pid in ids if pid != exclude_id]
    products_by_id = {p.pk: p for p in Product.objects.filter(pk__in=ids, is_active=True)}
    return [products_by_id[pid] for pid in ids if pid in products_by_id]


def get_wishlist(request):
    """
    TODO.md "Major" fix: same account-vs-session pattern as
    cart.utils.get_cart (BR-CART-02), now applied to Wishlist so it's a
    real persisted collection instead of a `?ids=` querystring.
    """
    if request.user.is_authenticated:
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        return wishlist

    if not request.session.session_key:
        request.session.save()

    wishlist = Wishlist.objects.filter(session_key=request.session.session_key, user__isnull=True).first()
    if wishlist is None:
        wishlist = Wishlist.objects.create(session_key=request.session.session_key)
    return wishlist


def get_compare(request):
    """Same pattern as get_wishlist above, for the Compare collection (spec 6.6)."""
    if request.user.is_authenticated:
        compare, _ = Compare.objects.get_or_create(user=request.user)
        return compare

    if not request.session.session_key:
        request.session.save()

    compare = Compare.objects.filter(session_key=request.session.session_key, user__isnull=True).first()
    if compare is None:
        compare = Compare.objects.create(session_key=request.session.session_key)
    return compare
