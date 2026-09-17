"""
programs.admin

Spec 6.15/6.16: Financing plans and Insurance tiers, managed as plain
business records (both selectable at Checkout — BR-CHK-08).
"""

from django.contrib import admin

from .models import FinancingPlan, InsuranceTier


@admin.register(FinancingPlan)
class FinancingPlanAdmin(admin.ModelAdmin):
    list_display = ("term_months", "apr", "zero_down_option", "is_featured", "is_active")
    list_filter = ("zero_down_option", "is_featured", "is_active")
    list_editable = ("apr", "is_featured", "is_active")
    ordering = ("term_months",)


@admin.register(InsuranceTier)
class InsuranceTierAdmin(admin.ModelAdmin):
    list_display = ("name", "monthly_price", "excess_amount", "is_featured", "is_active")
    list_filter = ("is_featured", "is_active")
    list_editable = ("monthly_price", "is_featured", "is_active")
    ordering = ("monthly_price",)
