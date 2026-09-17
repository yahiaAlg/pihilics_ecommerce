"""
core.utils

Helpers built on the core app's own models (CompanyInfo, CheckoutSettings,
VATRate, ShippingZone).
"""

from decimal import Decimal

from .models import CheckoutSettings, CompanyInfo, ShippingZone, VATRate


def get_vat_rate(wilaya_code):
    """
    BR-CHK-04: TVA is calculated using the rate for the selected shipping
    destination. Looks up an active VATRate row for `wilaya_code`; falls
    back to CompanyInfo.default_vat_rate when the destination has no
    explicit row -- which is the normal case, since Algeria applies one
    national rate (see the VATRate docstring).
    """
    rate = (
        VATRate.objects.filter(wilaya=wilaya_code, is_active=True)
        .values_list("rate_percent", flat=True)
        .first()
    )
    if rate is not None:
        return rate
    return CompanyInfo.get_solo().default_vat_rate


def get_shipping_zone(wilaya_code):
    """The active ShippingZone row for a wilaya, or None if it has no row."""
    return ShippingZone.objects.filter(wilaya=wilaya_code, is_active=True).first()


def get_shipping_cost(*, subtotal, delivery_method, wilaya_code):
    """
    BR-CHK-02, re-based on wilayas.

    Free above CheckoutSettings.free_shipping_threshold; otherwise the
    destination wilaya's own home-delivery fee (ShippingZone), falling back
    to CheckoutSettings.standard_shipping_fee when that wilaya has no row
    configured yet. Express adds its surcharge on top of that determination
    -- it never replaces it, and it is never added to an order that already
    ships free.

    All three figures come from the CheckoutSettings singleton rather than
    module constants, so re-pricing delivery is an admin edit.
    """
    settings_row = CheckoutSettings.get_safe()

    if subtotal >= settings_row.free_shipping_threshold:
        return Decimal("0.00")

    zone = get_shipping_zone(wilaya_code)
    base = zone.home_fee if zone else settings_row.standard_shipping_fee

    if delivery_method == "express":
        base += settings_row.express_shipping_surcharge
    return Decimal(base).quantize(Decimal("0.01"))
