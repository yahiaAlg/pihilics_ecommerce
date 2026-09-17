"""
cart.forms

Spec 6.8 (Add to Cart / Cart page) and 7.3 (Promo codes). AddToCartForm is
shared by every add-to-cart entry point (product card, product detail page,
Configurator, Quick View — spec 6.8 "Entry points") since they all supply
the same shape: a product, a quantity, and an options object.
"""

from django import forms

from catalog.models import Product, ProductType, VariantOption

from .models import PromoCode


class AddToCartForm(forms.Form):
    """
    BR-CART-01: a line's identity is (product, color, size, sorted
    upgrades). `upgrades` accepts one VariantOption per variant group (a
    motorcycle's Battery/Suspension/Wheels selections, spec 6.3/6.5); at
    most one option per group may be selected. `get_selected_upgrades()`
    converts the cleaned queryset into the {variant_group, option,
    price_delta} shape cart.utils.add_item_to_cart expects.
    """

    product_id = forms.IntegerField(widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=1, initial=1)
    color = forms.CharField(required=False, max_length=50)
    size = forms.CharField(required=False, max_length=20)
    upgrades = forms.ModelMultipleChoiceField(
        queryset=VariantOption.objects.none(), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._product = None

    def clean_product_id(self):
        product_id = self.cleaned_data["product_id"]
        try:
            product = Product.objects.get(pk=product_id, is_active=True)
        except Product.DoesNotExist:
            raise forms.ValidationError("This product is no longer available.")
        self._product = product
        self.fields["upgrades"].queryset = VariantOption.objects.filter(
            variant_group__product=product
        )
        return product_id

    def clean(self):
        cleaned_data = super().clean()
        product = self._product
        if product is None:
            return cleaned_data

        quantity = cleaned_data.get("quantity")
        if quantity and not product.is_pre_order and quantity > product.stock_quantity:
            self.add_error(
                "quantity", f"Only {product.stock_quantity} left of \"{product.name}\"."
            )

        color = cleaned_data.get("color")
        available_colors = set(product.colors.values_list("name", flat=True))
        if available_colors:
            if not color:
                self.add_error("color", "Please select a color.")
            elif color not in available_colors:
                self.add_error("color", "Not a valid color for this product.")

        size = cleaned_data.get("size")
        if product.product_type == ProductType.ACCESSORY:
            available_sizes = set(product.sizes.values_list("label", flat=True))
            if available_sizes:
                if not size:
                    self.add_error("size", "Please select a size.")
                elif size not in available_sizes:
                    self.add_error("size", "Not a valid size for this product.")
        elif size:
            self.add_error("size", "Sizes only apply to accessories (BR-CAT-05).")

        upgrades = cleaned_data.get("upgrades")
        if upgrades:
            seen_groups = set()
            for option in upgrades:
                if option.variant_group_id in seen_groups:
                    self.add_error(
                        "upgrades",
                        f'Only one option may be selected per variant group ("{option.variant_group.name}").',
                    )
                    break
                seen_groups.add(option.variant_group_id)

        return cleaned_data

    def get_selected_upgrades(self):
        """
        Serializes the cleaned `upgrades` queryset into cart.CartItem's
        selected_upgrades shape. `price_delta` is cast to `str()` because
        this dict is stored straight into a plain (unencoded) JSONField —
        a raw Decimal is not JSON-serializable and would raise
        `TypeError: Object of type Decimal is not JSON serializable` the
        moment this reaches CartItem.compute_options_key()/save(). See
        CartItem.unit_price, which parses it back into a Decimal on read.
        """
        return [
            {
                "variant_group": option.variant_group.name,
                "option": option.label,
                "price_delta": str(option.price_delta),
            }
            for option in self.cleaned_data.get("upgrades", [])
        ]

    def get_product(self):
        """Available after a successful clean(); the Product resolved from product_id."""
        return self._product


class CartItemUpdateForm(forms.Form):
    """Spec 6.8: the cart line's quantity stepper (floor of 1 — BR-CART-05)."""

    quantity = forms.IntegerField(min_value=1)


class PromoCodeForm(forms.Form):
    """
    Spec 7.3: the Cart page's promo-code input. A light existence/validity
    check happens here for immediate feedback ("Invalid promo code" toast);
    the authoritative check at order-placement time is
    orders.utils.calculate_discount / PromoCode.is_valid_for (BR-CHK-05),
    since a code can expire between the two moments (edge case 15.1).
    """

    code = forms.CharField(max_length=30)

    def __init__(self, *args, cart=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._cart = cart
        self._promo_code = None

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        try:
            promo_code = PromoCode.objects.get(code=code)
        except PromoCode.DoesNotExist:
            raise forms.ValidationError("Invalid promo code.")

        subtotal = self._cart.subtotal if self._cart is not None else 0
        if not promo_code.is_valid_for(subtotal):
            raise forms.ValidationError("Invalid promo code.")

        self._promo_code = promo_code
        return code

    def get_promo_code(self):
        return self._promo_code
