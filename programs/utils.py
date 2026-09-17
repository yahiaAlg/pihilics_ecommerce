"""
programs.utils
"""

from decimal import Decimal, ROUND_HALF_UP


def calculate_monthly_payment(vehicle_price, down_payment, term_months):
    """
    Financing page's Monthly Payment Calculator (spec 6.15): a down payment
    greater than the vehicle price is capped at the vehicle price; amount
    financed = vehicle price − down payment; monthly payment = amount
    financed ÷ term, rounded. Pure calculation, meant to back the small
    JsonResponse endpoint that recalculates live as inputs change.
    """
    vehicle_price = Decimal(vehicle_price)
    down_payment = min(Decimal(down_payment), vehicle_price)
    amount_financed = vehicle_price - down_payment
    monthly_payment = (amount_financed / Decimal(term_months)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {
        "vehicle_price": vehicle_price,
        "down_payment": down_payment,
        "amount_financed": amount_financed,
        "monthly_payment": monthly_payment,
    }
