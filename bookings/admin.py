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

from .models import ServiceBooking, ServiceTier, TestRideBooking, TimeSlot


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


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    """
    The slots the Test Ride and Service booking forms offer.

    `code` is what every booking stores, so it is only editable while
    adding: renaming an existing slot's code would orphan the bookings
    already made against it. Retiring a slot means unchecking `is_active`,
    which withdraws it from the forms while leaving old bookings able to
    render their own label.
    """

    list_display = ("code", "label", "sort_order", "is_active")
    list_editable = ("label", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "label")
    ordering = ("sort_order", "code")

    def get_readonly_fields(self, request, obj=None):
        return ("code",) if obj else ()
