"""
programs.forms

Spec 6.15.3, the Financing page's Monthly Payment Calculator: "pick a
specific motorcycle model (by price)..., enter a down payment amount, and
choose a term length." Backs the calculation in programs.utils
(calculate_monthly_payment), which that module's own docstring already
anticipates being called from a small JsonResponse endpoint as the visitor
edits any field.
"""

from decimal import Decimal

from django import forms

from catalog.models import Product, ProductType

from .models import FinancingPlan


class FinancingCalculatorForm(forms.Form):
    model = forms.ModelChoiceField(
        queryset=Product.objects.filter(product_type=ProductType.MOTORCYCLE, is_active=True),
        label="Motorcycle model",
    )
    down_payment = forms.DecimalField(min_value=Decimal("0"), initial=Decimal("0"))
    term_months = forms.ModelChoiceField(
        queryset=FinancingPlan.objects.filter(is_active=True),
        to_field_name="term_months",
        label="Term length",
    )
