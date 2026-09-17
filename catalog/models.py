from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


class ProductType(models.TextChoices):
    MOTORCYCLE = "motorcycle", "Motorcycle"
    ACCESSORY = "accessory", "Accessory"


class Badge(models.TextChoices):
    BEST_SELLER = "best_seller", "Best Seller"
    NEW = "new", "New"
    SALE = "sale", "Sale"
    LIMITED = "limited", "Limited"


class AvailabilityStatus(models.TextChoices):
    IN_STOCK = "in_stock", "In Stock"
    LOW_STOCK = "low_stock", "Low Stock"
    OUT_OF_STOCK = "out_of_stock", "Out of Stock"
    PRE_ORDER = "pre_order", "Pre-Order"


class Category(models.Model):
    """Motorcycle or accessory category (spec 2.1: 4 motorcycle categories,
    5 accessory categories) — admin-editable, not a fixed code list, so the
    business can add categories without a deploy (BR-CAT-*, spec 3.1)."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    product_type = models.CharField(max_length=20, choices=ProductType.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "product_type"], name="unique_category_name_per_type"),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_product_type_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """
    A catalog item — either a Motorcycle or an Accessory (spec 8.1/8.2).

    - BR-CAT-01: slug is unique, URL-safe, and immutable once any Order
      references the product (enforced by disallowing slug edits once
      order_items exist — see `clean()`).
    - BR-CAT-02/03: products are never deleted, only deactivated; inactive
      products stay resolvable for historical order display but drop out of
      listings/search/Configurator (enforced at the query/view layer).
    - BR-CAT-06: a product needs a name, category, price, and at least one
      image before it can be published (enforced at the form/admin layer,
      since "at least one image" spans a related model).
    """

    slug = models.SlugField(max_length=140, unique=True)
    name = models.CharField(max_length=200)
    product_type = models.CharField(max_length=20, choices=ProductType.choices)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")

    price = models.DecimalField(max_digits=10, decimal_places=2)
    old_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Optional; when present, shown struck-through to indicate a sale.",
    )

    description = models.TextField(blank=True)
    features = models.JSONField(default=list, blank=True, help_text="Ordered list of feature bullet strings.")

    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    is_pre_order = models.BooleanField(default=False, help_text="Flags this product as pre-order rather than stock-driven.")

    badge = models.CharField(max_length=20, choices=Badge.choices, blank=True)

    rating_cached = models.DecimalField(
        max_digits=3, decimal_places=2, default=0,
        help_text="Headline rating used as a fallback when no approved reviews exist yet.",
    )
    review_count_cached = models.PositiveIntegerField(default=0)

    video_trailer_url = models.URLField(blank=True, help_text="Motorcycles only: hero/trailer video reference.")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.product_type == ProductType.ACCESSORY and self.video_trailer_url:
            raise ValidationError({"video_trailer_url": "Only motorcycles may have a video trailer (spec 8.2)."})
        if self.pk and self.order_items.exists():
            original_slug = Product.objects.filter(pk=self.pk).values_list("slug", flat=True).first()
            if original_slug and original_slug != self.slug:
                raise ValidationError({"slug": "Slug is immutable once an order references this product (BR-CAT-01)."})

    @property
    def is_motorcycle(self):
        return self.product_type == ProductType.MOTORCYCLE

    @property
    def is_accessory(self):
        return self.product_type == ProductType.ACCESSORY

    @property
    def availability_status(self):
        """Derived, never stored — cannot drift from real stock (spec 10.3)."""
        if self.stock_quantity == 0:
            return AvailabilityStatus.OUT_OF_STOCK
        if self.stock_quantity <= self.low_stock_threshold:
            return AvailabilityStatus.LOW_STOCK
        if self.is_pre_order:
            return AvailabilityStatus.PRE_ORDER
        return AvailabilityStatus.IN_STOCK

    @property
    def availability_css_class(self):
        """
        Design System Section 2 defines exactly three badge classes —
        `.in-stock` / `.pre-order` / `.out-stock` — for four possible
        `availability_status` values, and none of the three matches its
        enum value verbatim (`out_of_stock` != `out-stock`; `low_stock`
        has no class of its own at all). Templates must render this
        property directly as the badge class (never re-derive color with
        an `{% if %}` chain — Design System item 13) so LOW_STOCK folds
        into the same "still purchasable" treatment as IN_STOCK, matching
        catalog.utils.filter_and_sort_products' own availability grouping.
        """
        return {
            AvailabilityStatus.IN_STOCK: "in-stock",
            AvailabilityStatus.LOW_STOCK: "in-stock",
            AvailabilityStatus.PRE_ORDER: "pre-order",
            AvailabilityStatus.OUT_OF_STOCK: "out-stock",
        }[self.availability_status]

    @property
    def average_rating(self):
        """Mean of approved reviews, falling back to rating_cached (spec 6.4, 10.3)."""
        approved = self.reviews.filter(is_approved=True)
        count = approved.count()
        if not count:
            return self.rating_cached
        return round(sum(r.rating for r in approved) / count, 2)


class ProductColor(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="colors")
    name = models.CharField(max_length=50)
    hex_value = models.CharField(max_length=7, help_text="e.g. #1A1A1A")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class ProductSize(models.Model):
    """Accessories only — used by jackets, helmets (spec 8.2; BR-CAT-05)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="sizes")
    label = models.CharField(max_length=20, help_text='e.g. "M", "42"')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.product.name} - {self.label}"

    def clean(self):
        if self.product_id and self.product.product_type != ProductType.ACCESSORY:
            raise ValidationError("Sizes may only be defined for accessories (BR-CAT-05).")


