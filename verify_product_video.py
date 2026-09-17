"""
verify_product_video

Covers the optional video added to the product detail page.

The interesting part isn't "a field exists" — it's the translation layer.
A YouTube link pasted by an admin is not a URL a browser can embed, and
the failure is silent: an iframe pointed at `youtube.com/watch?v=ID`
renders a whole YouTube page, and `youtu.be/ID` renders nothing at all.
So most of what's below is the URL parser, one case per shape an admin
might realistically paste, plus the two rendering paths (<video> for a
file, <iframe> for a hosted player) and the rule that decides between
them when both fields are filled.

Every product mutated here is restored in the `finally` block, so this
runs against a working database without leaving it changed.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings

settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ["testserver"]

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from catalog.models import Product, ProductType, validate_product_video
from catalog.video import mime_type_for, parse_video_url

PASSES = [0]


def ok(label, cond, extra=""):
    PASSES[0] += 1
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(extra)) if extra else ""))
    assert cond, label


def kind_of(url):
    return parse_video_url(url)[0]


def embed_of(url):
    return parse_video_url(url)[1]


bike = Product.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True).first()
accessory = Product.objects.filter(product_type=ProductType.ACCESSORY, is_active=True).first()
original_url = bike.video_trailer_url
original_file = bike.video_file.name

try:
    print("\n=== URL PARSING: THE SHAPES AN ADMIN ACTUALLY PASTES ===")
    ok("standard watch URL", kind_of("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube")
    ok("...becomes a real embed URL",
       embed_of("https://www.youtube.com/watch?v=dQw4w9WgXcQ").startswith(
           "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
       embed_of("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
    ok("share link (youtu.be)", kind_of("https://youtu.be/dQw4w9WgXcQ") == "youtube")
    ok("...resolves to the same embed",
       embed_of("https://youtu.be/dQw4w9WgXcQ") == embed_of("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
    ok("Shorts URL", kind_of("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "youtube")
    ok("already-an-embed URL is accepted, not double-wrapped",
       embed_of("https://www.youtube.com/embed/dQw4w9WgXcQ").count("embed") == 1)
    ok("mobile URL", kind_of("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube")
    ok("a start time is dropped (a product trailer starts at the start)",
       "t=42" not in embed_of("https://youtu.be/dQw4w9WgXcQ?t=42"))
    ok("a playlist is dropped (one trailer, not a queue of other videos)",
       "list=" not in embed_of("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123456"))

    ok("vimeo URL", kind_of("https://vimeo.com/76979871") == "vimeo")
    ok("...becomes a player URL",
       embed_of("https://vimeo.com/76979871") == "https://player.vimeo.com/video/76979871")
    ok("vimeo player URL is accepted as-is", kind_of("https://player.vimeo.com/video/76979871") == "vimeo")

    ok("direct mp4 link plays as a file", kind_of("https://cdn.example.com/films/urban-e.mp4") == "file")
    ok("...and a signed URL still matches on the path",
       kind_of("https://cdn.example.com/films/urban-e.mp4?token=abc123") == "file")
    ok("webm too", kind_of("https://cdn.example.com/films/urban-e.webm") == "file")

    print("\n=== URL PARSING: WHAT MUST *NOT* BE ACCEPTED ===")
    # Each of these renders an empty box rather than an error if it slips
    # through, which is why they're refused at save time instead.
    ok("a channel URL is not a video", kind_of("https://www.youtube.com/@pihilics") == "")
    ok("a playlist page is not a video", kind_of("https://www.youtube.com/playlist?list=PL123") == "")
    ok("the YouTube home page is not a video", kind_of("https://www.youtube.com/") == "")
    ok("a malformed id is refused", kind_of("https://youtu.be/tooshort") == "")
    ok("an arbitrary web page is refused", kind_of("https://example.com/our-video-page") == "")
    ok("a javascript: URL is refused", kind_of("javascript:alert(1)") == "")
    ok("empty input is handled, not raised on", kind_of("") == "")
    ok("None is handled too", kind_of(None) == "")

    ok("mime type follows the extension", mime_type_for("trailer.webm") == "video/webm")
    ok("...and defaults sensibly", mime_type_for("trailer.unknown") == "video/mp4")

    print("\n=== MODEL VALIDATION ===")
    bike.video_file = ""
    bike.video_trailer_url = "https://www.youtube.com/@pihilics"
    try:
        bike.full_clean()
        raised = False
    except ValidationError as exc:
        raised = "video_trailer_url" in exc.message_dict
    ok("an unembeddable link is rejected at save time, not at render time", raised)

    bike.video_trailer_url = "https://youtu.be/dQw4w9WgXcQ"
    bike.full_clean()
    ok("a real video link validates", True)

    accessory.video_trailer_url = "https://youtu.be/dQw4w9WgXcQ"
    try:
        accessory.full_clean()
        blocked = False
    except ValidationError as exc:
        blocked = "video_trailer_url" in exc.message_dict
    ok("accessories still can't have a trailer (spec 8.2)", blocked)
    accessory.video_trailer_url = ""

    oversized = SimpleUploadedFile("huge.mp4", b"0", content_type="video/mp4")
    oversized.size = 300 * 1024 * 1024
    try:
        validate_product_video(oversized)
        refused = False
    except ValidationError as exc:
        refused = "under" in " ".join(exc.messages)
    ok("an oversized upload is refused with the limit stated", refused)

    try:
        validate_product_video(SimpleUploadedFile("notes.pdf", b"x", content_type="application/pdf"))
        refused = False
    except ValidationError:
        refused = True
    ok("a non-video upload is refused", refused)

    try:
        validate_product_video(SimpleUploadedFile("film.mp4", b"x", content_type="application/zip"))
        refused = False
    except ValidationError:
        refused = True
    ok("an archive renamed .mp4 is refused (extension and type must agree)", refused)

    print("\n=== video_source: ONE ANSWER FOR THE TEMPLATE ===")
    bike.video_trailer_url = ""
    bike.video_file = ""
    bike.save()
    ok("no video configured -> nothing to render", bike.video_source is None)
    ok("has_video agrees", bike.has_video is False)

    bike.video_trailer_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    bike.save()
    source = bike.video_source
    ok("a link yields an iframe source", source["kind"] == "youtube", source)
    ok("...pointing at the no-cookie player", "youtube-nocookie.com" in source["url"])

    bike.video_file.save(
        "trailer.mp4", SimpleUploadedFile("trailer.mp4", b"fake-mp4-bytes", content_type="video/mp4"),
        save=True,
    )
    source = bike.video_source
    ok("an uploaded file wins over a link that's also set", source["kind"] == "file", source)
    ok("...with a mime type for the <source> tag", source["mime"] == "video/mp4")
    ok("...and a poster falling back to the product's own photo", bool(source["poster"]), source["poster"])

    print("\n=== RENDERED PAGE ===")
    client = Client()
    html = client.get(f"/products/{bike.slug}/").content.decode()
    ok("uploaded video renders as a <video> element", "<video controls" in html)
    ok("...not as an iframe", "<iframe" not in html)
    ok("...with the file as its source", bike.video_file.url in html)
    ok("...and preload=metadata, so scrolling past costs no bandwidth", 'preload="metadata"' in html)
    ok("...inside a reserved 16:9 box, so the page doesn't reflow on load", "aspect-ratio:16/9" in html)

    bike.video_file.delete(save=True)
    bike.video_trailer_url = "https://youtu.be/dQw4w9WgXcQ"
    bike.save()
    html = client.get(f"/products/{bike.slug}/").content.decode()
    ok("a link renders as an <iframe>", "<iframe" in html)
    ok("...not as a <video>", "<video controls" not in html)
    ok("...pointed at the embed URL, not the pasted one",
       "youtube-nocookie.com/embed/dQw4w9WgXcQ" in html)
    ok("...lazily, so it doesn't block the page it's below", 'loading="lazy"' in html)

    bike.video_trailer_url = ""
    bike.save()
    html = client.get(f"/products/{bike.slug}/").content.decode()
    ok("no video -> the section is absent entirely, no empty frame",
       'id="product-video"' not in html)
    ok("...and the rest of the page is unaffected", bike.name in html and "Add to Cart" in html)

    accessory_html = client.get(f"/products/{accessory.slug}/").content.decode()
    ok("accessory pages never show a video section", 'id="product-video"' not in accessory_html)

finally:
    bike.refresh_from_db()
    if bike.video_file:
        bike.video_file.delete(save=False)
    bike.video_file = original_file
    bike.video_trailer_url = original_url
    bike.save()
    accessory.video_trailer_url = ""
    accessory.save()

print(f"\nALL PRODUCT-VIDEO CHECKS PASSED ({PASSES[0]} assertions)")
print("  (database restored: product video fields back to their original values)")
