"""
Rebrand + re-territorialisation, core app.

`country` becomes `wilaya` on both CompanyInfo and VATRate. These are
RenameField operations, not drop-and-add: the column (and every row in it)
survives, which matters because VATRate rows are admin-entered data.

Any value already stored is a 2-letter ISO country code ("DE", "FR"), which
is not a valid wilaya code, so the accompanying data function clears those
stale values rather than leaving a row that renders as a blank label and
silently misprices an order. Seeded installs are expected to re-run
`seed_minimal` / `seed_full` afterwards.
"""

from django.db import migrations, models

from core.constants import WILAYA_CHOICES


STALE_COUNTRY_CODES = [
    "DE", "FR", "IT", "ES", "NL", "AT", "BE",
    "CH", "PT", "PL", "SE", "NO", "DK", "GB",
]


def clear_stale_country_values(apps, schema_editor):
    """Drop VATRate rows and reset CompanyInfo whose wilaya is an old country code."""
    VATRate = apps.get_model("core", "VATRate")
    CompanyInfo = apps.get_model("core", "CompanyInfo")

    VATRate.objects.filter(wilaya__in=STALE_COUNTRY_CODES).delete()
    CompanyInfo.objects.filter(wilaya__in=STALE_COUNTRY_CODES).update(wilaya="16")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_companyinfo_facebook_url_companyinfo_instagram_url_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="companyinfo", old_name="country", new_name="wilaya",
        ),
        migrations.RenameField(
            model_name="vatrate", old_name="country", new_name="wilaya",
        ),
        migrations.RunPython(clear_stale_country_values, noop),
        migrations.AlterField(
            model_name="companyinfo",
            name="wilaya",
            field=models.CharField(
                choices=WILAYA_CHOICES, default="16", max_length=2,
            ),
        ),
        migrations.AlterField(
            model_name="companyinfo",
            name="city",
            field=models.CharField(help_text="Commune / city.", max_length=100),
        ),
        migrations.AlterField(
            model_name="companyinfo",
            name="postal_code",
            field=models.CharField(help_text="5-digit Algerian postal code.", max_length=20),
        ),
        migrations.AlterField(
            model_name="companyinfo",
            name="registration_number",
            field=models.CharField(help_text="Registre de Commerce (RC) number.", max_length=100),
        ),
        migrations.AlterField(
            model_name="companyinfo",
            name="vat_number",
            field=models.CharField(max_length=50, verbose_name="NIF / TVA number"),
        ),
        migrations.AlterField(
            model_name="companyinfo",
            name="trade_name",
            field=models.CharField(
                blank=True,
                help_text="Public-facing brand name shown site-wide (header, footer, page titles, invoices).",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="companyinfo",
            name="tagline",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Short brand line used in page meta descriptions and the footer.",
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="companyinfo",
            name="default_currency",
            field=models.CharField(default="DZD", max_length=3),
        ),
        migrations.AlterField(
            model_name="companyinfo",
            name="default_vat_rate",
            field=models.DecimalField(
                decimal_places=2,
                default=19.0,
                help_text="Fallback TVA rate (Algeria's standard rate is 19%) used when the "
                          "destination wilaya has no explicit VATRate row.",
                max_digits=5,
            ),
        ),
        migrations.AlterField(
            model_name="vatrate",
            name="wilaya",
            field=models.CharField(choices=WILAYA_CHOICES, max_length=2, unique=True),
        ),
        migrations.AlterModelOptions(
            name="vatrate",
            options={
                "ordering": ["wilaya"],
                "verbose_name": "TVA Rate",
                "verbose_name_plural": "TVA Rates",
            },
        ),
        migrations.CreateModel(
            name="ShippingZone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("wilaya", models.CharField(choices=WILAYA_CHOICES, max_length=2, unique=True)),
                ("home_fee", models.DecimalField(
                    decimal_places=2, max_digits=10,
                    help_text="Cost of delivery to the customer's address (à domicile), in DZD.",
                )),
                ("desk_fee", models.DecimalField(
                    blank=True, decimal_places=2, max_digits=10, null=True,
                    help_text="Cost of collection from the courier's agency (stopdesk), in DZD. "
                              "Leave empty if stopdesk isn't offered in this wilaya.",
                )),
                ("delivery_days_min", models.PositiveSmallIntegerField(default=2)),
                ("delivery_days_max", models.PositiveSmallIntegerField(default=5)),
                ("is_active", models.BooleanField(
                    default=True,
                    help_text="Uncheck to stop offering delivery to this wilaya without deleting its pricing.",
                )),
            ],
            options={
                "verbose_name": "Shipping Zone",
                "verbose_name_plural": "Shipping Zones",
                "ordering": ["wilaya"],
            },
        ),
    ]
