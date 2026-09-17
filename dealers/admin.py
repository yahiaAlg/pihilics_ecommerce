"""
dealers.admin

Spec's Dealer directory management admin section. `is_active` is edited
via the change form only (not `list_editable`) so `save_model` can enforce
the 15.1 edge case below on every deactivation.
"""

from django.contrib import admin, messages

from .models import Dealer


@admin.register(Dealer)
class DealerAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "wilaya", "phone", "is_active")
    list_filter = ("wilaya", "is_active")
    search_fields = ("name", "city", "address")
    prepopulated_fields = {"slug": ("name",)}

    def save_model(self, request, obj, form, change):
        """Edge case 15.1: "Dealer deactivated with pending bookings — system
        blocks deactivation until pending bookings are reassigned or
        resolved." Reactivating is always allowed."""
        if change and not obj.is_active and obj.has_pending_bookings():
            obj.is_active = True
            self.message_user(
                request,
                f'"{obj.name}" was kept active — it still has pending bookings; '
                "reassign or resolve them first.",
                level=messages.WARNING,
            )
        super().save_model(request, obj, form, change)
