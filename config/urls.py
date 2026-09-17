"""
Project root URLConf. Each app owns its own path prefix and namespace;
`content` and `catalog` (and `programs`/`support`, which add their own
distinct top-level segments) are included at `""` since their internal
patterns already carry a leading segment (`shop/`, `financing/`, etc.).
`orders` is included at `""` too, since it owns both `checkout/` and
`orders/`.

Wired up as `ROOT_URLCONF = "config.urls"` in config/settings.py.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = (
    [
        path("admin/", admin.site.urls),
        path("", include("content.urls")),
        path("", include("catalog.urls")),
        path("cart/", include("cart.urls")),
        path("", include("orders.urls")),
        path("accounts/", include("accounts.urls")),
        path("bookings/", include("bookings.urls")),
        path("dealers/", include("dealers.urls")),
        path("", include("programs.urls")),
        path("", include("support.urls")),
    ]
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
)

handler404 = "content.views.page_not_found_view"
