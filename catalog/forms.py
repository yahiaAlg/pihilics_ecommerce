"""
catalog.forms

Spec 6.1 (Shop filters), 6.2 (Accessories filters), 6.19 (Search), and 6.4
(Reviews). These are plain `forms.Form` classes bound to GET query strings
(catalog listing/search is read-only filtering, not a state-changing
submission), except ReviewForm which is a real ModelForm — replacing the
prior prototype's "Write a Review... only shows a toast" no-op (spec 6.4,
11.3.13) with an actual, persisted Review (edge case 15.1: allowed even
from a non-purchasing customer, just recorded with `is_verified_purchase`
left False by the view).
"""

from django import forms

from .models import AvailabilityStatus, Category, ProductColor, ProductType, Review

MOTORCYCLE_SORT_CHOICES = [
    ("featured", "Featured"),
    ("price_asc", "Price: Low to High"),
    ("price_desc", "Price: High to Low"),
    ("top_rated", "Highest Rated"),
    ("longest_range", "Longest Range"),
]

ACCESSORY_SORT_CHOICES = [
    ("featured", "Featured"),
    ("price_asc", "Price: Low to High"),
    ("price_desc", "Price: High to Low"),
    ("top_rated", "Highest Rated"),
]

MIN_RANGE_CHOICES = [
    ("50", "50+ km"),
    ("100", "100+ km"),
    ("150", "150+ km"),
]

SEARCH_TYPE_CHOICES = [
    ("all", "All"),
    (ProductType.MOTORCYCLE, "Motorcycles"),
    (ProductType.ACCESSORY, "Accessories"),
]


class MotorcycleFilterForm(forms.Form):
    """
    Spec 6.1: category checkboxes, a price-cap slider (1,350,000-3,300,000 DA
    — the bounds live on the slider in catalog/shop.html, since they track the
    lineup's real price span rather than anything this form validates), a
    minimum-range radio group, an availability checkbox pair (both checked
    by default), dynamically-built color swatches, and a sort selector.
    All fields are optional — an empty form means "no filtering," matching
    "Clear All Filters" (spec 6.1 step 7).
    """

    category = forms.ModelMultipleChoiceField(
        queryset=Category.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True),
        required=False,
        to_field_name="slug",
    )
    max_price = forms.DecimalField(required=False, min_value=0)
    min_range_km = forms.ChoiceField(choices=MIN_RANGE_CHOICES, required=False)
    availability = forms.MultipleChoiceField(
        choices=[(AvailabilityStatus.IN_STOCK, "In Stock"), (AvailabilityStatus.PRE_ORDER, "Pre-Order")],
        required=False,
        initial=[AvailabilityStatus.IN_STOCK, AvailabilityStatus.PRE_ORDER],
    )
    color = forms.MultipleChoiceField(required=False)
    sort = forms.ChoiceField(choices=MOTORCYCLE_SORT_CHOICES, required=False, initial="featured")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Color swatches are "built dynamically from every color used across
        # the catalog" (spec 6.1 step 2) rather than a fixed choice list.
        color_names = (
            ProductColor.objects.filter(product__product_type=ProductType.MOTORCYCLE)
            .order_by("name")
            .values_list("name", flat=True)
            .distinct()
        )
        self.fields["color"].choices = [(name, name) for name in color_names]


class AccessoryFilterForm(forms.Form):
    """Spec 6.2: a smaller mirror of MotorcycleFilterForm — no Minimum Range or Color filter."""

    category = forms.ModelMultipleChoiceField(
        queryset=Category.objects.filter(product_type=ProductType.ACCESSORY, is_active=True),
        required=False,
        to_field_name="slug",
    )
    max_price = forms.DecimalField(required=False, min_value=0)
    in_stock_only = forms.BooleanField(required=False)
    sort = forms.ChoiceField(choices=ACCESSORY_SORT_CHOICES, required=False, initial="featured")


class SearchForm(forms.Form):
    """
    Spec 6.19: substring match against name/category/description, across
    both motorcycles and accessories, narrowable by product type.
    """

    q = forms.CharField(required=False, max_length=200, label="Search")
    type = forms.ChoiceField(choices=SEARCH_TYPE_CHOICES, required=False, initial="all")


class ReviewForm(forms.ModelForm):
    """
    Spec 6.4 "Write a Review": rating, title, and body. `product`,
    `author_name`/`user`, and `is_verified_purchase` are set by the view
    from the request context, not exposed here as editable fields.
    """

    rating = forms.TypedChoiceField(
        choices=[(i, f"{i} Star{'s' if i != 1 else ''}") for i in range(5, 0, -1)],
        coerce=int,
    )

    class Meta:
        model = Review
        fields = ["rating", "title", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}
