"""
catalog.views

Spec Chapter 6: 6.1 (Shop), 6.2 (Accessories), 6.3 (Product Detail), 6.4
(Reviews), 6.5 (Configurator), 6.6 (Compare), 6.7 (Wishlist display), 6.19
(Search). Function-based views throughout, GET/POST with the
Post-Redirect-Get pattern; the only JsonResponse endpoints here
(`search_suggest_json`, `configurator_running_total_json`) are the two
explicitly enumerated AJAX use cases outside of Cart/Checkout.

TODO.md "Major" fix: Wishlist and Compare used to have no backing model at
all, taking product IDs only from a `?ids=` querystring. Both now have a
real Wishlist/Compare model pair (session-scoped for guests, account-
persisted for registered customers, mirroring cart.models.Cart exactly —
see models.py, catalog/utils.py's get_wishlist/get_compare, and
catalog/signals.py's merge-on-login). `wishlist_view`/`compare_view`
default to that real collection; an explicit `?ids=` still works as an
override for a shareable link, same shape the static build used.
`wishlist_toggle_view`/`compare_toggle_view` are the new PRG POST
endpoints that actually add/remove a line. `compare_clear_view` and
`wishlist_move_to_cart_view`/`wishlist_move_all_to_cart_view` (Step 2,
catalog templates) are the real, server-side versions of the static
build's "Clear All" and "Move (All) to Cart" buttons, each still a single
PRG POST for what was always presented as one user-facing action.
"""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cart.utils import add_item_to_cart, get_cart
from core.constants import FREE_SHIPPING_THRESHOLD

from .forms import AccessoryFilterForm, MotorcycleFilterForm, ReviewForm, SearchForm
from .models import Category, Product, ProductType, VariantOption
from .utils import (
    filter_and_sort_products,
    get_compare,
    get_recently_viewed,
    get_wishlist,
    rating_breakdown,
    record_recently_viewed,
)


def _default_add_to_cart_options(product):
    """
    Djangofication brief (Step 2, catalog): a product-grid card, a Compare
    row, and a Wishlist row all have a one-click "Add to Cart"/"Move to
    Cart" button with no color/size picker of its own — exactly like the
    static build's `ARKO_STORE.addToCart(id, 1, {})` calls, which never
    asked for a color/size either. cart.forms.AddToCartForm does require a
    color (when the product has any) and a size (accessories with sizes),
    though, so these one-click entry points default to the product's
    first defined color/size — a shopper who wants a different one uses
    "View" to reach the full product page's picker instead.
    """
    color = ""
    first_color = product.colors.first()
    if first_color:
        color = first_color.name
    size = ""
    if product.is_accessory:
        first_size = product.sizes.first()
        if first_size:
            size = first_size.label
    return color, size


def shop_view(request):
    """Spec 6.1: the 11-model motorcycle grid with sidebar filters and a sort/view toolbar."""
    form = MotorcycleFilterForm(request.GET or None)
    base_qs = Product.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True)

    if form.is_valid():
        cd = form.cleaned_data
        products = filter_and_sort_products(
            base_qs,
            category_slugs=[c.slug for c in cd["category"]],
            max_price=cd["max_price"],
            min_range_km=Decimal(cd["min_range_km"]) if cd["min_range_km"] else None,
            availability=cd["availability"],
            colors=cd["color"],
            sort=cd["sort"] or "featured",
        )
    else:
        products = filter_and_sort_products(base_qs)

    # Spec 6.1 step 5: a category link elsewhere on the site can pre-check a
    # category via a URL parameter even before any filter form is submitted.
    category_counts = {
        c.slug: c.products.filter(is_active=True).count()
        for c in Category.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True)
    }

    return render(request, "catalog/shop.html", {
        "form": form,
        "products": products,
        "result_count": len(products),
        "category_counts": category_counts,
    })


def accessories_view(request):
    """Spec 6.2: a smaller mirror of the Shop page for the 12-item accessory catalog."""
    form = AccessoryFilterForm(request.GET or None)
    base_qs = Product.objects.filter(product_type=ProductType.ACCESSORY, is_active=True)

    if form.is_valid():
        cd = form.cleaned_data
        products = filter_and_sort_products(
            base_qs,
            category_slugs=[c.slug for c in cd["category"]],
            max_price=cd["max_price"],
            in_stock_only=cd["in_stock_only"],
            sort=cd["sort"] or "featured",
        )
    else:
        products = filter_and_sort_products(base_qs)

    return render(request, "catalog/accessories.html", {
        "form": form,
        "products": products,
        "result_count": len(products),
    })


