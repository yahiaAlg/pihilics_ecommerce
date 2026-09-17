"""
core.signals

Keeps core.constants' choice cache honest.

The choice lists (wilayas, languages, booking slots) are read on almost
every request -- every rendered <select>, every `get_wilaya_display()` --
and written roughly never, so core.constants caches them per process. The
receivers below are what makes that cache safe: editing a Wilaya in the
admin takes effect on the next request instead of at the next restart.

Registered from core.apps.CoreConfig.ready.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.constants import clear_choice_cache


@receiver(post_save, sender="core.Wilaya")
@receiver(post_delete, sender="core.Wilaya")
def _invalidate_wilaya_choices(sender, **kwargs):
    clear_choice_cache("wilaya")


@receiver(post_save, sender="core.Language")
@receiver(post_delete, sender="core.Language")
def _invalidate_language_choices(sender, **kwargs):
    clear_choice_cache("language")


@receiver(post_save, sender="bookings.TimeSlot")
@receiver(post_delete, sender="bookings.TimeSlot")
def _invalidate_time_slot_choices(sender, **kwargs):
    clear_choice_cache("time_slot")
