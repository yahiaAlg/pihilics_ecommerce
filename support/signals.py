"""
support.signals

Mailing (support/notifications.py): every ContactMessage — from either the
dedicated Contact page or the Help Center's embedded form, both of which
go through support.views.handle_contact_submission's single save path —
gets an acknowledgement email to the sender and an alert to the admin
inbox the moment it's created.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ContactMessage


@receiver(post_save, sender=ContactMessage)
def send_contact_mail(sender, instance, created, **kwargs):
    """Mail failures never raise (core.emails swallows them), so this never blocks the form submission."""
    if not created:
        return
    from . import notifications

    notifications.send_contact_acknowledgement(instance)
    notifications.send_contact_admin_alert(instance)
