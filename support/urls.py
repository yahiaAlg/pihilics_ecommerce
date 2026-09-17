"""
support.urls

Spec 6.20's dedicated Contact page. Mounted at the site root by the
project URLConf. (The Help Center/FAQ page that embeds this same form is
`content:support` at `/support/` — see content.views.support_view.)
"""

from django.urls import path

from . import views

app_name = "support"

urlpatterns = [
    path("contact/", views.contact_view, name="contact"),
]
