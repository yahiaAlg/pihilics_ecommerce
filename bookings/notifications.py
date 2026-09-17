"""
bookings.notifications

Test-ride and service-booking emails, sent via core.emails and triggered
from bookings/signals.py. Two events, shared across both booking types
since they share BookingStatus and the same dealer-queue approval flow:

- Booking received (REQUESTED, i.e. just created): one email to the
  customer, one to the admin inbox so staff know to act on the dealer
  queue (bookings:dealer_queue).
- Booking status changed (dealer staff confirming/cancelling/completing
  from the queue — bookings.views.booking_update_status_view is the only
  place either status field changes after creation): one email to the
  customer. "Ride test approval" is exactly the REQUESTED -> CONFIRMED
  transition here.

TestRideBooking and ServiceBooking have different contact-field names
(first_name/last_name/email/phone vs contact_first_name/... /
contact_email/contact_phone) but are otherwise interchangeable for
mailing purposes, so _describe() below normalizes both into one shape
the templates render from.
"""

from core.emails import send_admin_email, send_branded_email


def _describe(booking, booking_type):
    """Normalizes TestRideBooking/ServiceBooking's differing contact-field names into one shape."""
    if booking_type == "test_ride":
        first_name, last_name = booking.first_name, booking.last_name
        email, phone = booking.email, booking.phone
        label = "Test Ride"
    else:
        first_name, last_name = booking.contact_first_name, booking.contact_last_name
        email, phone = booking.contact_email, booking.contact_phone
        label = "Service Appointment"
    return {
        "booking": booking,
        "booking_type": booking_type,
        "booking_label": label,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
    }


def send_booking_received(booking, booking_type):
    """Fired once, when the booking is first created — see bookings/signals.py."""
    context = _describe(booking, booking_type)
    send_branded_email(
        to=context["email"],
        subject=f"{context['booking_label']} Received",
        template_name="booking_received_customer",
        context=context,
    )
    send_admin_email(
        subject=f"New {context['booking_label']} — {booking.dealer.name}",
        template_name="booking_received_admin",
        context=context,
        reply_to=context["email"],
    )


def send_booking_status_update(booking, booking_type):
    """Fired on every genuine status transition after creation — see bookings/signals.py."""
    context = _describe(booking, booking_type)
    send_branded_email(
        to=context["email"],
        subject=f"{context['booking_label']} — {booking.get_status_display()}",
        template_name="booking_status_update_customer",
        context=context,
    )
