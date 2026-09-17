"""
catalog.templatetags.catalog_extras

Djangofication brief rule 4: "Star ratings, prices, and quantities render
through a shared template filter/inclusion tag ... never duplicate
rounding/formatting logic per template." These three mirror the static
build's own shared helpers (js/main.js's starRating()/formatPrice()) 1:1,
just implemented server-side.
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.inclusion_tag("catalog/_star_rating.html")
def star_rating(rating, size=None):
    """Mirrors js/main.js's starRating(rating, size) — nearest-star rounding, filled/empty bx-star icons."""
    try:
        rating = float(rating or 0)
    except (TypeError, ValueError):
        rating = 0.0
    full = round(rating)
    return {
        "stars": [{"filled": i <= full} for i in range(1, 6)],
        "size": size or ".85rem",
    }


# Symbols for the currencies CompanyInfo.default_currency is realistically
# set to. DZD has no universally-rendered glyph, so Algerian amounts are
# suffixed with "DA" -- the form actually used on Algerian price tags --
# rather than a symbol most fonts would drop.
_CURRENCY_FORMATS = {
    "DZD": ("", " DA"),
    "EUR": ("\u20ac", ""),
    "USD": ("$", ""),
    "GBP": ("\u00a3", ""),
}


def _currency_affixes():
    """Prefix/suffix for the brand's configured currency (CompanyInfo)."""
    from core.models import CompanyInfo

    code = (CompanyInfo.get_solo().default_currency or "DZD").upper()
    return _CURRENCY_FORMATS.get(code, ("", f" {code}"))


@register.filter
def arko_price(value):
    """
    Shared money formatter (djangofication brief rule 4). Thousands-separated,
    no decimals on whole amounts.

    The currency is no longer the hardcoded euro the static build assumed --
    it follows CompanyInfo.default_currency, so the same admin record that
    renames the business also sets how its prices read.
    """
    if value in (None, ""):
        return ""
    try:
        value = Decimal(value)
    except InvalidOperation:
        return ""
    prefix, suffix = _currency_affixes()
    if value == value.to_integral_value():
        return f"{prefix}{int(value):,}{suffix}"
    return f"{prefix}{value:,.2f}{suffix}"


# Alias: the filter is named after the old brand throughout the templates.
# Registering the brand-neutral name too lets new templates use `price`
# without a sweeping rename of the ~40 existing call sites.
register.filter("price", arko_price)


@register.filter
def get_spec(product, key):
    """
    Looks up a ProductSpec value by key (e.g. "Range", "Power") from a
    product's already-prefetched `specs` relation — no extra query per
    card. Returns "" when the product has no spec under that key (most
    accessories don't have "Range", for instance).
    """
    for spec in product.specs.all():
        if spec.key == key:
            return spec.value
    return ""


@register.filter
def dict_get(mapping, key):
    """Plain dict[key] lookup usable in a template where `key` is itself a variable (e.g. category_counts|dict_get:category.slug)."""
    try:
        return mapping.get(key, 0)
    except AttributeError:
        return 0
