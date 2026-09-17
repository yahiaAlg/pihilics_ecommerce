"""
orders.urls

Spec 6.9 (Checkout, 4 session-held steps), 6.10 (Order Confirmation), and
6.11 (Order history/detail/tracking), plus the "Documents" key requirement
(`order_invoice_view`: a printable confirmation/invoice at its own URL).
Mounted at the site root by the project URLConf, since this one app owns
both the `checkout/` and `orders/` top-level paths.

Static suffixes (`lookup/`, `<reference>/success/`, `.../track/`,
`.../invoice/`) are ordered ahead of/around the bare `<str:reference>/`
detail route so `lookup/` can never be captured as a reference value.
"""

from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/information/", views.checkout_information_view, name="checkout_information"),
    path("checkout/delivery/", views.checkout_delivery_view, name="checkout_delivery"),
    path("checkout/payment/", views.checkout_payment_view, name="checkout_payment"),
    path("checkout/review/", views.checkout_review_view, name="checkout_review"),
    path("orders/", views.order_list_view, name="order_list"),
    path("orders/lookup/", views.guest_order_lookup_view, name="guest_order_lookup"),
    path("orders/<str:reference>/success/", views.order_success_view, name="order_success"),
    path("orders/<str:reference>/track/", views.order_track_view, name="order_track"),
    path("orders/<str:reference>/invoice/", views.order_invoice_view, name="order_invoice"),
    path("orders/<str:reference>/payment/", views.order_payment_view, name="order_payment"),
    path("orders/<str:reference>/", views.order_detail_view, name="order_detail"),
    # Not "orders/<reference>/..." like the routes above -- Chargily posts
    # here with no order reference in the URL at all (the checkout id in
    # the payload is how the matching order is found), and the URL itself
    # is baked into create_checkout_for_order's webhook_endpoint, so it
    # must stay stable rather than be nested under a per-order path.
    path("payments/chargily/webhook/", views.chargily_webhook_view, name="chargily_webhook"),
]
