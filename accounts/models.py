from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.constants import language_choices, wilaya_choices


class UserRole(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    DEALER_STAFF = "dealer_staff", "Dealer Staff"
    ADMIN = "admin", "Store Administrator"


class UserProfile(models.Model):
    """
    OneToOne extension of Django's built-in User (spec: "Django's built-in
    User model with a OneToOne Profile relationship"). Carries the role used
    for permission scoping (BR-ACC-04) plus the Account > Preferences tab
    fields (spec 6.17).
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.CUSTOMER)
    dealer = models.ForeignKey(
        "dealers.Dealer", on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_profiles",
        help_text="Required when role = Dealer Staff (BR-ACC-04); booking-queue access is scoped to this dealer only.",
    )
    phone = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    preferred_language = models.CharField(max_length=5, choices=language_choices, default="fr")

    # Preferences tab (spec 6.17.5): three notification toggles.
    marketing_opt_in = models.BooleanField(default=True, help_text="Product updates / news — on by default.")
    order_notifications_opt_in = models.BooleanField(default=True, help_text="Order notifications — on by default.")
    promo_opt_in = models.BooleanField(default=False, help_text="Promotional offers — off by default.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} ({self.get_role_display()})"

    def clean(self):
        if self.role == UserRole.DEALER_STAFF and not self.dealer_id:
            raise ValidationError({"dealer": "Dealer Staff must be assigned to a dealer (BR-ACC-04)."})
        if self.role != UserRole.DEALER_STAFF and self.dealer_id:
            raise ValidationError({"dealer": "Only Dealer Staff may be assigned to a dealer."})


class Address(models.Model):
    """A customer's saved shipping address (spec 6.17.6). Only one default
    per user; saving a new default clears the flag on the others."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=50, blank=True, help_text='e.g. "Home", "Work".')
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100, help_text="Commune / city.")
    postal_code = models.CharField(max_length=20)
    wilaya = models.CharField(max_length=2, choices=wilaya_choices)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Addresses"
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.street}, {self.city} ({self.user})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            Address.objects.filter(user=self.user).exclude(pk=self.pk).update(is_default=False)


class GarageEntry(models.Model):
    """
    A motorcycle associated with a customer's account (spec 6.17.2, 8.x).
    Auto-created on motorcycle purchase (BR-ORD-05) — that creation itself
    happens via a signal in a later phase, not here.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="garage_entries")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="garage_entries")
    order_item = models.ForeignKey(
        "orders.OrderItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="garage_entry",
        help_text="Links this entry back to the purchase that created it, if any.",
    )
    vin = models.CharField(max_length=17, unique=True, verbose_name="VIN")
    warranty_active = models.BooleanField(default=True)
    service_due_at = models.DateField(null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Garage Entries"
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.product.name} - {self.vin} ({self.user})"

    def clean(self):
        if self.product_id and not self.product.is_motorcycle:
            raise ValidationError({"product": "Only motorcycles can be added to the Garage."})
