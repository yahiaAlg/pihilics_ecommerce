"""
bookings.signals

BR-BK-05: "Completing a Service Booking updates the related
GarageEntry.service_due_at based on the service tier performed." The
interval-per-tier math itself lives in bookings.utils.calculate_next_service_due.

Mailing (bookings/notifications.py): both TestRideBooking and
ServiceBooking share the same lifecycle (REQUESTED -> CONFIRMED/CANCELLED
-> COMPLETED, all admin-driven from the dealer queue —
bookings.views.booking_update_status_view), so one pair of generic
receivers below covers both models rather than duplicating them per type.
The pre_save "stash previous status" pattern mirrors orders/signals.py.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from accounts.models import GarageEntry

from .models import BookingStatus, ServiceBooking, TestRideBooking
from .utils import calculate_next_service_due


@receiver(pre_save, sender=ServiceBooking)
@receiver(pre_save, sender=TestRideBooking)
def stash_previous_status(sender, instance, **kwargs):
    """Records the pre-save status so post_save can detect a genuine transition."""
    if instance.pk:
        instance._previous_status = (
            sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    else:
        instance._previous_status = None


@receiver(post_save, sender=ServiceBooking)
def update_garage_entry_service_due_date(sender, instance, created, **kwargs):
    """BR-BK-05: push the linked GarageEntry's next-service-due date out by the tier's interval."""
    if created:
        return
    previous_status = getattr(instance, "_previous_status", None)
    if instance.status != BookingStatus.COMPLETED or previous_status == BookingStatus.COMPLETED:
        return
    if not instance.garage_entry_id:
        return

    next_due = calculate_next_service_due(timezone.localdate(), instance.service_tier.name)
    GarageEntry.objects.filter(pk=instance.garage_entry_id).update(service_due_at=next_due)


@receiver(post_save, sender=ServiceBooking)
@receiver(post_save, sender=TestRideBooking)
def send_booking_mail(sender, instance, created, **kwargs):
    """
    Mailing: a "received" email (+ admin alert) the moment a booking is
    requested, or a status-change email to the customer on every later
    genuine transition (dealer-queue confirm/cancel/complete). Mail
    failures never raise (core.emails swallows them), so this never
    blocks the save that triggered it.
    """
    from . import notifications

    booking_type = "test_ride" if sender is TestRideBooking else "service"

    if created:
        notifications.send_booking_received(instance, booking_type)
        return

    previous_status = getattr(instance, "_previous_status", None)
    if previous_status is not None and previous_status != instance.status:
        notifications.send_booking_status_update(instance, booking_type)
