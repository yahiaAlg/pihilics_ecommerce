"""
programs.urls

Spec 6.15 (Financing) and 6.16 (Insurance). Mounted at the site root by
the project URLConf. `financing_calculate_json` is one of the four
explicitly allowed AJAX (JsonResponse) endpoints — the calculator's live
recalculation as any field changes.
"""

from django.urls import path

from . import views

app_name = "programs"

urlpatterns = [
    path("financing/", views.financing_view, name="financing"),
    path("financing/calculate/", views.financing_calculate_json, name="financing_calculate"),  # AJAX
    path("insurance/", views.insurance_view, name="insurance"),
]
