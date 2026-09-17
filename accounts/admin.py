"""
accounts.admin

Spec's User & role management admin section, plus "Django's built-in User
model with a OneToOne Profile relationship": rather than a separate
UserProfile admin page, the profile (role, dealer assignment, phone,
preferences) is edited inline on the standard User change page.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from .models import Address, GarageEntry, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profile"
    fk_name = "user"
    fields = (
        "role", "dealer", "phone", "date_of_birth", "preferred_language",
        "marketing_opt_in", "order_notifications_opt_in", "promo_opt_in",
    )


class UserAdmin(DjangoUserAdmin):
    inlines = (UserProfileInline,)
    list_display = DjangoUserAdmin.list_display + ("role",)
    list_select_related = ("profile",)

    @admin.display(description="Role")
    def role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, "profile") else "—"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "label", "street", "city", "wilaya", "is_default")
    list_filter = ("wilaya", "is_default")
    search_fields = ("user__username", "user__email", "street", "city", "postal_code")
    autocomplete_fields = ("user",)


@admin.register(GarageEntry)
class GarageEntryAdmin(admin.ModelAdmin):
    list_display = ("vin", "product", "user", "warranty_active", "service_due_at", "added_at")
    list_filter = ("warranty_active",)
    search_fields = ("vin", "user__username", "user__email", "product__name")
    autocomplete_fields = ("user", "product")
    raw_id_fields = ("order_item",)
    readonly_fields = ("added_at",)
