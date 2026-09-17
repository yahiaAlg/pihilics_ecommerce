from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.constants import time_slot_choices


class TimeSlot(models.Model):
    """
    A bookable half-day slot offered by the Test Ride and Service forms
    (spec 6.12/6.13), and the source of the `time_slot` choices on both
    booking models via core.constants.time_slot_choices.

    Was a two-entry hardcoded list. It is a table because opening hours
    are an operations decision, not a code one: adding an evening slot,
    shifting the afternoon window by an hour, or suspending mornings for
    a season are all things the shop should be able to do from the admin.

    `is_active` withdraws a slot from the booking forms while leaving
    every booking already made against it able to display its own label.
    """

    code = models.SlugField(
        max_length=20, unique=True,
        help_text='Stored on bookings, e.g. "morning". Changing it orphans existing bookings — add a new slot instead.',
    )
    label = models.CharField(
        max_length=100, help_text='What the customer sees, e.g. "Morning (9:00 - 13:00)".'
    )
    is_active = models.BooleanField(
        default=True, help_text="Uncheck to stop offering this slot without deleting it."
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0, help_text="Lower numbers appear first on the booking forms."
    )

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return self.label


class BookingStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    CONFIRMED = "confirmed", "Confirmed"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class ServiceTierName(models.TextChoices):
    ROUTINE_CHECK = "routine_check", "Routine Check"
    BATTERY_SERVICE = "battery_service", "Battery Service"
    MAJOR_SERVICE = "major_service", "Major Service"


class ServiceTier(models.Model):
    """One of three fixed-price maintenance packages (spec 6.13, 8.8)."""

    name = models.CharField(max_length=30, choices=ServiceTierName.choices, unique=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        from catalog.templatetags.catalog_extras import arko_price

        return f"{self.get_name_display()} ({arko_price(self.price)})"


class TestRideBooking(models.Model):
    """
    A scheduled test-ride appointment (spec 6.12, 8.8; BR-BK-*). Slot
    availability is enforced at the database level for CONFIRMED bookings
    (BR-BK-02); the REQUESTED-state conflict check against other pending
    requests happens at the view/form layer (a later phase), since it
    depends on business timing, not a hard DB constraint.
    """

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="test_ride_bookings")
    dealer = models.ForeignKey("dealers.Dealer", on_delete=models.PROTECT, related_name="test_ride_bookings")
    date = models.DateField()
    time_slot = models.CharField(max_length=20, choices=time_slot_choices)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    license_number = models.CharField(max_length=50, verbose_name="Motorcycle licence number")
    waiver_acknowledged = models.BooleanField(default=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="test_ride_bookings"
    )
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["dealer", "date", "time_slot"],
                condition=models.Q(status=BookingStatus.CONFIRMED),
                name="unique_confirmed_test_ride_slot",
            ),
        ]

    def __str__(self):
        return f"Test Ride - {self.product.name} @ {self.dealer.name} on {self.date}"

    def clean(self):
        if self.date and self.date <= timezone.localdate():
            raise ValidationError({"date": "Test ride date must be at least tomorrow."})
        if not self.waiver_acknowledged:
            raise ValidationError({"waiver_acknowledged": "The waiver must be acknowledged."})
        if self.product_id and not self.product.is_motorcycle:
            raise ValidationError({"product": "Test rides are for motorcycles only."})


class ServiceBooking(models.Model):
    """A scheduled maintenance appointment (spec 6.13, 8.8; BR-BK-*)."""

    garage_entry = models.ForeignKey(
        "accounts.GarageEntry", on_delete=models.SET_NULL, null=True, blank=True, related_name="service_bookings",
        help_text="The owned motorcycle this booking is for, when booked from the Garage.",
    )
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="service_bookings")
    dealer = models.ForeignKey("dealers.Dealer", on_delete=models.PROTECT, related_name="service_bookings")
    service_tier = models.ForeignKey(ServiceTier, on_delete=models.PROTECT, related_name="bookings")
    date = models.DateField()
    time_slot = models.CharField(max_length=20, choices=time_slot_choices)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="service_bookings"
    )
    contact_first_name = models.CharField(max_length=100)
    contact_last_name = models.CharField(max_length=100)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30)

    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["dealer", "date", "time_slot"],
                condition=models.Q(status=BookingStatus.CONFIRMED),
                name="unique_confirmed_service_slot",
            ),
        ]

    def __str__(self):
        return f"Service - {self.product.name} @ {self.dealer.name} on {self.date}"

    def clean(self):
        if self.date and self.date <= timezone.localdate():
            raise ValidationError({"date": "Service date must be at least tomorrow."})
        if self.garage_entry_id and self.user_id and self.garage_entry.user_id != self.user_id:
            raise ValidationError({"garage_entry": "Garage entry must belong to the booking's own user."})
