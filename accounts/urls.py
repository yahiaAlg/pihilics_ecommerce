"""
accounts.urls

Spec 6.17 (Account — one tabbed page) and 6.18 (Login/Register). Mounted
at `accounts/` by the project URLConf. All Account-tab mutations
(`profile/`, `preferences/`, `addresses/...`) are POST-only and redirect
back to the single `account/` page (PRG) rather than owning pages of
their own.
"""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("account/", views.account_view, name="account"),
    path("account/profile/", views.profile_update_view, name="profile_update"),
    path("account/preferences/", views.preferences_update_view, name="preferences_update"),
    path("account/addresses/add/", views.address_create_view, name="address_create"),
    path("account/addresses/<int:pk>/update/", views.address_update_view, name="address_update"),
    path("account/addresses/<int:pk>/delete/", views.address_delete_view, name="address_delete"),
]
