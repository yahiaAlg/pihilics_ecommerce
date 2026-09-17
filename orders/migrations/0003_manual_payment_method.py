"""
Collapses the "cod" / "transfer" PaymentMethod choices into a single
"manual" choice (Manual Order — Cash on Delivery / Bank Transfer), now
that both are fulfilled the same way: no gateway, confirmed and tracked
entirely through the mailing flow between admin and customer.

Orders are immutable snapshots (BR-ORD-01/02), so this is a genuine data
migration, not just a choices relabel — existing "cod"/"transfer" rows are
rewritten to "manual" so they render under the current label and are
included in the same admin filter/queue as new manual orders. This is the
one deliberate exception to migration 0002's "historic rows keep whatever
they recorded" rule: that rule protects facts about the order (what wilaya
it shipped to), not a payment-method taxonomy that no longer exists.
"""

from django.db import migrations, models


def forwards(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.filter(payment_method__in=["cod", "transfer"]).update(payment_method="manual")


def backwards(apps, schema_editor):
    # Not reversible in a lossless way (we don't know which of cod/transfer
    # a "manual" row originally was); leave rows as "manual" on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_order_wilaya_and_dz_payments"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cib", "CIB / Edahabia Card"),
                    ("manual", "Manual Order (Cash on Delivery / Bank Transfer)"),
                ],
                max_length=20,
            ),
        ),
    ]
