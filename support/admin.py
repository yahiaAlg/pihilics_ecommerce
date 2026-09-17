"""
support.admin

Contact-form submissions (spec 6.20; both the Support and Contact pages
route into this one model), routed to Store Administrators for triage.
"""

from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "email", "subject", "is_resolved", "created_at")
    list_filter = ("department", "is_resolved")
    list_editable = ("is_resolved",)
    search_fields = ("name", "email", "subject", "message")
    readonly_fields = ("name", "email", "department", "subject", "message", "user", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        # Only ever created by a customer submitting the Contact/Support form.
        return False
