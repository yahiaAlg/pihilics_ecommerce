"""
content.admin

Spec's Content management admin section (FAQ, Stories, and the CMS-editable
Home/About/Support/404 page copy plus the two legal documents).
"""

from django.contrib import admin
from django.shortcuts import redirect

from .models import (
    AboutPageContent,
    FAQEntry,
    HomeCarouselSlide,
    HomeHeroStat,
    HomeMarqueeItem,
    HomePageContent,
    HomeShowcasePanel,
    LegalDocument,
    NotFoundPageContent,
    Story,
    SupportPageContent,
    TeamMember,
    TimelineEvent,
    ValueProp,
)


class SingletonContentAdminMixin:
    """Same treatment as core.admin.CompanyInfoAdmin: hide "Add" once the
    one row exists, forbid delete, and skip the changelist entirely in
    favour of that row's change page -- there is never a second one to
    choose between."""

    def has_add_permission(self, request):
        return not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = self.model.get_solo()
        return redirect(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change", obj.pk)


@admin.register(FAQEntry)
class FAQEntryAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "sort_order", "is_active")
    list_filter = ("category", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("question", "answer")
    ordering = ("category", "sort_order")


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ("title", "is_published", "published_at", "created_at")
    list_filter = ("is_published",)
    list_editable = ("is_published",)
    search_fields = ("title", "excerpt", "body")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"
    readonly_fields = ("created_at",)


class HomeHeroStatInline(admin.TabularInline):
    model = HomeHeroStat
    extra = 1


class HomeMarqueeItemInline(admin.TabularInline):
    model = HomeMarqueeItem
    extra = 1


class HomeCarouselSlideInline(admin.TabularInline):
    model = HomeCarouselSlide
    extra = 1


class HomeShowcasePanelInline(admin.TabularInline):
    model = HomeShowcasePanel
    extra = 1


@admin.register(HomePageContent)
class HomePageContentAdmin(SingletonContentAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Hero", {"fields": ("hero_eyebrow", "hero_title_line1", "hero_title_line2", "hero_subtitle", "hero_image")}),
        ("Battery Swap", {"fields": (
            "battery_eyebrow", "battery_title_line1", "battery_title_line2",
            "battery_body", "battery_image",
        )}),
        ("Cinematic Banner", {"fields": ("cine_title_line1", "cine_title_line2", "cine_image", "cine_video")}),
        ("Compare Models CTA", {"fields": ("compare_eyebrow", "compare_title", "compare_body")}),
        ("Test Ride CTA", {"fields": ("testride_eyebrow", "testride_title", "testride_body")}),
        ("Final CTA", {"fields": (
            "final_cta_title_line1", "final_cta_title_line2",
            "final_cta_body", "final_cta_image",
        )}),
    )
    inlines = (HomeHeroStatInline, HomeMarqueeItemInline, HomeCarouselSlideInline, HomeShowcasePanelInline)


class ValuePropInline(admin.TabularInline):
    model = ValueProp
    extra = 1


class TimelineEventInline(admin.TabularInline):
    model = TimelineEvent
    extra = 1


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 1


@admin.register(AboutPageContent)
class AboutPageContentAdmin(SingletonContentAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Hero", {"fields": ("hero_eyebrow", "hero_title_line1", "hero_title_line2", "hero_subtitle", "hero_image")}),
        ("Mission", {"fields": (
            "mission_eyebrow", "mission_title",
            "mission_paragraph_1", "mission_paragraph_2", "mission_paragraph_3",
            "mission_image",
        )}),
        ("By the Numbers", {"fields": (
            "stats_eyebrow", "stats_title",
            "riders_stat_value", "riders_stat_label",
            "co2_stat_value", "co2_stat_label",
        )}),
        ("Our Values", {"fields": ("values_eyebrow", "values_title")}),
        ("Our Timeline", {"fields": ("timeline_eyebrow", "timeline_title")}),
        ("Leadership", {"fields": ("team_eyebrow", "team_title")}),
        ("Join the Ride CTA", {"fields": ("cta_eyebrow", "cta_title", "cta_body")}),
    )
    inlines = (ValuePropInline, TimelineEventInline, TeamMemberInline)


@admin.register(SupportPageContent)
class SupportPageContentAdmin(SingletonContentAdminMixin, admin.ModelAdmin):
    fieldsets = (
        ("Email", {"fields": ("email_support", "email_sales", "email_response_note")}),
        ("Phone & Chat", {"fields": ("hours_text", "livechat_text")}),
    )


@admin.register(NotFoundPageContent)
class NotFoundPageContentAdmin(SingletonContentAdminMixin, admin.ModelAdmin):
    fieldsets = (("404 Page", {"fields": ("heading", "body")}),)


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "last_updated")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "body")
