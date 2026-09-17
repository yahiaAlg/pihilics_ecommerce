"""
bookings.views

Spec 6.12 (Test Ride), 6.13 (Service), and the Dealer & Booking Module's
dealer-side booking queue (requirements doc Chapter 4 "In Scope"; BR-BK-03
"visible immediately in the assigned dealer's booking queue", BR-BK-04
"only Dealer Staff assigned to that specific dealer... may confirm,
reschedule, cancel, or complete").
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import UserRole

from .forms import ServiceBookingForm, TestRideBookingForm
from .models import BookingStatus, ServiceBooking, TestRideBooking


def test_ride_view(request):
    """Spec 6.12."""
    initial = {}
    if request.user.is_authenticated:
        initial = {
            "first_name": request.user.first_name, "last_name": request.user.last_name,
            "email": request.user.email, "phone": request.user.profile.phone,
        }
    product_slug = request.GET.get("product")

    if request.method == "POST":
        form = TestRideBookingForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            if request.user.is_authenticated:
                booking.user = request.user
            booking.save()
            _grant_booking_access(request, "test_ride", booking.pk)
            messages.success(request, "Your test ride request has been sent — the dealer will confirm shortly.")
            return redirect("bookings:test_ride_confirmation", pk=booking.pk)
    else:
        if product_slug:
            initial["product"] = TestRideBookingForm().fields["product"].queryset.filter(slug=product_slug).first()
        form = TestRideBookingForm(initial=initial)

    return render(request, "bookings/test_ride.html", {"form": form})


BOOKING_ACCESS_SESSION_KEY = "accessible_bookings"


def _grant_booking_access(request, booking_type, pk):
    """Remember that this session just created this booking, so its own
    confirmation page is viewable afterwards (mirrors orders' guest-access
    pattern)."""
    granted = request.session.setdefault(BOOKING_ACCESS_SESSION_KEY, [])
    token = f"{booking_type}:{pk}"
    if token not in granted:
        granted.append(token)
        request.session.modified = True


def _can_access_booking(request, booking_type, booking):
    """
    SECURITY FIX (found while converting the confirmation pages): both
    confirmation views previously did a bare `get_object_or_404(Model, pk=pk)`
    with no ownership check at all, so /bookings/service/3/confirmation/
    exposed a stranger's full name, email, phone -- and, for test rides, their
    motorcycle licence number -- to anyone who incremented the pk. That
    violates the brief's "never render another user's data if the session
    happens to overlap" rule. Access is now: the booking's own user, or the
    session that created it (covering guests, who may book without an
    account), or that dealer's own staff (BR-BK-04).
    """
    if request.user.is_authenticated and booking.user_id == request.user.id:
        return True
    if f"{booking_type}:{booking.pk}" in request.session.get(BOOKING_ACCESS_SESSION_KEY, []):
        return True
    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        if profile and profile.role == UserRole.DEALER_STAFF and profile.dealer_id == booking.dealer_id:
            return True
    return False


def test_ride_confirmation_view(request, pk):
    booking = get_object_or_404(TestRideBooking, pk=pk)
    if not _can_access_booking(request, "test_ride", booking):
        raise PermissionDenied
    return render(request, "bookings/test_ride_confirmation.html", {"booking": booking})


def service_booking_view(request):
    """
    Spec 6.13. `?garage_entry=<id>` pre-selects the motorcycle when reached
    via the Garage tab's "Book Service" action (spec 6.17.2).
    """
    initial = {}
    if request.user.is_authenticated:
        initial = {
            "contact_first_name": request.user.first_name, "contact_last_name": request.user.last_name,
            "contact_email": request.user.email, "contact_phone": request.user.profile.phone,
        }
        garage_entry_id = request.GET.get("garage_entry")
        if garage_entry_id:
            entry = request.user.garage_entries.filter(pk=garage_entry_id).first()
            if entry:
                initial["garage_entry"] = entry
                initial["product"] = entry.product

    if request.method == "POST":
        form = ServiceBookingForm(request.POST, user=request.user)
        if form.is_valid():
            booking = form.save(commit=False)
            if request.user.is_authenticated:
                booking.user = request.user
            booking.save()
            _grant_booking_access(request, "service", booking.pk)
            messages.success(request, "Your service request has been sent — the dealer will confirm shortly.")
            return redirect("bookings:service_confirmation", pk=booking.pk)
    else:
        form = ServiceBookingForm(user=request.user, initial=initial)

    return render(request, "bookings/service_booking.html", {
        "form": form,
        # Drives the optional "From Your Garage" selector, which only renders
        # when the signed-in user actually owns something. The form already
        # scopes `garage_entry`'s queryset to this user (so a forged pk from
        # another account is rejected server-side regardless) -- this is only
        # so the template can decide whether to show the field at all.
        "garage_entries": (
            request.user.garage_entries.select_related("product").all()
            if request.user.is_authenticated else []
        ),
    })


def service_confirmation_view(request, pk):
    booking = get_object_or_404(ServiceBooking, pk=pk)
    if not _can_access_booking(request, "service", booking):
        raise PermissionDenied
    return render(request, "bookings/service_confirmation.html", {"booking": booking})


def _require_dealer_staff(request):
    """BR-ACC-04/BR-BK-04: only Dealer Staff assigned to a dealer may see or act on that dealer's queue."""
    if not request.user.is_authenticated:
        raise PermissionDenied
    profile = request.user.profile
    if profile.role != UserRole.DEALER_STAFF or profile.dealer_id is None:
        raise PermissionDenied
    return profile


@login_required
def dealer_booking_queue_view(request):
    profile = _require_dealer_staff(request)
    return render(request, "bookings/dealer_queue.html", {
        "dealer": profile.dealer,
        "test_ride_bookings": TestRideBooking.objects.filter(
            dealer=profile.dealer, status__in=[BookingStatus.REQUESTED, BookingStatus.CONFIRMED]
        ),
        "service_bookings": ServiceBooking.objects.filter(
            dealer=profile.dealer, status__in=[BookingStatus.REQUESTED, BookingStatus.CONFIRMED]
        ),
    })


_BOOKING_MODELS = {"test_ride": TestRideBooking, "service": ServiceBooking}
_ALLOWED_TRANSITIONS = {BookingStatus.CONFIRMED, BookingStatus.CANCELLED, BookingStatus.COMPLETED}


@login_required
def booking_update_status_view(request, booking_type, pk):
    """BR-BK-04: confirm / cancel / complete, restricted to the booking's own dealer's staff."""
    profile = _require_dealer_staff(request)
    model_cls = _BOOKING_MODELS.get(booking_type)
    if model_cls is None:
        raise PermissionDenied
    booking = get_object_or_404(model_cls, pk=pk, dealer=profile.dealer)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in _ALLOWED_TRANSITIONS:
            booking.status = new_status
            booking.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Booking marked {booking.get_status_display()}.")
        else:
            messages.error(request, "Invalid status.")

    return redirect("bookings:dealer_queue")
