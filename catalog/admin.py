"""
catalog.admin

Spec's Catalog management admin section (products, categories, variants,
stock, media) plus review moderation (`Review.is_approved`). `ProductAdmin`
gates activation on BR-CAT-06 via `catalog.utils.get_publish_blockers` (that
function's own docstring: "Intended for the Forms/Admin phase to gate
activating a Product") and only shows the Sizes / Variant-Groups /
Recommended-Accessories inlines for the product type each actually applies
to (BR-CAT-05).

True nested inlines (options within a variant group, right inside the
Product page) aren't supported by stock Django admin, so `VariantOption` is
managed from the separately registered `VariantGroupAdmin` instead — the
standard two-level pattern for this kind of relation.
"""

from django.contrib import admin, messages
from import_export.admin import ImportExportModelAdmin

from .models import (
    AvailabilityStatus,
    Category,
    Compare,
    CompareItem,
    Product,
    ProductColor,
    ProductImage,
    ProductSize,
    ProductSpec,
    ProductType,
    RecommendedAccessory,
    RelatedProduct,
    Review,
    VariantGroup,
    VariantOption,
    Wishlist,
    WishlistItem,
)
from .resources import CategoryResource, ProductResource
from .utils import get_publish_blockers


@admin.register(Category)
class CategoryAdmin(ImportExportModelAdmin):
    resource_class = CategoryResource
    list_display = ("name", "product_type", "is_active")
    list_filter = ("product_type", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class ProductColorInline(admin.TabularInline):
    model = ProductColor
    extra = 1


class ProductSizeInline(admin.TabularInline):
    model = ProductSize
    extra = 1


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "sort_order")


class ProductSpecInline(admin.TabularInline):
    model = ProductSpec
    extra = 1


class VariantGroupInline(admin.TabularInline):
    model = VariantGroup
    extra = 1
    fields = ("name", "sort_order")
    show_change_link = True  # options themselves are managed from VariantGroupAdmin


class RelatedProductInline(admin.TabularInline):
    model = RelatedProduct
    fk_name = "product"
    extra = 1
    autocomplete_fields = ("related_product",)


class RecommendedAccessoryInline(admin.TabularInline):
    model = RecommendedAccessory
    fk_name = "motorcycle"
    extra = 1
    autocomplete_fields = ("accessory",)


@admin.register(Product)
class ProductAdmin(ImportExportModelAdmin):
    resource_class = ProductResource
    list_display = (
        "name", "product_type", "category", "price", "stock_quantity",
        "availability_status", "badge", "is_active",
    )
    list_filter = ("product_type", "category", "badge", "is_active", "is_pre_order")
    list_editable = ("price", "stock_quantity", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category",)
    readonly_fields = ("rating_cached", "review_count_cached", "created_at", "updated_at")
    common_inlines = [ProductColorInline, ProductImageInline, ProductSpecInline, RelatedProductInline]

    @admin.display(description="Availability")
    def availability_status(self, obj):
        return AvailabilityStatus(obj.availability_status).label

    def get_inline_instances(self, request, obj=None):
        """BR-CAT-05: Sizes are accessory-only, Variant Groups and Recommended
        Accessories are motorcycle-only. Both show on the add form (product
        type isn't chosen yet) and are filtered once a type is set."""
        inline_classes = list(self.common_inlines)
        if obj is None or obj.product_type == ProductType.ACCESSORY:
            inline_classes.append(ProductSizeInline)
        if obj is None or obj.product_type == ProductType.MOTORCYCLE:
            inline_classes += [VariantGroupInline, RecommendedAccessoryInline]
        return [cls(self.model, self.admin_site) for cls in inline_classes]

    def save_related(self, request, form, formsets, change):
        """
        BR-CAT-06 gate, run after the product's inlines (images included)
        are saved — checking "at least one image" earlier, during the main
        form's own clean(), would run before the image inline formset has
        been saved and always fail. If activation isn't yet earned, the
        product is quietly kept inactive instead of blocking the save.
        """
        super().save_related(request, form, formsets, change)
        product = form.instance
        if product.is_active:
            blockers = get_publish_blockers(product)
            if blockers:
                Product.objects.filter(pk=product.pk).update(is_active=False)
                self.message_user(
                    request,
                    "Kept inactive — publishing requires: " + " ".join(blockers),
                    level=messages.WARNING,
                )


@admin.register(VariantGroup)
class VariantGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "sort_order", "has_default_option")
    list_filter = ("product__product_type",)
    search_fields = ("name", "product__name")
    autocomplete_fields = ("product",)

    class VariantOptionInline(admin.TabularInline):
        model = VariantOption
        extra = 1

    inlines = [VariantOptionInline]

    @admin.display(boolean=True, description="Has default option")
    def has_default_option(self, obj):
        return obj.has_default_option()


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "author_name", "rating", "is_approved", "is_verified_purchase", "created_at")
    list_filter = ("is_approved", "is_verified_purchase", "rating")
    list_editable = ("is_approved",)
    search_fields = ("author_name", "title", "body", "product__name")
    autocomplete_fields = ("product", "user")
    readonly_fields = ("created_at",)


# TODO.md "Major" fix: Wishlist/Compare are now real, persisted collections
# (see models.py) — read-mostly admin, same rationale as cart.admin.CartAdmin
# (helpful for support/debugging what a customer has saved, not a record
# anyone authors by hand).
class WishlistItemInline(admin.TabularInline):
    model = WishlistItem
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "item_count", "updated_at")
    search_fields = ("user__username", "user__email", "session_key")
    readonly_fields = ("created_at", "updated_at")
    inlines = [WishlistItemInline]

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()


class CompareItemInline(admin.TabularInline):
    model = CompareItem
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(Compare)
class CompareAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "item_count", "updated_at")
    search_fields = ("user__username", "user__email", "session_key")
    readonly_fields = ("created_at", "updated_at")
    inlines = [CompareItemInline]

    @admin.display(description="Items")
    def item_count(self, obj):
        return obj.items.count()
