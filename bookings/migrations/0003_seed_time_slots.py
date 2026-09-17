"""
Seeds bookings.TimeSlot with the two half-day slots that used to be
core.constants.TIME_SLOT_CHOICES.

Same reasoning as core.0007: the accessor falls back to the literals when
the table is empty, so this isn't load-bearing -- it's what makes the new
table make sense to whoever opens it. Codes match the old constants
exactly, so every booking already stored ("morning", "afternoon") still
resolves to a label.
"""

from django.db import migrations

from core.constants import FALLBACK_TIME_SLOTS


def seed(apps, schema_editor):
    TimeSlot = apps.get_model("bookings", "TimeSlot")
    for index, (code, label) in enumerate(FALLBACK_TIME_SLOTS):
        TimeSlot.objects.update_or_create(
            code=code, defaults={"label": label, "sort_order": index}
        )


def unseed(apps, schema_editor):
    """No-op on purpose — see the note in core.0007_seed_dynamic_config."""


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0002_timeslot_alter_servicebooking_time_slot_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
