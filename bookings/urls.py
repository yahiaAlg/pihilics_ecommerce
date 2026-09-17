"""
bookings.urls

Spec 6.12 (Test Ride), 6.13 (Service), and the Dealer Staff booking queue
(BR-BK-03/04). Mounted at `bookings/` by the project URLConf.
"""

from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("test-ride/", views.test_ride_view, name="test_ride"),
    path("test-ride/<int:pk>/confirmation/", views.test_ride_confirmation_view, name="test_ride_confirmation"),
    path("service/", views.service_booking_view, name="service_booking"),
    path("service/<int:pk>/confirmation/", views.service_confirmation_view, name="service_confirmation"),
    path("dealer-queue/", views.dealer_booking_queue_view, name="dealer_queue"),
    path(
        "dealer-queue/<str:booking_type>/<int:pk>/status/",
        views.booking_update_status_view,
        name="booking_update_status",
    ),
]
