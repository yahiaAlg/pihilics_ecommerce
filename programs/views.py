"""
programs.views

Spec 6.15 (Financing) and 6.16 (Insurance).
"""

from django.http import JsonResponse
from django.shortcuts import render

from .forms import FinancingCalculatorForm
from .models import FinancingPlan, InsuranceTier, InsuranceTierName
from .utils import calculate_monthly_payment
from catalog.templatetags.catalog_extras import _currency_affixes

# The static build's Insurance page shows a one-line summary under each
# tier's price ("Third-party liability and theft protection.", etc.).
# `InsuranceTier` (unlike `FinancingPlan`, which has its own `description`
# field) has no matching field for this. It's a fixed 3-value enum, so --
# same treatment as the availability-badge CSS mapping -- this is an
# explicit dict of the reference's own copy, not a new model field or an
# invented per-tier calculation.
INSURANCE_TIER_BLURBS = {
    InsuranceTierName.ESSENTIAL: "Third-party liability and theft protection.",
    InsuranceTierName.COMPREHENSIVE: "Full coverage including battery and accidental damage.",
    InsuranceTierName.PREMIUM: "Everything covered, including gear and roadside.",
}


def financing_view(request):
    """Spec 6.15: financing plan cards plus the Monthly Payment Calculator (initial render; live edits use the AJAX endpoint below)."""
    form = FinancingCalculatorForm(request.GET or None)
    result = None
    if form.is_valid():
        result = calculate_monthly_payment(
            vehicle_price=form.cleaned_data["model"].price,
            down_payment=form.cleaned_data["down_payment"],
            term_months=form.cleaned_data["term_months"].term_months,
        )

    # The calculator formats its running total client-side, so it needs the
    # same currency affixes the server-side `arko_price` filter uses --
    # otherwise a DZD site would still print "€" beside every live figure.
    prefix, suffix = _currency_affixes()

    return render(request, "programs/financing.html", {
        "plans": FinancingPlan.objects.filter(is_active=True),
        "form": form,
        "result": result,
        "currency_affixes": {"prefix": prefix, "suffix": suffix},
    })


def financing_calculate_json(request):
    """AJAX: the calculator's live recalculation as any field changes (programs.utils docstring)."""
    form = FinancingCalculatorForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    result = calculate_monthly_payment(
        vehicle_price=form.cleaned_data["model"].price,
        down_payment=form.cleaned_data["down_payment"],
        term_months=form.cleaned_data["term_months"].term_months,
    )
    return JsonResponse({key: str(value) for key, value in result.items()})


def insurance_view(request):
    """Spec 6.16: the three insurance tiers."""
    tiers = list(InsuranceTier.objects.filter(is_active=True))
    for tier in tiers:
        tier.blurb = INSURANCE_TIER_BLURBS.get(tier.name, "")

    return render(request, "programs/insurance.html", {
        "tiers": tiers,
    })
