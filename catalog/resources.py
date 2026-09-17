"""
catalog.resources

django-import-export Resources for bulk catalog import — the spec's one
named import-export use case ("django-import-export resources for catalog
bulk import"), which the Admin section (12.16) scopes to "products,
categories, variants, stock, media." `Category` is included alongside
`Product` because a Product import's `category` column can only resolve
against categories that already exist — importing categories first (or in
the same session) is how a real bulk catalog load would actually work.

`slug` is each model's natural business key (BR-CAT-01 for Product: unique,
URL-safe, immutable once ordered; Category.slug is unique the same way), so
it's what a re-import matches existing rows on; `Product.category` is
resolved by that same slug rather than by numeric id, since a
spreadsheet-driven import won't know Django's internal category ids.

Deliberately excluded from the importable field set: `rating_cached` and
`review_count_cached` (derived/cached, not editable business data — see
Product.average_rating) and `created_at`/`updated_at` (managed by Django).
Variant Groups/Options, Sizes, Colors, Images, and Specs aren't part of
either resource; they're one-to-many child rows managed through the
Product admin's inlines instead (see catalog.admin), matching Product and
Category being the two catalog rows a bulk spreadsheet import naturally
maps one row to.
"""

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from .models import Category, Product


class CategoryResource(resources.ModelResource):
    class Meta:
        model = Category
        import_id_fields = ("slug",)
        fields = export_order = ("slug", "name", "product_type", "is_active")
        skip_unchanged = True
        report_skipped = True
        clean_model_instances = True


class ProductResource(resources.ModelResource):
    category = fields.Field(
        column_name="category",
        attribute="category",
        widget=ForeignKeyWidget(Category, field="slug"),
    )

    class Meta:
        model = Product
        import_id_fields = ("slug",)
        fields = export_order = (
            "slug", "name", "product_type", "category",
            "price", "old_price", "description",
            "stock_quantity", "low_stock_threshold", "is_pre_order",
            "badge", "video_trailer_url", "is_active",
        )
        skip_unchanged = True
        report_skipped = True
        # Without this, django-import-export skips Model.full_clean() entirely
        # (its default), so a bulk import could silently violate Product.clean()
        # — e.g. give an accessory a video_trailer_url, or rewrite the slug of a
        # product that's already been ordered (BR-CAT-01).
        clean_model_instances = True
