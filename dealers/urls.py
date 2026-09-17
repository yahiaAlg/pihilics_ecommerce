"""
dealers.urls

Spec 6.14: the dealer directory (map + live search). Mounted at
`dealers/` by the project URLConf.
"""

from django.urls import path

from . import views

app_name = "dealers"

urlpatterns = [
    path("", views.dealer_list_view, name="dealer_list"),
]
