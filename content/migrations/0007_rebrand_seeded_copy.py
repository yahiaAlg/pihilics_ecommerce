"""
Rewrite the seeded Home/About copy for the Algerian rebrand.

Why this is a data migration and not just a default change: the
HomePageContent/AboutPageContent singletons are created by
0003_seed_page_content, which -- like every migration -- builds its rows from
the *historical* model state frozen in 0002, not from content/models.py as it
reads today. Changing the field defaults (0006) therefore only affects rows
created from here on; the already-seeded singleton keeps the original German
copy. This updates the row itself.

It only rewrites a field still holding the exact superseded default, so an
admin who has already edited the copy in the CMS keeps their wording.
"""

from django.db import migrations


HOME_REPLACEMENTS = {
    "hero_subtitle": (
        "Instant torque. Hot-swap batteries. Zero emissions. Built in "
        "Europe for riders who go where the road ends.",
        "Instant torque. Hot-swap batteries. Zero emissions. Built for "
        "Algerian roads and the tracks beyond them.",
    ),
    "testride_body": (
        "Book a free test ride at any of our {dealer_count} European "
        "dealers. Bring your licence, we'll bring the bike.",
        "Book a free test ride at any of our {dealer_count} dealers "
        "across the country. Bring your licence, we'll bring the bike.",
    ),
}

ABOUT_REPLACEMENTS = {
    "hero_subtitle": (
        "Founded in 2021 in Berlin, ARKO builds electric motorcycles "
        "for riders who go where the road ends. No noise. No emissions. No compromise.",
        "Founded in 2021 in Setif, we build electric motorcycles "
        "for riders who go where the road ends. No noise. No emissions. No compromise.",
    ),
    "mission_paragraph_1": (
        "We started ARKO because electric motorcycles were either "
        "street scooters or expensive prototypes. We wanted a bike that "
        "could handle a hard enduro stage on Saturday and commute to work "
        "on Monday — all electric, all silent, all torque.",
        "We started this company because electric motorcycles were either "
        "street scooters or expensive prototypes. We wanted a bike that "
        "could handle a hard enduro stage on Saturday and commute to work "
        "on Monday — all electric, all silent, all torque.",
    ),
    "mission_paragraph_2": (
        "Every ARKO is designed and assembled in our Berlin "
        "facility. We forge our own frames, wind our own motors, and test "
        "every bike on the trails of the Brandenburg forest before it ships.",
        "Every bike is designed and assembled in our Setif "
        "facility. We forge our own frames, wind our own motors, and test "
        "every bike in the Babor mountains before it ships.",
    ),
    "stats_title": ("ARKO in 2026", "By the Numbers, 2026"),
    "riders_stat_label": ("Riders Worldwide", "Riders Nationwide"),
}


def _apply(model, replacements):
    for row in model.objects.all():
        changed = []
        for field, (old, new) in replacements.items():
            if getattr(row, field) == old:
                setattr(row, field, new)
                changed.append(field)
        if changed:
            row.save(update_fields=changed)


def rebrand_copy(apps, schema_editor):
    _apply(apps.get_model("content", "HomePageContent"), HOME_REPLACEMENTS)
    _apply(apps.get_model("content", "AboutPageContent"), ABOUT_REPLACEMENTS)


def restore_copy(apps, schema_editor):
    """Reverse: swap the pairs so `migrate content 0006` restores the old copy."""
    _apply(
        apps.get_model("content", "HomePageContent"),
        {f: (new, old) for f, (old, new) in HOME_REPLACEMENTS.items()},
    )
    _apply(
        apps.get_model("content", "AboutPageContent"),
        {f: (new, old) for f, (old, new) in ABOUT_REPLACEMENTS.items()},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0006_algeria_copy_defaults"),
    ]

    operations = [
        migrations.RunPython(rebrand_copy, restore_copy),
    ]
