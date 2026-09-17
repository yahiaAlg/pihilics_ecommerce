import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from catalog.video import VIDEO_FILE_EXTENSIONS, mime_type_for, parse_video_url

# An uploaded trailer is the largest thing an admin can put on this server,
# so the ceiling is explicit rather than left to whatever the web server
# happens to allow. 200 MB comfortably fits a two-minute 1080p product
# film; anything longer belongs on YouTube, which is why the URL field
# exists alongside this one.
PRODUCT_VIDEO_MAX_BYTES = 200 * 1024 * 1024
PRODUCT_VIDEO_CONTENT_TYPES = (
    "video/mp4", "video/webm", "video/ogg", "video/quicktime", "video/x-m4v",
)


def validate_product_video(upload):
    """
    Rejects anything a browser couldn't play, or anything oversized.

    Both the extension and the browser-supplied content type are checked,
    the same way payment proofs are (orders.models.validate_payment_proof):
    neither is trustworthy alone, but requiring both to land in a short
    allow-list stops the obvious case of an archive renamed to .mp4. This
    is an admin-only upload, so the threat model is mostly "someone picked
    the wrong file" rather than a real attacker -- the size ceiling is the
    part that earns its keep.
    """
    extension = os.path.splitext(upload.name)[1].lower()
    if extension not in VIDEO_FILE_EXTENSIONS:
        raise ValidationError(
            "Upload a video file (%(allowed)s). “%(ext)s” files aren't accepted.",
            params={"allowed": ", ".join(VIDEO_FILE_EXTENSIONS), "ext": extension or "unknown"},
        )

    content_type = getattr(upload, "content_type", None)
    if content_type and content_type not in PRODUCT_VIDEO_CONTENT_TYPES:
        raise ValidationError("That file doesn't look like a video.")

    if upload.size and upload.size > PRODUCT_VIDEO_MAX_BYTES:
        raise ValidationError(
            "That file is %(size).0f MB. Product videos must be under %(limit)s MB — "
            "for anything longer, paste a YouTube or Vimeo link instead.",
            params={
                "size": upload.size / (1024 * 1024),
                "limit": PRODUCT_VIDEO_MAX_BYTES // (1024 * 1024),
            },
        )


def product_video_upload_to(instance, filename):
    """media/products/video/<slug>/<filename> — one folder per product, so
    replacing a trailer doesn't leave the old one anonymous in a flat
    directory."""
    return f"products/video/{instance.slug or 'unsorted'}/{filename}"


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

    # -- Optional product video (motorcycles only, spec 8.2) --------------
    #
    # Two fields, one feature, because there are two genuinely different
    # ways a shop ends up with a product film: it's already on YouTube or
    # Vimeo (paste the link), or it's a file someone was handed and has
    # nowhere to host (upload it). Supporting only the URL would force
    # every video onto a third-party account; supporting only the upload
    # would put avoidable megabytes through this server for videos that
    # are already hosted perfectly well elsewhere.
    #
    # If both are filled in the uploaded file wins -- see `video_source`.
    # That is a deliberate choice rather than a validation error: the
    # realistic sequence is "we had a link, now we have the real file",
    # and making the admin clear one field before filling the other adds
    # a step for no benefit.
    video_trailer_url = models.URLField(
        blank=True,
        verbose_name="Video link (YouTube / Vimeo)",
        help_text="Motorcycles only. Paste a YouTube, Vimeo, or direct video-file link. "
                  "Watch, youtu.be, Shorts and embed forms are all accepted. "
                  "Ignored if a video file is uploaded below.",
    )
    video_file = models.FileField(
        upload_to=product_video_upload_to,
        blank=True,
        validators=[validate_product_video],
        verbose_name="Video file (upload)",
        help_text=f"Motorcycles only. Optional. MP4 or WebM, under "
                  f"{PRODUCT_VIDEO_MAX_BYTES // (1024 * 1024)} MB. Takes precedence over the link above.",
    )
    video_poster = models.ImageField(
        upload_to="products/video/posters/",
        blank=True,
        help_text="Optional still shown before an uploaded video plays. "
                  "Falls back to the product's first photo. Not used for YouTube/Vimeo, "
                  "which supply their own thumbnail.",
    )

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
        if self.product_type == ProductType.ACCESSORY and self.video_file:
            raise ValidationError({"video_file": "Only motorcycles may have a video trailer (spec 8.2)."})

        # Caught here rather than left to render as an empty box on the
        # product page: a channel URL, a playlist, or a link to a page that
        # merely *contains* a video all look fine pasted into a text input
        # and all produce nothing at all in an iframe. The admin finds out
        # at save time instead of a customer finding out later.
        if self.video_trailer_url and not parse_video_url(self.video_trailer_url)[0]:
            raise ValidationError({
                "video_trailer_url":
                    "That link isn't a video we can embed. Use a YouTube or Vimeo video URL, "
                    "or a direct link to a video file (" + ", ".join(VIDEO_FILE_EXTENSIONS) + ").",
            })
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
    def video_source(self):
        """
        Everything the template needs to render this product's video, or
        None when there isn't one.

        Returns a dict with `kind` ("file", "youtube" or "vimeo"), `url`
        (a src for <video> / <iframe>), `mime` (for a <video><source>) and
        `poster`. One property rather than three or four separate ones so
        the template branches once, and so "which wins when both fields
        are set" is answered here instead of in template logic.
        """
        if not self.is_motorcycle:
            return None

        if self.video_file:
            first_image = self.images.first()
            poster = self.video_poster.url if self.video_poster else (
                first_image.image.url if first_image else ""
            )
            return {
                "kind": "file",
                "url": self.video_file.url,
                "mime": mime_type_for(self.video_file.name),
                "poster": poster,
            }

        kind, url = parse_video_url(self.video_trailer_url)
        if not kind:
            return None
        if kind == "file":
            return {"kind": "file", "url": url, "mime": mime_type_for(url), "poster": ""}
        return {"kind": kind, "url": url, "mime": "", "poster": ""}

    @property
    def has_video(self):
        return self.video_source is not None

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