def product_detail_view(request, slug):
    """
    Spec 6.3: motorcycle or accessory detail page — one view for both,
    matching 3.1's "single lookup surface" trait (the site resolves a
    product by ID/slug regardless of type).
    """
    product = get_object_or_404(
        Product.objects.prefetch_related(
            "colors", "sizes", "images", "specs", "variant_groups__options",
            "reviews", "related_to__related_product", "recommended_accessories__accessory",
        ),
        slug=slug, is_active=True,
    )
    record_recently_viewed(request, product.pk)

    related = [rp.related_product for rp in product.related_to.all() if rp.related_product.is_active]
    if not related:
        # Spec 6.3 step 5: "falling back to a generic set of other motorcycles if none is defined."
        related = list(
            Product.objects.filter(product_type=product.product_type, is_active=True).exclude(pk=product.pk)[:4]
        )
    recommended_accessories = [
        ra.accessory for ra in product.recommended_accessories.all() if ra.accessory.is_active
    ] if product.is_motorcycle else []

    review_form = ReviewForm()

    return render(request, "catalog/product_detail.html", {
        "product": product,
        "related_products": related,
        "recommended_accessories": recommended_accessories,
        "rating_breakdown": rating_breakdown(product),
        "reviews": product.reviews.filter(is_approved=True),
        "review_form": review_form,
        "recently_viewed": get_recently_viewed(request, exclude_id=product.pk),
        # core.context_processors.NAV_ACTIVE_BY_URL_NAME intentionally has no
        # entry for catalog:product_detail (one view serves both product
        # types) -- this is that override, keyed off the actual product.
        "nav_active": "shop" if product.is_motorcycle else "accessories",
        # The delivery blurbs used to promise "free EU delivery" — a flat
        # claim inherited from the pre-rebrand build. Shipping is priced per
        # wilaya now (core.utils.get_shipping_quote), with one rule that
        # still holds nationwide: free above this subtotal. Passed through
        # rather than written into the template so the copy can't drift from
        # what checkout actually charges.
        "free_shipping_threshold": FREE_SHIPPING_THRESHOLD,
    })


@login_required
def review_submit_view(request, slug):
    """
    Spec 6.4 "Write a Review" — now a real, persisted submission (fixing
    11.3.13's no-op). Edge case 15.1: allowed even from a customer who
    never purchased the product; `is_verified_purchase` is set from the
    customer's own order history rather than left to the submitter.
    """
    product = get_object_or_404(Product, slug=slug, is_active=True)
    if request.method != "POST":
        return redirect("catalog:product_detail", slug=slug)

    form = ReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.product = product
        review.user = request.user
        review.author_name = request.user.get_full_name() or request.user.username
        review.is_verified_purchase = product.order_items.filter(order__user=request.user).exists()
        review.save()
        messages.success(request, "Thank you — your review has been posted.")
    else:
        messages.error(request, "Please correct the errors in your review.")
    return redirect("catalog:product_detail", slug=slug)


def compare_view(request):
    """
    Spec 6.6: up to 4 motorcycles, side by side. Defaults to the visitor's
    real Compare list (TODO.md fix — session for guests, account for
    registered customers); an explicit `?ids=` overrides it, e.g. for a
    shareable link. IDs past the 4-model cap are silently ignored rather
    than erroring, since the cap itself is enforced when a model is added
    (compare_toggle_view), not here.
    """
    ids_param = request.GET.get("ids")
    if ids_param is not None:
        ids = [int(v) for v in ids_param.split(",") if v.strip().isdigit()][:4]
    else:
        ids = get_compare(request).product_ids[:4]

    products = list(
        Product.objects.filter(pk__in=ids, product_type=ProductType.MOTORCYCLE, is_active=True)
        .prefetch_related("colors", "specs")
    )
    products.sort(key=lambda p: ids.index(p.pk))

    all_specs = ["Range", "Power", "Weight", "Top Speed", "Battery Capacity", "Charge Time"]
    differing_specs = set()
    if len(products) > 1:
        for key in all_specs:
            values = {next((s.value for s in p.specs.all() if s.key == key), None) for p in products}
            if len(values) > 1:
                differing_specs.add(key)

    other_motorcycles = Product.objects.filter(
        product_type=ProductType.MOTORCYCLE, is_active=True
    ).exclude(pk__in=[p.pk for p in products])

    return render(request, "catalog/compare.html", {
        "products": products,
        "spec_keys": all_specs,
        "differing_specs": differing_specs,
        "other_motorcycles": other_motorcycles,
    })


