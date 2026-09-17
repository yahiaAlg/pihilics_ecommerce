"""
orders.utils

Checkout/order-placement business logic (BR-CHK-*, BR-ORD-*). Kept out of
the future checkout view so the pricing formula and order-creation
sequence have exactly one implementation, used both to preview totals and
to actually place the order.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.db import transaction

from core.utils import get_shipping_cost, get_vat_rate

from .models import DeliveryMethod, Order, OrderItem


@dataclass
class CheckoutIssue:
    cart_item_id: int
    product_name: str
    issue_type: str  # "inactive" | "out_of_stock" | "price_changed"
    message: str


class CheckoutValidationError(Exception):
    """Raised by create_order_from_cart when BR-CHK-01 revalidation finds a problem."""

    def __init__(self, issues):
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


def calculate_shipping_cost(subtotal, delivery_method, destination_wilaya=None):
    """
    BR-CHK-02, now wilaya-priced: free above the threshold, otherwise the
    destination wilaya's own fee (core.utils.get_shipping_cost reads the
    ShippingZone table and falls back to the flat constant when that wilaya
    has no row); Express adds its surcharge on top.
    """
    return get_shipping_cost(
        subtotal=subtotal,
        delivery_method=delivery_method,
        wilaya_code=destination_wilaya,
    )


def calculate_discount(subtotal, promo_code, at=None):
    """BR-CHK-05: only applied while the promo code is active, in-window, and subtotal meets its minimum."""
    if promo_code is None or not promo_code.is_valid_for(subtotal, at=at):
        return Decimal("0.00")
    return (subtotal * promo_code.discount_percent / Decimal("100")).quantize(Decimal("0.01"))


def build_order_pricing(*, subtotal, promo_code, delivery_method, destination_wilaya):
    """BR-CHK-04/06: TVA on (subtotal − discount); Order Total = Subtotal − Discount + Shipping + TVA."""
    discount_amount = calculate_discount(subtotal, promo_code)
    shipping_cost = calculate_shipping_cost(subtotal, delivery_method, destination_wilaya)
    vat_rate = get_vat_rate(destination_wilaya)
    vat_amount = ((subtotal - discount_amount) * vat_rate / Decimal("100")).quantize(Decimal("0.01"))
    total = subtotal - discount_amount + shipping_cost + vat_amount
    return {
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "shipping_cost": shipping_cost,
        "vat_amount": vat_amount,
        "total": total,
    }


def validate_cart_for_checkout(cart, expected_prices: Optional[dict] = None):
    """
    BR-CHK-01: re-validate every line's stock and current price server-side
    immediately before charging. Stock sufficiency and active status are
    always checked; `expected_prices` (an optional {cart_item_id: Decimal}
    map — e.g. captured from a hidden field when the Review step rendered)
    lets the checkout view additionally catch a price change during that
    window. Returns a list of CheckoutIssue; an empty list means the cart
    is safe to charge as-is.
    """
    expected_prices = expected_prices or {}
    issues = []

    for item in cart.items.select_related("product"):
        product = item.product

        if not product.is_active:
            issues.append(CheckoutIssue(item.id, product.name, "inactive", f'"{product.name}" is no longer available.'))
            continue

        if not product.is_pre_order and product.stock_quantity < item.quantity:
            issues.append(CheckoutIssue(
                item.id, product.name, "out_of_stock",
                f'Only {product.stock_quantity} left of "{product.name}" — please update the quantity.',
            ))

        expected = expected_prices.get(item.id)
        if expected is not None and Decimal(expected) != item.unit_price:
            issues.append(CheckoutIssue(
                item.id, product.name, "price_changed",
                f'The price of "{product.name}" has changed since it was added to your cart.',
            ))

    return issues


def create_order_from_cart(
    cart, *,
    user=None, guest_email="", guest_name="", guest_phone="",
    contact_first_name, contact_last_name, contact_email, contact_phone,
    delivery_street, delivery_city, delivery_postal_code, delivery_wilaya,
    delivery_method=DeliveryMethod.STANDARD,
    payment_method, save_payment_method=True,
    promo_code=None, financing_plan=None, insurance_tier=None,
    expected_prices=None,
):
    """
    Turns a validated Cart into a placed Order (BR-CHK-01/06/07,
    BR-ORD-01/02/06). Raises CheckoutValidationError — charging and
    creating nothing — if revalidation finds a stock/availability/price
    problem. On success, each OrderItem is created as a write-once
    snapshot of its cart line (BR-ORD-01), which in turn fires the
    stock-decrement / GarageEntry signals (BR-ORD-03/05); the cart is then
    cleared, since "the cart is cleared automatically the moment an order
    is placed in Checkout."

    BR-CHK-08: `financing_plan` / `insurance_tier` are attached to the
    Order as-is; neither alters the computed total here, since the spec
    ties any total impact to an explicit price on the plan/tier itself,
    which isn't modeled as a checkout-time charge.
    """
    issues = validate_cart_for_checkout(cart, expected_prices=expected_prices)
    if issues:
        raise CheckoutValidationError(issues)

    with transaction.atomic():
        subtotal = cart.subtotal
        pricing = build_order_pricing(
            subtotal=subtotal,
            promo_code=promo_code,
            delivery_method=delivery_method,
            destination_wilaya=delivery_wilaya,
        )

        order = Order.objects.create(
            user=user,
            guest_email=guest_email, guest_name=guest_name, guest_phone=guest_phone,
            contact_first_name=contact_first_name, contact_last_name=contact_last_name,
            contact_email=contact_email, contact_phone=contact_phone,
            delivery_street=delivery_street, delivery_city=delivery_city,
            delivery_postal_code=delivery_postal_code, delivery_wilaya=delivery_wilaya,
            delivery_method=delivery_method,
            payment_method=payment_method, save_payment_method=save_payment_method,
            subtotal=pricing["subtotal"], shipping_cost=pricing["shipping_cost"],
            vat_amount=pricing["vat_amount"], discount_amount=pricing["discount_amount"],
            total=pricing["total"],
            promo_code=promo_code, financing_plan=financing_plan, insurance_tier=insurance_tier,
        )

        for line in cart.items.select_related("product"):
            OrderItem.objects.create(
                order=order,
                product=line.product,
                product_name_snapshot=line.product.name,
                unit_price_snapshot=line.unit_price,
                quantity=line.quantity,
                selected_options_snapshot={
                    "color": line.selected_color,
                    "size": line.selected_size,
                    "upgrades": line.selected_upgrades,
                },
            )

        cart.items.all().delete()

    return order
