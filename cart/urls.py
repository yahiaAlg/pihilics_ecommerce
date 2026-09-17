"""
cart.urls

Spec 6.8 (Cart) and 7.3 (Promo codes). Mounted at `cart/` by the project
URLConf. Every mutating endpoint here answers with a redirect (PRG) for a
plain form post, or JsonResponse for the "live cart totals" AJAX use case
— see views.py's `_is_ajax` helper. `totals/` is the GET-only refresh
endpoint that powers the same live-totals panel.
"""

from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("", views.cart_detail_view, name="cart_detail"),
    path("add/", views.add_to_cart_view, name="add_to_cart"),
    path("items/<int:item_id>/update/", views.update_cart_item_view, name="update_item"),
    path("items/<int:item_id>/remove/", views.remove_cart_item_view, name="remove_item"),
    path("clear/", views.clear_cart_view, name="clear_cart"),
    path("promo/apply/", views.apply_promo_view, name="apply_promo"),
    path("promo/remove/", views.remove_promo_view, name="remove_promo"),
    path("totals/", views.cart_totals_json, name="totals"),  # AJAX
]
