"""
content.urls

Spec 9 (Content and Informational Pages) plus 6.20's Help Center. Mounted
at the site root by the project URLConf — Home therefore owns `""`.
`page_not_found_view` is wired as `handler404` in the project URLConf, not
routed here.
"""

from django.urls import path

from . import views

app_name = "content"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("about/", views.about_view, name="about"),
    path("stories/", views.story_list_view, name="story_list"),
    path("stories/<slug:slug>/", views.story_detail_view, name="story_detail"),
    path("support/", views.support_view, name="support"),
    path("support/faq-search/", views.faq_search_json, name="faq_search"),  # AJAX
    path("terms/", views.terms_view, name="terms"),
    path("privacy/", views.privacy_view, name="privacy"),
]
