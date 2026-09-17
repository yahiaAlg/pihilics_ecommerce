"""
Populates the tables that replaced the hardcoded lists in core/constants.py.

The choice accessors fall back to those literals when a table is empty, so
nothing *breaks* without this migration -- but an empty Wilayas changelist
would be a puzzle for whoever opens the admin looking to edit the list they
were told is now editable. Seeding makes the new tables self-explanatory:
58 wilayas, four languages, one settings row carrying the same figures the
constants used to hold.

`update_or_create` on the code, not `create`: re-running this (a squash, a
re-applied migration on a database that already has rows) must not
duplicate or crash. `is_active` is deliberately *not* forced on update,
so re-applying can't silently re-enable a wilaya an operator withdrew.
"""

from django.db import migrations

from core.constants import (
    DEFAULT_EXPRESS_SHIPPING_SURCHARGE,
    DEFAULT_FREE_SHIPPING_THRESHOLD,
    DEFAULT_STANDARD_SHIPPING_FEE,
    FALLBACK_LANGUAGES,
    FALLBACK_WILAYAS,
)


def seed(apps, schema_editor):
    Wilaya = apps.get_model("core", "Wilaya")
    Language = apps.get_model("core", "Language")
    CheckoutSettings = apps.get_model("core", "CheckoutSettings")

    for code, name in FALLBACK_WILAYAS:
        Wilaya.objects.update_or_create(
            code=code, defaults={"name": name}
        )

    for index, (code, name) in enumerate(FALLBACK_LANGUAGES):
        Language.objects.update_or_create(
            code=code, defaults={"name": name, "sort_order": index}
        )

    # Singleton: the historical model has no custom save() enforcing pk=1
    # (migrations run against a rebuilt model class), so pin it explicitly.
    CheckoutSettings.objects.update_or_create(
        pk=1,
        defaults={
            "free_shipping_threshold": DEFAULT_FREE_SHIPPING_THRESHOLD,
            "standard_shipping_fee": DEFAULT_STANDARD_SHIPPING_FEE,
            "express_shipping_surcharge": DEFAULT_EXPRESS_SHIPPING_SURCHARGE,
            # CIB/Edahabia stays off until Chargily has verified the
            # account; the integration itself is complete and untouched.
            "card_payments_enabled": False,
        },
    )


def unseed(apps, schema_editor):
    """
    Deliberately a no-op.

    Reversing this migration is reversing *seeding*, not reversing a schema
    change -- and by the time anyone does, the rows will have been edited:
    wilayas deactivated, a threshold re-priced. Deleting them to "restore"
    a previous state would throw that away, and every field here has a code
    default to fall back on anyway. The following migration
    (0006_...) is what actually drops the tables on a full reverse.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_checkoutsettings_language_wilaya_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
