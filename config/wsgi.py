"""
WSGI config for the Pihilics backend.

Exposes the WSGI callable as a module-level variable named `application`.
Project-config layout (see settings.py's docstring): this file lives in
the `config/` package next to settings.py and urls.py, so
DJANGO_SETTINGS_MODULE is the dotted "config.settings" path.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
