from django.db import models


class FinancingPlan(models.Model):
    """Term-based, informational payment-plan option, selectable at Checkout
    (spec 6.15; BR-CHK-08)."""

    term_months = models.PositiveSmallIntegerField(unique=True, help_text="e.g. 12, 24, 36")
    apr = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Annual percentage rate, e.g. 0.00 for 0%% APR.",
    )
    description = models.TextField(blank=True)
    zero_down_option = models.BooleanField(
        default=False, help_text='e.g. the 24-month plan\'s "zero-down" option.'
    )
    is_featured = models.BooleanField(default=False, help_text='Visually marked as "most popular".')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["term_months"]

    def __str__(self):
        return f"{self.term_months}-Month Plan ({self.apr}% APR)"


class InsuranceTierName(models.TextChoices):
    ESSENTIAL = "essential", "Essential"
    COMPREHENSIVE = "comprehensive", "Comprehensive"
    PREMIUM = "premium", "Premium"


class InsuranceTier(models.Model):
    """Tiered protection plan, selectable/bundled at Checkout (spec 6.16; BR-CHK-08)."""

    name = models.CharField(max_length=20, choices=InsuranceTierName.choices, unique=True)
    monthly_price = models.DecimalField(max_digits=8, decimal_places=2)
    features = models.JSONField(default=list, blank=True, help_text="Ordered list of included feature strings.")
    excess_amount = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="e.g. 37,000 DA excess on Comprehensive, 0 on Premium.",
    )
    is_featured = models.BooleanField(default=False, help_text='Visually marked as the "popular" tier.')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["monthly_price"]

    def __str__(self):
        return self.get_name_display()
