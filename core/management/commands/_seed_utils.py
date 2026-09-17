"""
Shared helpers for the `seed_minimal` / `seed_full` management commands.

Kept as a private (underscore-prefixed) module inside `core/management/commands/`
so Django's command auto-discovery ignores it -- it isn't a command itself,
just code the two real commands import.
"""

import urllib.error
import urllib.request

from django.core.files.base import ContentFile

# Lorem Picsum (https://picsum.photos) is a free, no-signup, no-API-key image
# API: requesting the same seed always returns the same photo, which is what
# lets re-running a seed command produce identical demo data instead of a new
# random image every time.
PLACEHOLDER_IMAGE_URL = "https://picsum.photos/seed/{seed}/{width}/{height}"


def fetch_placeholder_image(seed, width=800, height=600, timeout=8):
    """
    Downloads a deterministic placeholder photo and returns it as a
    Django ContentFile ready to assign to an ImageField, e.g.:

        product.images.create(image=fetch_placeholder_image("arko-rvx"))

    Never raises: on any network problem this returns None, so seeding still
    completes -- just without photos -- when run offline or in CI. Callers
    should treat a None return as "skip this image" rather than an error.
    """
    url = PLACEHOLDER_IMAGE_URL.format(seed=seed, width=width, height=height)
    request = urllib.request.Request(url, headers={"User-Agent": "arko-seed-command/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if not data:
        return None
    return ContentFile(data, name=f"{seed}.jpg")


def ensure_legal_documents(stdout=None):
    """
    Recreates the Terms of Service / Privacy Policy rows if they are absent.

    Both seed commands call this. The rows are normally created by
    content.0003_seed_page_content, but a migration only runs once: after a
    `manage.py flush` or any data rebuild the rows are gone for good while
    Django still considers the database fully migrated, and `/terms/` and
    `/privacy/` start returning 404 (their views resolve the row by slug with
    get_object_or_404). Seeding is the one place that rebuilds content, so it
    is also where the legal pages get put back.

    Idempotent by design: an existing row -- including one an admin has since
    rewritten in the CMS -- is left exactly as it is.
    """
    from content.legal_seed import LEGAL_DOCUMENTS
    from content.models import LegalDocument

    created = []
    for slug, (title, last_updated, body) in LEGAL_DOCUMENTS.items():
        _, was_created = LegalDocument.objects.get_or_create(
            slug=slug,
            defaults={"title": title, "last_updated": last_updated, "body": body},
        )
        if was_created:
            created.append(slug)
    if stdout is not None and created:
        stdout.write(f"  Legal documents restored: {', '.join(created)}")
    return created
