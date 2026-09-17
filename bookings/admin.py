"""
bookings.admin

BR-BK-04: "Only Dealer Staff assigned to the booking's dealer (or a Store
Administrator) may confirm, reschedule, cancel, or complete a booking." The
dealer-staff side of that lives in bookings.views (scoped to their own
dealer); this admin is the Store Administrator side — unscoped, and with
`status` directly editable so completing a Service Booking here still
fires `bookings.signals.update_garage_entry_service_due_date` (BR-BK-05)
exactly as it would from the dealer queue.
"""

from django.contrib import admin

from .models import ServiceBooking, ServiceTier, TestRideBooking


@admin.register(ServiceTier)
class ServiceTierAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "is_active")
    list_editable = ("price", "is_active")
    list_filter = ("is_active",)


@admin.register(TestRideBooking)
class TestRideBookingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "date", "time_slot", "first_name", "last_name", "email")
    list_filter = ("status", "dealer", "date")
    list_editable = ("status",)
    search_fields = ("first_name", "last_name", "email", "license_number", "product__name", "dealer__name")
    autocomplete_fields = ("product", "dealer", "user")
    date_hierarchy = "date"


@admin.register(ServiceBooking)
class ServiceBookingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "status", "date", "time_slot", "service_tier", "contact_first_name", "contact_last_name")
    list_filter = ("status", "dealer", "service_tier", "date")
    list_editable = ("status",)
    search_fields = ("contact_first_name", "contact_last_name", "contact_email", "product__name", "dealer__name")
    autocomplete_fields = ("product", "dealer", "user", "garage_entry")
