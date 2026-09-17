from django.db import models

from core.constants import (
    DEFAULT_EXPRESS_SHIPPING_SURCHARGE,
    DEFAULT_FREE_SHIPPING_THRESHOLD,
    DEFAULT_STANDARD_SHIPPING_FEE,
    wilaya_choices,
)


class Wilaya(models.Model):
    """
    One Algerian province, and the single source of truth for every
    "which wilaya?" dropdown on the site -- Address, Order.delivery_wilaya,
    Dealer, CompanyInfo, ShippingZone and VATRate all take their choices
    from this table via core.constants.wilaya_choices.

    Previously this was a hardcoded 58-entry list in core/constants.py.
    It is a table now for one concrete reason: the list genuinely changes.
    Algeria's 2026 reform takes the official count to 69 from January 2027,
    couriers will adopt the new codes on their own schedule, and in the
    meantime a wilaya we simply can't deliver to needs to come *off* the
    dropdown for a while. All three are admin edits now, not deploys.

    `is_active` is how you withdraw one without deleting it: existing
    orders keep resolving their stored code to a name, but nobody can pick
    it at checkout.
    """

    code = models.CharField(
        max_length=2, unique=True,
        help_text="Official 2-digit wilaya code (01-58) as used by the courier networks.",
    )
    name = models.CharField(max_length=100, help_text="Display name shown in dropdowns.")
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to withdraw this wilaya from every dropdown without deleting it "
                  "(existing orders keep resolving its name).",
    )

    class Meta:
        verbose_name = "Wilaya"
        verbose_name_plural = "Wilayas"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Language(models.Model):
    """
    An interface language offered on Account > Preferences (spec 6.17).

    A table rather than a constant so a language can be added or pulled
    the moment its translations are (or stop being) ready, which is
    exactly the sort of thing that shouldn't wait for a release.
    """

    code = models.CharField(
        max_length=5, unique=True, help_text='Language code, e.g. "fr", "ar", "kab".'
    )
    name = models.CharField(max_length=100, help_text="Name shown in the selector, in that language.")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(
        default=0, help_text="Lower numbers appear first in the selector."
    )

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class CheckoutSettings(models.Model):
    """
    Singleton holding the checkout rules that used to be Decimal literals
    in core/constants.py, plus which online payment routes are currently
    open for business.

    The pricing half exists because these numbers are business decisions
    with a short shelf life. The free-shipping threshold in particular is
    priced against the catalogue: set it at 150,000 DZD in a shop selling
    motorcycles priced in the millions and *every* order ships free, which
    makes the paid delivery tiers decorative. Whoever notices that should
    be able to fix it in the admin, in a minute, rather than filing a
    change request against a Python file.

    The payment half (`card_payments_enabled`) is the kill switch for the
    CIB/Edahabia route. The whole Chargily integration stays wired up and
    functional behind it -- see orders/chargily.py -- so turning cards on
    once Chargily has approved the account and the keys are in `.env` is
    a single checkbox, with no code to re-enable.
    """

    free_shipping_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, default=DEFAULT_FREE_SHIPPING_THRESHOLD,
        help_text="Orders at or above this subtotal (DZD) ship free, whichever delivery "
                  "method was chosen. Set it high enough that it doesn't swallow every order.",
    )
    standard_shipping_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=DEFAULT_STANDARD_SHIPPING_FEE,
        help_text="Flat home-delivery fee (DZD) used for wilayas with no Shipping Zone row of their own.",
    )
    express_shipping_surcharge = models.DecimalField(
        max_digits=10, decimal_places=2, default=DEFAULT_EXPRESS_SHIPPING_SURCHARGE,
        help_text="Added on top of the home-delivery fee for Express. Never charged on a free-shipping order.",
    )

    card_payments_enabled = models.BooleanField(
        default=False, verbose_name="CIB / Edahabia card payments enabled",
        help_text="Off until Chargily has verified the account and CHARGILY_KEY/CHARGILY_SECRET are set. "
                  "While off, the card option is shown at checkout as 'coming soon' and cannot be "
                  "selected (server-side too, not just visually).",
    )
    card_payments_unavailable_note = models.CharField(
        max_length=255, blank=True,
        default="Card payments are coming soon — please use one of the options below.",
        help_text="Shown under the greyed-out card option while card payments are disabled.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Checkout Settings"
        verbose_name_plural = "Checkout Settings"

    def __str__(self):
        return "Checkout Settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton row
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Singleton: configuration, not deletable data.
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def get_safe(cls):
        """
        get_solo(), but survivable before the table exists (fresh `migrate`,
        a check run on an empty database). Returns an unsaved instance
        carrying the field defaults rather than raising, so pricing helpers
        and checkout templates never depend on migration order.
        """
        try:
            return cls.get_solo()
        except Exception:
            return cls()


class CompanyInfo(models.Model):
    """
    Singleton record holding the business's own legal/company identity:
    registration details, NIF/TVA numbers, and banking info. Used to populate
    printable invoices/order confirmations (see `orders` app) and any
    legal-footer or "about the company" content site-wide. Enforced as a
    single row (pk=1).

    `trade_name` is the single source of truth for the site-wide brand name
    (rendered everywhere via core.context_processors.site_identity), so the
    business can be renamed from the admin with no code change.
    """

    legal_name = models.CharField(max_length=255, help_text="Registered legal company name.")
    trade_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Public-facing brand name shown site-wide (header, footer, page titles, invoices).",
    )
    tagline = models.CharField(
        max_length=255,
        blank=True,
        help_text="Short brand line used in page meta descriptions and the footer.",
    )
    registration_number = models.CharField(max_length=100, help_text="Registre de Commerce (RC) number.")
    vat_number = models.CharField(max_length=50, verbose_name="NIF / TVA number")

    street = models.CharField(max_length=255)
    city = models.CharField(max_length=100, help_text="Commune / city.")
    postal_code = models.CharField(max_length=20, help_text="5-digit Algerian postal code.")
    wilaya = models.CharField(max_length=2, choices=wilaya_choices, default="16")

    email = models.EmailField()
    phone = models.CharField(max_length=30)
    website = models.URLField(blank=True)

    bank_name = models.CharField(max_length=150, blank=True)
    iban = models.CharField(max_length=34, blank=True)
    bic_swift = models.CharField(max_length=11, blank=True, verbose_name="BIC / SWIFT")

    # -- Sales department receiving account (shown to the customer) --------
    #
    # Distinct from the bank_name/iban/bic_swift block above, which is the
    # company's own banking identity printed on invoices and never shown
    # mid-checkout. These are the *destination* details a BaridiMob / CCP
    # customer types into their banking app to pay us, so they are rendered
    # straight onto the payment page and into the payment-instructions
    # email. Kept on this singleton, rather than hardcoded in a template,
    # because the receiving account is the one detail here that genuinely
    # changes (a new account, a corrected RIP) and must be fixable from the
    # admin without a deploy -- getting it wrong sends customer money to the
    # wrong place.
    #
    # Blank by default: the BaridiMob option hides itself at checkout until
    # a RIP or CCP number is filled in (see CompanyInfo.has_sales_account),
    # so a fresh install can never show an empty "transfer to:" box.
    sales_account_holder = models.CharField(
        max_length=255, blank=True,
        help_text="Name the account is registered under, exactly as it appears to the sender.",
    )
    sales_bank_name = models.CharField(
        max_length=150, blank=True,
        help_text="Bank or institution holding the sales account (e.g. Algérie Poste, BNA).",
    )
    sales_rip = models.CharField(
        max_length=25, blank=True, verbose_name="Sales RIP (BaridiMob)",
        help_text="20-digit RIP used for BaridiMob transfers. Shown to customers at checkout.",
    )
    sales_ccp_number = models.CharField(
        max_length=25, blank=True, verbose_name="Sales CCP number",
        help_text="CCP account number including its 2-digit key (e.g. 1234567 89).",
    )
    sales_payment_email = models.EmailField(
        blank=True,
        help_text="Where customers send payment proof if the upload fails. "
                  "Falls back to settings.ADMIN_NOTIFICATION_EMAIL when empty.",
    )
    sales_payment_note = models.TextField(
        blank=True,
        help_text="Optional extra instructions shown under the transfer details "
                  "(e.g. what reference to put on the transfer).",
    )

    logo = models.ImageField(upload_to="company/", blank=True, null=True)

    # Social links, shown site-wide in the footer and on the Support page's
    # "Follow Us" block. Both consumers previously hardcoded `href="#"` --
    # CompanyInfo is the one singleton already wired into every template via
    # `core.context_processors.site_identity`, so it's the natural home for
    # brand-identity links that aren't specific to any one page.
    instagram_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)

    invoice_footer_note = models.TextField(
        blank=True,
        help_text="Free-text note printed at the bottom of invoices/receipts (e.g. legal disclaimers).",
    )

    default_currency = models.CharField(max_length=3, default="DZD")
    default_vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=19.00,
        help_text="Fallback TVA rate (Algeria's standard rate is 19%) used when the "
        "destination wilaya has no explicit VATRate row.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Information"
        verbose_name_plural = "Company Information"

    def __str__(self):
        return self.trade_name or self.legal_name

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton row
        super().save(*args, **kwargs)

    @property
    def has_sales_account(self):
        """
        True once there is somewhere for a customer to actually send money.

        Checkout gates the BaridiMob option on this: offering "transfer to
        us" with no RIP or CCP to transfer *to* would strand the order at
        the payment step with nothing the customer could do about it.
        """
        return bool(self.sales_rip or self.sales_ccp_number)

    @property
    def payment_proof_email(self):
        """
        Mailbox printed as the manual fallback ("if the upload fails, send
        it here"). Prefers the sales address so proofs land with the people
        who reconcile them, and falls back to the internal alert inbox so
        the fallback line is never blank.
        """
        from django.conf import settings

        return self.sales_payment_email or settings.ADMIN_NOTIFICATION_EMAIL

    def delete(self, *args, **kwargs):
        # Singleton: company info is configuration, not deletable data.
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "legal_name": "Pihilics SARL",
                "trade_name": "Pihilics",
                "tagline": "Bikes built for Algerian roads.",
                "registration_number": "PENDING",
                "vat_number": "PENDING",
                "street": "",
                "city": "",
                "postal_code": "",
                "email": "contact@pihilics.dz",
                "phone": "",
            },
        )
        return obj


