"""Address.country -> Address.wilaya, plus the localized language default."""

from django.db import migrations, models

from core.constants import LANGUAGE_CHOICES, WILAYA_CHOICES

STALE_COUNTRY_CODES = [
    "DE", "FR", "IT", "ES", "NL", "AT", "BE",
    "CH", "PT", "PL", "SE", "NO", "DK", "GB",
]


def clear_stale_country_values(apps, schema_editor):
    """A saved address whose wilaya is an old ISO country code can't be
    delivered to, and guessing a wilaya for it would be worse than asking.
    Deleting the row makes the customer re-enter it at next checkout, which
    is the only correct outcome -- the street/city underneath it are foreign
    addresses this store no longer ships to at all."""
    Address = apps.get_model("accounts", "Address")
    Address.objects.filter(wilaya__in=STALE_COUNTRY_CODES).delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("core", "0003_algeria_wilaya_and_brand"),
    ]

    operations = [
        migrations.RenameField(model_name="address", old_name="country", new_name="wilaya"),
        migrations.RunPython(clear_stale_country_values, noop),
        migrations.AlterField(
            model_name="address",
            name="wilaya",
            field=models.CharField(choices=WILAYA_CHOICES, max_length=2),
        ),
        migrations.AlterField(
            model_name="address",
            name="city",
            field=models.CharField(help_text="Commune / city.", max_length=100),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="preferred_language",
            field=models.CharField(choices=LANGUAGE_CHOICES, default="fr", max_length=5),
        ),
    ]
