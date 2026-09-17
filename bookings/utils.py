"""
bookings.utils
"""

import calendar
from datetime import date

from .models import BookingStatus, ServiceTierName

# BR-BK-05: the spec names the three tiers but doesn't pin an exact
# maintenance interval per tier, so this encodes ARKO's schedule as a
# business-configurable default, keyed by tier name.
SERVICE_INTERVAL_MONTHS = {
    ServiceTierName.ROUTINE_CHECK: 6,
    ServiceTierName.BATTERY_SERVICE: 12,
    ServiceTierName.MAJOR_SERVICE: 24,
}
DEFAULT_SERVICE_INTERVAL_MONTHS = 12


def add_months(source_date, months):
    """Calendar-correct month addition (handles year rollover and short months)."""
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_next_service_due(base_date, service_tier_name):
    """BR-BK-05: next service-due date, `base_date` plus the tier's interval."""
    months = SERVICE_INTERVAL_MONTHS.get(service_tier_name, DEFAULT_SERVICE_INTERVAL_MONTHS)
    return add_months(base_date, months)


def check_slot_conflict(model_cls, dealer, date_, time_slot, exclude_pk=None):
    """
    BR-BK-01/02: does `dealer` already have a REQUESTED or CONFIRMED
    booking at (date_, time_slot)? A hard DB constraint already blocks a
    second CONFIRMED booking for the same slot; this covers the
    REQUESTED-state conflict check the model docstrings defer to the
    view/form layer, for use by the Forms phase's booking forms.
    `model_cls` is TestRideBooking or ServiceBooking.
    """
    qs = model_cls.objects.filter(
        dealer=dealer,
        date=date_,
        time_slot=time_slot,
        status__in=[BookingStatus.REQUESTED, BookingStatus.CONFIRMED],
    )
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()
