"""
orders.templatetags.orders_extras

Djangofication brief rule 4 ("never duplicate rounding/formatting logic per
template") applied to order-line option display.

Five orders-app templates render a purchased line together with its selected
options: Checkout Review, Order Success, Order Detail, Order Tracking, and
the printable Invoice. Those templates must produce *identical* option markup
even though they are not all fed the same object:

  - Checkout Review runs before the order exists, so it iterates live
    `cart.CartItem`s (`selected_color` / `selected_upgrades` fields).
  - Every page after Place Order iterates `orders.OrderItem`s, whose options
    live in the flattened `selected_options_snapshot` JSON written once at
    checkout (BR-ORD-01).

Rather than let the Review page drift from the post-order pages, this one
filter accepts either shape and normalises it. It mirrors
`cart.views._option_rows()` exactly (that helper stays as-is, still serving
the already-verified cart page) — same rows, same order, same Decimal
pre-parse of each upgrade's `price_delta`. Currency formatting is still done
in the template by the shared `arko_price` filter; this only decides *which*
rows exist.

Note, matching `cart._option_rows` rather than re-deriving new behavior: a
selected *size* is stored but never rendered as its own row, exactly as the
cart page does not render one today.
"""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def _to_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


@register.filter
def option_rows(item):
    """Yield [{label, price}] for an OrderItem *or* a CartItem."""
    if hasattr(item, "selected_options_snapshot"):
        opts = item.selected_options_snapshot or {}
        color = opts.get("color")
        upgrades = opts.get("upgrades") or []
    else:
        color = getattr(item, "selected_color", None)
        upgrades = getattr(item, "selected_upgrades", None) or []

    rows = []
    if color:
        rows.append({"label": f"Color: {color}", "price": None})
    for upgrade in upgrades:
        price = _to_decimal(upgrade.get("price_delta", 0))
        rows.append({"label": upgrade.get("option", ""), "price": price or None})
    return rows