class VariantGroup(models.Model):
    """Motorcycles only — Battery, Suspension, Wheels (spec 8.1; BR-CAT-05)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variant_groups")
    name = models.CharField(max_length=50, help_text="e.g. Battery, Suspension, Wheels")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    def clean(self):
        if self.product_id and self.product.product_type != ProductType.MOTORCYCLE:
            raise ValidationError("Variant groups may only be defined for motorcycles (BR-CAT-05).")

    def has_default_option(self):
        """BR-CAT-04: each variant group requires at least one default option."""
        return self.options.filter(is_default=True).exists()


class VariantOption(models.Model):
    variant_group = models.ForeignKey(VariantGroup, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=100)
    price_delta = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_default = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        from catalog.templatetags.catalog_extras import arko_price

        delta = f"+{arko_price(self.price_delta)}" if self.price_delta else "Included"
        return f"{self.variant_group.name}: {self.label} ({delta})"


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.product.name} image #{self.sort_order}"


class ProductSpec(models.Model):
    """Key/value technical attributes: range, power, weight, top speed, battery, charge time, etc."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="specs")
    key = models.CharField(max_length=100)
    value = models.CharField(max_length=200)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "key"], name="unique_spec_key_per_product"),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.key}: {self.value}"


class RelatedProduct(models.Model):
    """Self-referencing 'Related Models' cross-sell — motorcycles only (spec 8.1/8.2)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="related_to")
    related_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="related_from")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["product", "related_product"], name="unique_related_product_pair"),
        ]

    def clean(self):
        if self.product_id == self.related_product_id:
            raise ValidationError("A product cannot be related to itself.")

    def __str__(self):
        return f"{self.product.name} -> {self.related_product.name}"


class RecommendedAccessory(models.Model):
    """
    Motorcycle -> Accessory cross-sell. Drives Configurator step 6 ("a
    multi-select list of the accessories recommended for the selected model
    specifically") and product-detail "You May Also Need" (spec 6.5, 8.1).
    """

    motorcycle = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="recommended_accessories")
    accessory = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="recommended_for_motorcycles")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["motorcycle", "accessory"], name="unique_recommended_accessory_pair"),
        ]

    def clean(self):
        if self.motorcycle_id and self.motorcycle.product_type != ProductType.MOTORCYCLE:
            raise ValidationError({"motorcycle": "Must be a motorcycle."})
        if self.accessory_id and self.accessory.product_type != ProductType.ACCESSORY:
            raise ValidationError({"accessory": "Must be an accessory."})

    def __str__(self):
        return f"{self.motorcycle.name} -> {self.accessory.name}"


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews"
    )
    author_name = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=150)
    body = models.TextField()
    is_approved = models.BooleanField(default=True)
    is_verified_purchase = models.BooleanField(
        default=False, help_text="Set true when the reviewer actually purchased this product (spec 15.1)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if not (1 <= self.rating <= 5):
            raise ValidationError({"rating": "Rating must be an integer between 1 and 5."})

    def __str__(self):
        return f"{self.product.name} - {self.rating} stars by {self.author_name}"


class Wishlist(models.Model):
    """
    TODO.md "Major" fix: Wishlist previously had no backing model at all
    (product IDs came only from a `?ids=` querystring). This mirrors
    cart.models.Cart's own guest-session-vs-account pattern exactly
    (BR-CART-02) so functional spec 3.2's "session-scoped for a guest,
    account-persisted for a registered customer" requirement actually
    holds for Wishlist too. On login, the guest session wishlist is
    merged into the account wishlist — see catalog/signals.py, mirroring
    cart.signals' guest-cart merge (BR-CART-03).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="wishlist"
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session_key"],
                condition=models.Q(user__isnull=True),
                name="unique_guest_wishlist_session",
            ),
        ]

    def __str__(self):
        return f"Wishlist #{self.pk} ({self.user or self.session_key})"

    def clean(self):
        if not self.user_id and not self.session_key:
            raise ValidationError("A wishlist must belong to either a user or a guest session.")

    @property
    def product_ids(self):
        return list(self.items.values_list("product_id", flat=True))


class WishlistItem(models.Model):
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-added_at"]
        constraints = [
            models.UniqueConstraint(fields=["wishlist", "product"], name="unique_wishlist_line"),
        ]

    def __str__(self):
        return f"{self.product.name} in wishlist #{self.wishlist_id}"


class Compare(models.Model):
    """
    TODO.md "Major" fix, same pattern as Wishlist above. Spec 6.6 caps a
    compare list at 4 motorcycles; that cap is enforced where items are
    added (catalog.views.compare_toggle_view), not here, so a bulk import
    or admin edit isn't blocked by a business-rule constraint at the DB
    layer.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="compare"
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Compares"
        constraints = [
            models.UniqueConstraint(
                fields=["session_key"],
                condition=models.Q(user__isnull=True),
                name="unique_guest_compare_session",
            ),
        ]

    def __str__(self):
        return f"Compare #{self.pk} ({self.user or self.session_key})"

    def clean(self):
        if not self.user_id and not self.session_key:
            raise ValidationError("A compare list must belong to either a user or a guest session.")

    @property
    def product_ids(self):
        return list(self.items.values_list("product_id", flat=True))


class CompareItem(models.Model):
    compare = models.ForeignKey(Compare, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="compared_by")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at"]  # insertion order is the compare slot order
        constraints = [
            models.UniqueConstraint(fields=["compare", "product"], name="unique_compare_line"),
        ]

    def clean(self):
        if self.product_id and self.product.product_type != ProductType.MOTORCYCLE:
            raise ValidationError("Only motorcycles can be added to Compare (spec 6.6).")

    def __str__(self):
        return f"{self.product.name} in compare #{self.compare_id}"