class VATRate(models.Model):
    """
    Destination-based TVA rate table (BR-CHK-04: VAT is calculated on
    (subtotal - discount) using the rate for the selected shipping
    destination). Looked up by Checkout using the delivery wilaya chosen in
    Step 2.

    Algeria applies one national TVA rate (19% standard, 9% reduced), so in
    practice CompanyInfo.default_vat_rate covers every order and this table
    stays empty. It is kept per-wilaya rather than dropped because the
    southern wilayas carry statutory TVA relief on some goods, and that
    exemption is exactly a "this wilaya bills a different rate" row.
    """

    wilaya = models.CharField(max_length=2, choices=wilaya_choices, unique=True)
    rate_percent = models.DecimalField(max_digits=5, decimal_places=2, help_text="e.g. 19.00 for 19%")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "TVA Rate"
        verbose_name_plural = "TVA Rates"
        ordering = ["wilaya"]

    def __str__(self):
        return f"{self.get_wilaya_display()} - {self.rate_percent}%"


class ShippingZone(models.Model):
    """
    Per-wilaya delivery pricing and lead time.

    Replaces the old flat "one fee for all of Europe" rule: every Algerian
    courier network prices by wilaya (and charges more for the south), and
    quotes a different number of days per wilaya, so the fee can't be a
    single constant anymore. core.utils.get_shipping_quote reads this table
    and falls back to CheckoutSettings.standard_shipping_fee when a wilaya
    has no row yet, which keeps checkout working on a fresh install.

    `desk_fee` supports "stopdesk" delivery -- collection from the courier's
    own agency, which is how most Algerian e-commerce delivery actually
    happens and is always cheaper than delivery to the door (`home_fee`).
    """

    wilaya = models.CharField(max_length=2, choices=wilaya_choices, unique=True)
    home_fee = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Cost of delivery to the customer's address (à domicile), in DZD.",
    )
    desk_fee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Cost of collection from the courier's agency (stopdesk), in DZD. "
                  "Leave empty if stopdesk isn't offered in this wilaya.",
    )
    delivery_days_min = models.PositiveSmallIntegerField(default=2)
    delivery_days_max = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to stop offering delivery to this wilaya without deleting its pricing.",
    )

    class Meta:
        verbose_name = "Shipping Zone"
        verbose_name_plural = "Shipping Zones"
        ordering = ["wilaya"]

    def __str__(self):
        return f"{self.get_wilaya_display()} - {self.home_fee} DZD"

    @property
    def delivery_estimate(self):
        if self.delivery_days_min == self.delivery_days_max:
            return f"{self.delivery_days_min} days"
        return f"{self.delivery_days_min}-{self.delivery_days_max} days"
