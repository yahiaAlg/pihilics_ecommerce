"""Dealer.country -> Dealer.wilaya (see core/migrations/0003 for the rationale)."""

from django.db import migrations, models

from core.constants import WILAYA_CHOICES

STALE_COUNTRY_CODES = [
    "DE", "FR", "IT", "ES", "NL", "AT", "BE",
    "CH", "PT", "PL", "SE", "NO", "DK", "GB",
]


def clear_stale_country_values(apps, schema_editor):
    """Old rows hold ISO country codes, which are not valid wilaya codes.

    The seeded European dealer network is replaced wholesale by the Algerian
    one in seed_full/seed_minimal, so those rows are deactivated rather than
    left pointing at a wilaya they were never in. Deactivating (not deleting)
    keeps any FK from bookings intact.
    """
    Dealer = apps.get_model("dealers", "Dealer")
    Dealer.objects.filter(wilaya__in=STALE_COUNTRY_CODES).update(wilaya="16", is_active=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("dealers", "0001_initial"),
        ("core", "0003_algeria_wilaya_and_brand"),
    ]

    operations = [
        migrations.RenameField(model_name="dealer", old_name="country", new_name="wilaya"),
        migrations.RunPython(clear_stale_country_values, noop),
        migrations.AlterField(
            model_name="dealer",
            name="wilaya",
            field=models.CharField(choices=WILAYA_CHOICES, max_length=2),
        ),
    ]
