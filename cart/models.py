import hashlib
import json
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Cart(models.Model):
    """
    A guest's cart is keyed to their session; a registered customer's cart is
    keyed to their account and persists across devices (BR-CART-02). On
    login, the guest session cart is merged into the account cart
    (BR-CART-03) — handled by a signal in a later phase, not here.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="cart"
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session_key"],
                condition=models.Q(user__isnull=True),
                name="unique_guest_cart_session",
            ),
        ]

    def __str__(self):
        return f"Cart #{self.pk} ({self.user or self.session_key})"

    def clean(self):
        if not self.user_id and not self.session_key:
            raise ValidationError("A cart must belong to either a user or a guest session.")

    @property
    def subtotal(self):
        """BR-CART-04: always derived from current line prices, never cached as truth."""
        return sum((item.line_total for item in self.items.all()), start=0)

    @property
    def item_count(self):
        return sum((item.quantity for item in self.items.all()), start=0)


class CartItem(models.Model):
    """
    A cart line's identity is (product, color, size, sorted selected
    upgrades) — BR-CART-01. Matching identity increments quantity; any
    difference (different color/size/upgrade set) creates a new, separate
    line, even though both point at the same underlying product.
    """

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    selected_color = models.CharField(max_length=50, blank=True)
    selected_size = models.CharField(max_length=20, blank=True)
    selected_upgrades = models.JSONField(
        default=list, blank=True,
        help_text="List of {variant_group, option, price_delta} dicts selected on the product page or Configurator.",
    )
    options_key = models.CharField(
        max_length=64, editable=False, db_index=True,
        help_text="Deterministic hash of selected options; forms this line's identity together with product+cart.",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-added_at"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "product", "options_key"], name="unique_cart_line_identity"),
        ]

    def clean(self):
        if self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least 1 (BR-CART-05)."})

    def compute_options_key(self):
        upgrades_sorted = sorted(
            self.selected_upgrades or [],
            key=lambda u: (u.get("variant_group", ""), u.get("option", "")),
        )
        payload = json.dumps(
            {"color": self.selected_color, "size": self.selected_size, "upgrades": upgrades_sorted},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def save(self, *args, **kwargs):
        self.options_key = self.compute_options_key()
        super().save(*args, **kwargs)

    @property
    def unit_price(self):
        """
        BR-CART-04: unit price = base price + selected upgrade deltas,
        computed live. `price_delta` is stored as a string in the JSON
        blob (see AddToCartForm.get_selected_upgrades) since a plain
        JSONField can't round-trip Decimal directly; re-cast through
        Decimal(str(...)) here rather than summing floats, so this stays
        exact currency math instead of drifting through float precision.
        """
        upgrades_total = sum(
            (Decimal(str(u.get("price_delta", 0))) for u in (self.selected_upgrades or [])),
            start=Decimal("0"),
        )
        return self.product.price + upgrades_total

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


class PromoCode(models.Model):
    """Cart/Checkout discount code (spec 7.3; BR-CHK-03/05)."""

    code = models.CharField(max_length=30, unique=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code

    def clean(self):
        if not (0 < self.discount_percent <= 100):
            raise ValidationError({"discount_percent": "Must be greater than 0 and at most 100 (BR-CHK-05)."})
        if self.valid_until <= self.valid_from:
            raise ValidationError({"valid_until": "Must be after valid_from."})

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        super().save(*args, **kwargs)

    def is_valid_for(self, subtotal, at=None):
        """BR-CHK-05: active, within its validity window, and subtotal meets min_order_value."""
        at = at or timezone.now()
        return self.is_active and self.valid_from <= at <= self.valid_until and subtotal >= self.min_order_value
