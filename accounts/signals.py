"""
accounts.signals

Automated workflow: every Django auth ``User`` must have a matching
``UserProfile`` (spec/system requirement: "Django's built-in User model
with a OneToOne Profile relationship"). Creating it here, at the moment the
User is created, means every other app can safely assume
``request.user.profile`` exists without defensive get_or_create calls.

The BR-ORD-05 "purchasing a motorcycle auto-creates a GarageEntry" workflow
is *not* handled here even though GarageEntry lives in this app — it is a
consequence of an order being placed, so it lives in orders.signals
alongside the related stock-decrement logic (BR-ORD-03), keeping all of an
order's side effects in one place.
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """Give every newly created User a default (customer-role) UserProfile."""
    if created:
        UserProfile.objects.get_or_create(user=instance)
