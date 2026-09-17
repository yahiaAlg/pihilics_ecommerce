"""
bookings.templatetags.bookings_extras

The static service.html hardcodes one Boxicon per service-type card
(wrench / battery-charging / buildings). `ServiceTier` has no icon field, so
the icon has to be derived from the tier's enum value somewhere.

Per the djangofication brief's rule 3 -- presentation tokens keyed off a
model enum go through an *explicit* mapping, never a string transform -- this
is a literal dict, not a `|slugify` or a name-munge. `ServiceTierName` has
exactly three members and all three are covered; the `.get` fallback exists
only so an admin adding a fourth tier renders a neutral icon rather than an
empty `<i>` tag.
"""

from django import template

from bookings.models import ServiceTierName

register = template.Library()

SERVICE_TIER_ICONS = {
    ServiceTierName.ROUTINE_CHECK: "bx-wrench",
    ServiceTierName.BATTERY_SERVICE: "bx-battery-charging",
    ServiceTierName.MAJOR_SERVICE: "bx-buildings",
}


@register.filter
def service_tier_icon(tier):
    """Boxicons class for a ServiceTier, mirroring service.html's card icons."""
    return SERVICE_TIER_ICONS.get(tier.name, "bx-cog")


# ---------------------------------------------------------------------------
# Booking status badge classes
# ---------------------------------------------------------------------------
# FLAGGED GAP -- the djangofication brief states that BookingStatus values
# "already match their badge class names 1:1 ... a direct swap is correct
# there, confirm rather than re-derive." Confirming it returned the opposite
# result, so it is recorded here rather than acted on as given.
#
# `pages.css` lines 505-509 define exactly four badge modifiers, and all four
# are ORDER states: .delivered, .shipped, .processing, .cancelled. Grepping
# both frozen stylesheets for "requested", "confirmed" and "completed"
# returns nothing. Of BookingStatus's four values, only `cancelled` has a
# class -- and only by coincidental overlap with OrderStatus. A direct swap
# would therefore ship three of four booking badges completely unstyled
# (bare uppercase text, no background), which is the same failure mode the
# brief itself flagged for AvailabilityStatus.LOW_STOCK.
#
# DECISION (same remedy the brief recommended for LOW_STOCK -- reuse the
# nearest documented visual state rather than ship an unstyled badge, and
# via an explicit dict, never a string transform):
#
#   requested -> .processing  (warning amber: awaiting action, not yet acted on)
#   confirmed -> .shipped     (info blue: acknowledged and scheduled)
#   completed -> .delivered   (success green: terminal success state)
#   cancelled -> .cancelled   (direct match, the one genuine 1:1)
#
# This introduces no new CSS and no new color -- it reuses the four modifiers
# the design system already documents.

from bookings.models import BookingStatus  # noqa: E402

BOOKING_STATUS_BADGE_CLASSES = {
    BookingStatus.REQUESTED: "processing",
    BookingStatus.CONFIRMED: "shipped",
    BookingStatus.COMPLETED: "delivered",
    BookingStatus.CANCELLED: "cancelled",
}


@register.filter
def booking_status_class(status):
    """Map a BookingStatus value onto a documented .order-status-badge modifier."""
    return BOOKING_STATUS_BADGE_CLASSES.get(status, "processing")