@require_POST
def compare_toggle_view(request):
    """
    PRG POST endpoint (TODO.md fix) that actually adds/removes a line in
    the visitor's Compare list — the "Add to Compare" control everywhere
    a motorcycle card appears posts here rather than only ever linking to
    `?ids=`. Redirects back to `next` (defaults to the Compare page).
    """
    product = get_object_or_404(
        Product, pk=request.POST.get("product_id"), product_type=ProductType.MOTORCYCLE, is_active=True
    )
    compare = get_compare(request)
    item = compare.items.filter(product=product).first()
    if item:
        item.delete()
        messages.success(request, f'Removed "{product.name}" from Compare.')
    elif compare.items.count() >= 4:
        messages.error(request, "You can compare up to 4 models at a time — remove one first.")
    else:
        compare.items.create(product=product)
        messages.success(request, f'Added "{product.name}" to Compare.')
    return redirect(request.POST.get("next") or "catalog:compare")


@require_POST
def compare_clear_view(request):
    """
    PRG POST endpoint for the Compare page's "Clear All" button. The
    static build's equivalent looped `ARKO_STORE.removeFromCompare()`
    client-side across every id; a single bulk-delete is the real,
    server-side version of the same one user-facing action.
    """
    get_compare(request).items.all().delete()
    messages.success(request, "Compare list cleared.")
    return redirect(request.POST.get("next") or "catalog:compare")


def wishlist_view(request):
    """
    Spec 6.7: the Wishlist page. Defaults to the visitor's real Wishlist
    (TODO.md fix — session for guests, account for registered customers);
    an explicit `?ids=` still overrides it, e.g. for a shareable link.
    """
    ids_param = request.GET.get("ids")
    if ids_param is not None:
        ids = [int(v) for v in ids_param.split(",") if v.strip().isdigit()]
    else:
        ids = get_wishlist(request).product_ids
    products = Product.objects.filter(pk__in=ids, is_active=True)
    return render(request, "catalog/wishlist.html", {"products": products})


@require_POST
def wishlist_toggle_view(request):
    """
    PRG POST endpoint (TODO.md fix) that actually adds/removes a line in
    the visitor's Wishlist — the heart/"Add to Wishlist" control anywhere
    a product card appears posts here. Redirects back to `next` (defaults
    to the Wishlist page).
    """
    product = get_object_or_404(Product, pk=request.POST.get("product_id"), is_active=True)
    wishlist = get_wishlist(request)
    item = wishlist.items.filter(product=product).first()
    if item:
        item.delete()
        messages.success(request, f'Removed "{product.name}" from your wishlist.')
    else:
        wishlist.items.create(product=product)
        messages.success(request, f'Added "{product.name}" to your wishlist.')
    return redirect(request.POST.get("next") or "catalog:wishlist")


@require_POST
def wishlist_move_to_cart_view(request):
    """
    PRG POST endpoint for the Wishlist page's per-item "Move to Cart"
    button — the static build's `moveToCart()` did both
    `ARKO_STORE.addToCart()` and `removeFromWishlist()` in one click, so
    this is the real, server-side version of that same one user-facing
    action (cart.utils.add_item_to_cart + a Wishlist line delete).
    """
    product = get_object_or_404(Product, pk=request.POST.get("product_id"), is_active=True)
    color, size = _default_add_to_cart_options(product)
    add_item_to_cart(get_cart(request), product, quantity=1, selected_color=color, selected_size=size)
    get_wishlist(request).items.filter(product=product).delete()
    messages.success(request, f'Moved "{product.name}" to your cart.')
    return redirect(request.POST.get("next") or "catalog:wishlist")


