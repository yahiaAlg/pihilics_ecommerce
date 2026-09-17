"""
core.admin

`CompanyInfo` is a singleton holding the business's own legal/company
identity, used on printable invoices and the About/legal pages — and, via
`trade_name`, the brand name rendered site-wide. The admin below hides
"Add" once a row exists and always routes to the one existing row's change
page, rather than letting a second row be created.
"""

from django.contrib import admin
from django.shortcuts import redirect

from .models import CompanyInfo, ShippingZone, VATRate


@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Brand", {
            "fields": ("trade_name", "tagline", "logo"),
            "description": "The public-facing brand. `trade_name` is rendered as the site "
                           "name everywhere (header, page titles, footer, invoices), so "
                           "renaming the business here renames it site-wide.",
        }),
        ("Legal Identity", {"fields": ("legal_name", "registration_number", "vat_number")}),
        ("Registered Address", {"fields": ("street", "city", "postal_code", "wilaya")}),
        ("Contact", {"fields": ("email", "phone", "website")}),
        ("Banking", {"fields": ("bank_name", "iban", "bic_swift")}),
        ("Invoicing Defaults", {"fields": ("default_currency", "default_vat_rate", "invoice_footer_note")}),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        # Singleton (Model.save() enforces pk=1) — only ever one row.
        return not CompanyInfo.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Skip the changelist entirely and go straight to the one row,
        # creating it (via get_solo's defaults) the first time it's opened.
        obj = CompanyInfo.get_solo()
        return redirect("admin:core_companyinfo_change", obj.pk)


@admin.register(VATRate)
class VATRateAdmin(admin.ModelAdmin):
    list_display = ("wilaya", "rate_percent", "is_active")
    list_filter = ("is_active",)
    list_editable = ("rate_percent", "is_active")
    search_fields = ("wilaya",)
    ordering = ("wilaya",)


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    """
    Per-wilaya delivery pricing. `list_editable` on the fees and the active
    flag makes the common job -- re-pricing a batch of wilayas after a
    courier rate change, or suspending delivery to one -- a single
    changelist edit rather than 58 trips through the change form.
    """

    list_display = (
        "wilaya", "home_fee", "desk_fee", "delivery_days_min", "delivery_days_max", "is_active",
    )
    list_filter = ("is_active",)
    list_editable = ("home_fee", "desk_fee", "delivery_days_min", "delivery_days_max", "is_active")
    search_fields = ("wilaya",)
    ordering = ("wilaya",)
