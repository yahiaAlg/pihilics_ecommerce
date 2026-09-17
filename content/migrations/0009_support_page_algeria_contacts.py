"""
Algerian contact details for the Support page.

Three leftovers from the pre-rebrand build were still reaching visitors:
the two department mailboxes (`support@arko.eu` / `sales@arko.eu`) and an
opening-hours line advertising "Mon-Fri ... CET". Algeria's working week is
Sunday to Thursday, so the days were simply wrong, and the domain no longer
exists.

Same two-part shape as 0006 + 0007: an AlterField so newly created rows get
the right defaults, and a data pass for the singleton 0003 already created
from the *historical* model state -- changing a default alone would never
touch it. As in 0007, a field is only rewritten when it still holds the
exact superseded default, so an admin who has already set a real mailbox in
the CMS keeps it. Reverse restores the old values on the same condition.
"""

from django.db import migrations, models


REPLACEMENTS = {
    "email_support": ("support@arko.eu", "support@pihilics.dz"),
    "email_sales": ("sales@arko.eu", "sales@pihilics.dz"),
    "hours_text": ("Mon–Fri 9:00–18:00 CET", "Sun–Thu 9:00–17:00"),
}


def _apply(model, index_from, index_to):
    row = model.objects.first()
    if row is None:
        return
    changed = []
    for field, values in REPLACEMENTS.items():
        if getattr(row, field) == values[index_from]:
            setattr(row, field, values[index_to])
            changed.append(field)
    if changed:
        row.save(update_fields=changed)


def localize_contacts(apps, schema_editor):
    _apply(apps.get_model("content", "SupportPageContent"), 0, 1)


def restore_contacts(apps, schema_editor):
    _apply(apps.get_model("content", "SupportPageContent"), 1, 0)


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0008_reseed_legal_documents"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supportpagecontent",
            name="email_support",
            field=models.EmailField(default="support@pihilics.dz", max_length=254),
        ),
        migrations.AlterField(
            model_name="supportpagecontent",
            name="email_sales",
            field=models.EmailField(default="sales@pihilics.dz", max_length=254),
        ),
        migrations.AlterField(
            model_name="supportpagecontent",
            name="hours_text",
            field=models.CharField(default="Sun–Thu 9:00–17:00", max_length=80),
        ),
        migrations.RunPython(localize_contacts, restore_contacts),
    ]
