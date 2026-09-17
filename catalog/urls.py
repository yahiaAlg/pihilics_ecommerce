"""
catalog.urls

Spec 6.1-6.7 and 6.19. Mounted at the site root by the project URLConf.
`product_detail_view` is the single lookup surface for both motorcycles
and accessories (see views.py module docstring), so there is one
`<slug:slug>/` route rather than separate motorcycle/accessory detail
paths. `search_suggest_json` and `configurator_running_total_json` are two
of the four explicitly allowed AJAX (JsonResponse) endpoints.
`wishlist_toggle`/`compare_toggle` are plain PRG POST endpoints (TODO.md
fix), not AJAX.
"""

from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("shop/", views.shop_view, name="shop"),
    path("accessories/", views.accessories_view, name="accessories"),
    path("products/<slug:slug>/", views.product_detail_view, name="product_detail"),
    path("products/<slug:slug>/review/", views.review_submit_view, name="review_submit"),
    path("compare/", views.compare_view, name="compare"),
    path("compare/toggle/", views.compare_toggle_view, name="compare_toggle"),
    path("compare/clear/", views.compare_clear_view, name="compare_clear"),
    path("wishlist/", views.wishlist_view, name="wishlist"),
    path("wishlist/toggle/", views.wishlist_toggle_view, name="wishlist_toggle"),
    path("wishlist/move-to-cart/", views.wishlist_move_to_cart_view, name="wishlist_move_to_cart"),
    path("wishlist/move-all-to-cart/", views.wishlist_move_all_to_cart_view, name="wishlist_move_all_to_cart"),
    path("search/", views.search_view, name="search"),
    path("search/suggest/", views.search_suggest_json, name="search_suggest"),  # AJAX
    path("configurator/", views.configurator_view, name="configurator"),
    # BUG FOUND & FIXED (this session): this must come before
    # "configurator/<slug:slug>/" below -- Django tries urlpatterns in
    # order, so with the slug pattern first, a GET to
    # "configurator/running-total/" matched it as slug="running-total"
    # and 404'd (no product has that slug) instead of ever reaching this
    # view. Reproduced live: the Configurator template's running-total
    # AJAX call (the one explicitly allowed AJAX case for this app) was
    # unreachable until this reorder.
    path("configurator/running-total/", views.configurator_running_total_json, name="configurator_running_total"),  # AJAX
    path("configurator/<slug:slug>/", views.configurator_view, name="configurator_model"),
]
