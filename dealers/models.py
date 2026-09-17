from django.db import models
from django.utils.text import slugify

from core.constants import wilaya_choices


class Dealer(models.Model):
    """A physical retail/service location (spec 8.5)."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    city = models.CharField(max_length=100)
    wilaya = models.CharField(max_length=2, choices=wilaya_choices)
    address = models.CharField(max_length=255)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    hours = models.CharField(max_length=255, help_text="Human-readable opening hours.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.get_wilaya_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def has_pending_bookings(self):
        """Used to block deactivation while bookings are outstanding (spec 15.1)."""
        return (
            self.test_ride_bookings.filter(status__in=["requested", "confirmed"]).exists()
            or self.service_bookings.filter(status__in=["requested", "confirmed"]).exists()
        )
