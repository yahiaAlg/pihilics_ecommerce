"""
Order.delivery_country -> delivery_wilaya, plus Algerian delivery/payment
method choices.

Orders are immutable snapshots (BR-ORD-01/02), so historic rows are NOT
rewritten to a wilaya they never shipped to. The rename keeps whatever the
row recorded; `get_delivery_wilaya_display()` falls back to the raw stored
value when it isn't in WILAYA_CHOICES, so an old order still prints the
destination it was actually sent to.

The choice-list changes on delivery_method/payment_method are
Django-validation-level only (CharField columns are unconstrained), so a
historic "paypal" order likewise keeps rendering its own value.
"""

from django.db import migrations, models

from core.constants import WILAYA_CHOICES


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0001_initial"),
        ("core", "0003_algeria_wilaya_and_brand"),
    ]

    operations = [
        migrations.RenameField(
            model_name="order", old_name="delivery_country", new_name="delivery_wilaya",
        ),
        migrations.AlterField(
            model_name="order",
            name="delivery_wilaya",
            field=models.CharField(choices=WILAYA_CHOICES, max_length=2),
        ),
        migrations.AlterField(
            model_name="order",
            name="delivery_method",
            field=models.CharField(
                choices=[
                    ("standard", "Home Delivery (à domicile)"),
                    ("express", "Express Home Delivery"),
                    ("desk", "Stopdesk (collect from agency)"),
                ],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cib", "CIB / Edahabia Card"),
                    ("cod", "Cash on Delivery"),
                    ("transfer", "Bank Transfer (CCP / Virement)"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="reference",
            field=models.CharField(
                editable=False, help_text="e.g. PHL-2026-0847", max_length=20, unique=True,
            ),
        ),
    ]
