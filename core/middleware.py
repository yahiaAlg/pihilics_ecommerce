"""
core.middleware

WhiteNoise serves STATIC_ROOT out of the box, but it has no concept of
Django's MEDIA_ROOT: `WHITENOISE_ROOT` mounts a directory at the URL *root*,
so pointing it at MEDIA_ROOT would publish an uploaded file as
`/home/hero.jpg` rather than the `/media/home/hero.jpg` that MEDIA_URL (and
therefore every `{{ product.image.url }}` in a template) actually emits.

This subclass adds MEDIA_ROOT to the same file index WhiteNoise already
maintains for static, but under the MEDIA_URL prefix, so admin-uploaded
media is served by the app process alongside static with no nginx, no S3,
and no `static()` URL-conf hack that only works while DEBUG is on.

Media is deliberately *not* added to the hashed static manifest: its
filenames are stored in the database and must stay exactly as uploaded.
It therefore gets WHITENOISE_MAX_AGE (a short cache) rather than the
immutable far-future header hashed static files receive.
"""

from django.conf import settings
from whitenoise.middleware import WhiteNoiseMiddleware


class WhiteNoiseMediaMiddleware(WhiteNoiseMiddleware):
    def __init__(self, get_response=None, settings=settings):
        super().__init__(get_response, settings)

        media_root = getattr(settings, "MEDIA_ROOT", None)
        media_url = getattr(settings, "MEDIA_URL", None)
        if media_root and media_url:
            # add_files is what WhiteNoise itself uses for STATIC_ROOT; the
            # prefix makes every file under MEDIA_ROOT resolve at MEDIA_URL.
            self.add_files(str(media_root), prefix=media_url)
