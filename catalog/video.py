"""
catalog.video

Turns whatever an admin pasted into `Product.video_trailer_url` into
something a browser can actually play.

There are only two ways to show a video on a page, and they need different
markup: a file the browser fetches and plays itself (`<video>`), or a
player hosted by someone else (`<iframe>`). A pasted YouTube link is
neither until it's translated -- `youtube.com/watch?v=ID` renders as a
full YouTube *page* inside an iframe, ads and sidebar included, and
`youtu.be/ID` doesn't render at all. The embed form is a different URL, so
something has to do the translation. This module is that something, kept
out of models.py because the URL shapes are fiddly and worth testing on
their own.

Recognised: YouTube (watch / youtu.be / shorts / embed / live), Vimeo
(vimeo.com/ID and player.vimeo.com/video/ID), and any direct link to a
video file. Anything else is reported as unrecognised so the admin form
can say so at save time rather than the product page rendering an empty
box a year later.

YouTube embeds go through youtube-nocookie.com: same player, but it
doesn't set tracking cookies until the visitor presses play, which is the
polite default for a video most visitors will scroll past.
"""

import re
from urllib.parse import parse_qs, urlparse

# Extensions a <video> element can be pointed at directly. Deliberately
# short: these are the formats browsers actually decode natively.
VIDEO_FILE_EXTENSIONS = (".mp4", ".webm", ".ogv", ".ogg", ".mov", ".m4v")

# MIME types matching the extensions above, used for the <source> hint.
_MIME_BY_EXTENSION = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".ogv": "video/ogg",
    ".ogg": "video/ogg",
}

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com",
                  "www.youtube-nocookie.com", "music.youtube.com"}
_YOUTUBE_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_VIMEO_HOSTS = {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}

# A YouTube id is 11 characters of URL-safe base64. Matching the shape
# rather than accepting any path segment keeps a mistyped link (a channel
# URL, a playlist page) from being silently turned into a dead embed.
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VIMEO_ID = re.compile(r"^\d+$")


def mime_type_for(path):
    """Best-guess MIME type for a video path/filename, for a <source> tag."""
    lowered = (path or "").lower()
    for extension, mime in _MIME_BY_EXTENSION.items():
        if lowered.endswith(extension):
            return mime
    return "video/mp4"


def _youtube_id(parsed):
    host = parsed.netloc.lower()
    segments = [segment for segment in parsed.path.split("/") if segment]

    if host in _YOUTUBE_SHORT_HOSTS:
        candidate = segments[0] if segments else ""
    elif host in _YOUTUBE_HOSTS:
        if segments and segments[0] == "watch":
            # ?v=ID, possibly alongside &t= or &list= which we drop: a
            # start time is a viewing detail, a playlist would quietly turn
            # one product's trailer into a queue of unrelated videos.
            candidate = (parse_qs(parsed.query).get("v") or [""])[0]
        elif len(segments) >= 2 and segments[0] in ("embed", "shorts", "live", "v"):
            candidate = segments[1]
        else:
            candidate = ""
    else:
        return ""

    return candidate if _YOUTUBE_ID.match(candidate) else ""


def _vimeo_id(parsed):
    if parsed.netloc.lower() not in _VIMEO_HOSTS:
        return ""
    segments = [segment for segment in parsed.path.split("/") if segment]
    if segments and segments[0] == "video":  # player.vimeo.com/video/ID
        segments = segments[1:]
    candidate = segments[0] if segments else ""
    return candidate if _VIMEO_ID.match(candidate) else ""


def parse_video_url(url):
    """
    Classify `url` and return `(kind, playable_url)`.

    kind is one of:
      "youtube" / "vimeo" -- playable_url is an embed URL for an <iframe>
      "file"              -- playable_url is the original URL, for <video>
      ""                  -- not recognised; playable_url is empty

    An empty or malformed input returns `("", "")` rather than raising:
    callers are a template property and a form validator, and neither
    wants to guard every access.
    """
    url = (url or "").strip()
    if not url:
        return "", ""

    try:
        parsed = urlparse(url)
    except ValueError:
        return "", ""

    if parsed.scheme not in ("http", "https"):
        return "", ""

    video_id = _youtube_id(parsed)
    if video_id:
        return "youtube", f"https://www.youtube-nocookie.com/embed/{video_id}?rel=0"

    video_id = _vimeo_id(parsed)
    if video_id:
        return "vimeo", f"https://player.vimeo.com/video/{video_id}"

    # A direct link to a file the browser can play. Checked against the
    # path alone so a `?token=...` signed URL from a CDN still matches.
    if parsed.path.lower().endswith(VIDEO_FILE_EXTENSIONS):
        return "file", url

    return "", ""