@require_POST
def wishlist_move_all_to_cart_view(request):
    """Same as wishlist_move_to_cart_view above, for the "Move All to Cart" button."""
    wishlist = get_wishlist(request)
    cart = get_cart(request)
    products = list(Product.objects.filter(pk__in=wishlist.product_ids, is_active=True))
    for product in products:
        color, size = _default_add_to_cart_options(product)
        add_item_to_cart(cart, product, quantity=1, selected_color=color, selected_size=size)
    wishlist.items.all().delete()
    messages.success(request, "All items moved to your cart.")
    return redirect(request.POST.get("next") or "catalog:wishlist")


def search_view(request):
    """Spec 6.19: substring match on name/category/description, across both product types."""
    form = SearchForm(request.GET or None)
    query = ""
    product_type = "all"
    products = []

    if form.is_valid():
        query = form.cleaned_data["q"].strip()
        product_type = form.cleaned_data["type"] or "all"
        if query:
            qs = Product.objects.filter(is_active=True).filter(
                Q(name__icontains=query) | Q(category__name__icontains=query) | Q(description__icontains=query)
            )
            if product_type in (ProductType.MOTORCYCLE, ProductType.ACCESSORY):
                qs = qs.filter(product_type=product_type)
            products = list(qs)

    return render(request, "catalog/search.html", {
        "form": form,
        "query": query,
        "products": products,
        "result_count": len(products),
    })


def search_suggest_json(request):
    """AJAX (allowed use case: "product search-as-you-type"). Spec 6.19 step 2."""
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"results": []})

    products = Product.objects.filter(is_active=True).filter(
        Q(name__icontains=query) | Q(category__name__icontains=query) | Q(description__icontains=query)
    )[:8]
    return JsonResponse({
        "results": [
            {
                "id": p.pk,
                "slug": p.slug,
                "name": p.name,
                "product_type": p.product_type,
                "price": str(p.price),
            }
            for p in products
        ]
    })


def configurator_view(request, slug=None):
    """
    Spec 6.5: a six-step guided build. Step 1 (choose a model) is this
    view with `slug=None`; a deep link (or choosing a model) re-renders it
    with that model's colors/variants/recommended accessories loaded for
    steps 2-6. "Add to Cart"/"Buy Now" post straight to
    cart.views.add_to_cart_view — the Configurator has no submission
    endpoint of its own (spec 6.5 business rule: the cart has no awareness
    a line came from the Configurator).
    """
    motorcycles = Product.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True)
    selected = None
    if slug:
        selected = get_object_or_404(
            motorcycles.prefetch_related("colors", "variant_groups__options", "recommended_accessories__accessory"),
            slug=slug,
        )

    context = {"motorcycles": motorcycles, "selected": selected}
    if selected:
        context["recommended_accessories"] = [
            ra.accessory for ra in selected.recommended_accessories.all() if ra.accessory.is_active
        ]
    return render(request, "catalog/configurator.html", context)


def configurator_running_total_json(request):
    """
    AJAX (allowed use case: "Configurator running total"). Spec 6.5: "a
    running total" that updates after every choice, before anything is
    added to the cart. Accepts `product_id`, `color`, repeated `option`
    (VariantOption ids — at most one per variant group, same BR-CART-01
    rule cart.forms.AddToCartForm enforces), and repeated `accessory`
    (accessory Product ids).
    """
    product_id = request.GET.get("product_id")
    product = Product.objects.filter(
        pk=product_id, product_type=ProductType.MOTORCYCLE, is_active=True
    ).first()
    if product is None:
        return JsonResponse({"error": "Choose a model first."}, status=400)

    line_items = [{"label": product.name, "price": str(product.price)}]
    total = product.price

    option_ids = request.GET.getlist("option")
    options = VariantOption.objects.filter(pk__in=option_ids, variant_group__product=product)
    seen_groups = set()
    for option in options:
        if option.variant_group_id in seen_groups:
            continue
        seen_groups.add(option.variant_group_id)
        if option.price_delta:
            line_items.append({"label": f"{option.variant_group.name}: {option.label}", "price": str(option.price_delta)})
        total += option.price_delta

    accessory_ids = request.GET.getlist("accessory")
    recommended_ids = set(
        product.recommended_accessories.values_list("accessory_id", flat=True)
    )
    accessories = Product.objects.filter(
        pk__in=[aid for aid in accessory_ids if int(aid) in recommended_ids], is_active=True
    )
    for accessory in accessories:
        line_items.append({"label": accessory.name, "price": str(accessory.price)})
        total += accessory.price

    return JsonResponse({"line_items": line_items, "total": str(total)})
