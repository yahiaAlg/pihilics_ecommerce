"""
Restores the two LegalDocument rows if they are missing.

Why a second seeding pass: 0003_seed_page_content created "terms" and
"privacy", but a migration runs once. Any later `manage.py flush` or data
rebuild deletes the rows while django_migrations still records 0003 as
applied, so nothing ever recreates them -- which is exactly the state this
database was in, with `/terms/` and `/privacy/` returning 404 from
`_legal_document_view`'s get_object_or_404 even though the routes exist.

Unlike 0003 this migration reads its copy from content.legal_seed rather
than carrying its own frozen constants. Legal text is editorial content that
an admin owns after the first insert, not schema, so there is nothing to
freeze: get_or_create means an existing (possibly admin-edited) row is never
touched, and the same module backs the seed commands, so a flush-and-reseed
cycle restores the pages too.

No reverse: dropping the legal pages again is never the desired end state of
a `migrate content 0007`, and 0003's own unseed_content already handles the
delete side of this data.
"""

from django.db import migrations

from content.legal_seed import LEGAL_DOCUMENTS


def reseed_legal_documents(apps, schema_editor):
    LegalDocument = apps.get_model("content", "LegalDocument")
    for slug, (title, last_updated, body) in LEGAL_DOCUMENTS.items():
        LegalDocument.objects.get_or_create(
            slug=slug,
            defaults={"title": title, "last_updated": last_updated, "body": body},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0007_rebrand_seeded_copy"),
    ]

    operations = [
        migrations.RunPython(reseed_legal_documents, migrations.RunPython.noop),
    ]
