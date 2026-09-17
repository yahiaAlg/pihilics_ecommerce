import os
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.constants import wilaya_choices

# Payment-proof uploads are the one place on this site where an anonymous
# visitor can put a file on our disk, so the accepted set is deliberately
# tiny: what a banking app actually produces (a screenshot) or exports (a
# PDF receipt). The size ceiling is generous for a phone screenshot but low
# enough that the upload can't be used as free storage.
PAYMENT_PROOF_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".webp")
PAYMENT_PROOF_CONTENT_TYPES = (
    "application/pdf", "image/jpeg", "image/png", "image/webp",
)
PAYMENT_PROOF_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_payment_proof(upload):
    """
    Rejects anything that isn't a small PDF or image.

    Both the extension and the browser-supplied content type are checked:
    neither is trustworthy on its own (an extension is just a string, and
    content_type is whatever the client claims), but requiring the two to
    agree on a short allow-list stops the obvious upload of an executable
    or archive renamed to .png, which is the realistic risk here.
    """
    extension = os.path.splitext(upload.name)[1].lower()
    if extension not in PAYMENT_PROOF_EXTENSIONS:
        raise ValidationError(
            "Upload a PDF or an image (%(allowed)s). “%(ext)s” files aren't accepted.",
            params={"allowed": ", ".join(PAYMENT_PROOF_EXTENSIONS), "ext": extension or "unknown"},
        )

    content_type = getattr(upload, "content_type", None)
    if content_type and content_type not in PAYMENT_PROOF_CONTENT_TYPES:
        raise ValidationError("That file doesn't look like a PDF or an image.")

    if upload.size and upload.size > PAYMENT_PROOF_MAX_BYTES:
        raise ValidationError(
            "That file is %(size).1f MB. Payment proofs must be under %(limit)s MB.",
            params={"size": upload.size / (1024 * 1024), "limit": PAYMENT_PROOF_MAX_BYTES // (1024 * 1024)},
        )


class OrderStatus(models.TextChoices):
    PROCESSING = "processing", "Processing"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class DeliveryMethod(models.TextChoices):
    STANDARD = "standard", "Home Delivery (à domicile)"
    EXPRESS = "express", "Express Home Delivery"
    DESK = "desk", "Stopdesk (collect from agency)"


class PaymentMethod(models.TextChoices):
    CIB = "cib", "CIB / Edahabia Card"
    BARIDIMOB = "baridimob", "BaridiMob / CCP / Bank Transfer"
    MANUAL = "manual", "Manual Order (Cash on Delivery / Bank Transfer)"


class PaymentState(models.TextChoices):
    """
    Where an order sits in the settlement cycle, tracked separately from
    OrderStatus because they answer different questions: OrderStatus is
    about fulfilment (has it shipped?), this is about money (have we been
    paid?). An order can be PROCESSING while its payment is still
    AWAITING_PROOF or PENDING, and conflating the two would mean either
    blocking fulfilment on payment or losing the payment state entirely.

    Two settlement routes share this one field:

    - BaridiMob (a transfer the customer proves with an upload, reviewed by
      a person): AWAITING_PROOF -> UNDER_REVIEW -> CONFIRMED / REJECTED
      (REJECTED re-opens uploading -- see Order.can_upload_payment_proof).
    - CIB/Edahabia (a real-time card payment through Chargily's hosted
      checkout, settled by webhook): PENDING -> CONFIRMED / FAILED /
      CANCELED / EXPIRED (all three re-open the checkout for a retry --
      see Order.can_retry_card_payment).

    NOT_REQUIRED covers Manual Order (cash on delivery / bank transfer),
    the one method that never settles through this site at all -- it's
    collected by the courier or reconciled by hand outside any queue here.
    """

    NOT_REQUIRED = "not_required", "Not Required"
    AWAITING_PROOF = "awaiting_proof", "Awaiting Payment Proof"
    UNDER_REVIEW = "under_review", "Proof Under Review"
    PENDING = "pending", "Awaiting Card Payment"
    CONFIRMED = "confirmed", "Payment Confirmed"
    REJECTED = "rejected", "Proof Rejected"
    FAILED = "failed", "Card Payment Failed"
    CANCELED = "canceled", "Card Payment Canceled"
    EXPIRED = "expired", "Checkout Expired"


class PaymentProofStatus(models.TextChoices):
    PENDING = "pending", "Pending Review"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"


class ShipmentStage(models.TextChoices):
    ORDER_PLACED = "order_placed", "Order Placed"
    MANUFACTURING = "manufacturing", "Manufacturing"
    QUALITY_CHECK = "quality_check", "Quality Check"
    SHIPPED = "shipped", "Shipped"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out for Delivery"
    DELIVERED = "delivered", "Delivered"


class Order(models.Model):
    """
    A confirmed purchase — immutable once placed except for `status` and its
    ShipmentEvent rows (BR-ORD-02). Every contact/address/pricing field
    below is a write-once snapshot taken at Checkout time (spec 8.4 note;
    BR-ORD-01), independent of later changes to the customer's saved
    Address, profile, or the live catalog. The delivery address is embedded
    directly (not FK'd to accounts.Address) so editing or deleting a saved
    address can never alter a past order.
    """

    reference = models.CharField(max_length=20, unique=True, editable=False, help_text="e.g. PHL-2026-0847")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    guest_email = models.EmailField(blank=True)
    guest_name = models.CharField(max_length=150, blank=True)
    guest_phone = models.CharField(max_length=30, blank=True)

    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PROCESSING)

    # -- Checkout Step 1: Information --
    contact_first_name = models.CharField(max_length=100)
    contact_last_name = models.CharField(max_length=100)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30)

    # -- Checkout Step 2: Delivery (embedded snapshot — BR-CHK-07) --
    delivery_street = models.CharField(max_length=255)
    delivery_city = models.CharField(max_length=100)
    delivery_postal_code = models.CharField(max_length=20)
    delivery_wilaya = models.CharField(max_length=2, choices=wilaya_choices)
    delivery_method = models.CharField(
        max_length=20, choices=DeliveryMethod.choices, default=DeliveryMethod.STANDARD
    )

    # -- Checkout Step 3: Payment --
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    save_payment_method = models.BooleanField(default=True)
    # Settlement state, set from payment_method at placement time by
    # orders.signals.initialise_payment_state and advanced only by a proof
    # being uploaded or reviewed. Deliberately *not* part of the BR-ORD-01
    # write-once snapshot: unlike every pricing/address field above, this is
    # meant to change after placement -- it is the order's payment lifecycle.
    payment_state = models.CharField(
        max_length=20, choices=PaymentState.choices, default=PaymentState.NOT_REQUIRED
    )

    # -- Chargily Pay (CIB / Edahabia) --
    #
    # Set once orders.chargily.create_checkout_for_order succeeds -- either
    # from the placement view (the common case: the customer is redirected
    # straight to Chargily) or from a retry on the order_payment page (a
    # failed/expired/canceled checkout gets a fresh one on demand). Blank
    # until then, including for every other payment method, which never
    # touch these fields at all.
    #
    # chargily_checkout_id is what a webhook's `data.id` is matched
    # against (orders.views.chargily_webhook_view) -- it, not the order's
    # own reference, is Chargily's primary key for the transaction.
    # chargily_checkout_url is kept (rather than re-derived) so a customer
    # who navigates back to order_payment before finishing can resume the
    # same checkout instead of starting a new one.
    chargily_checkout_id = models.CharField(max_length=64, blank=True, db_index=True)
    chargily_checkout_url = models.URLField(blank=True)

    # -- Pricing snapshot (BR-CHK-06) --
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    promo_code = models.ForeignKey(
        "cart.PromoCode", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    financing_plan = models.ForeignKey(
        "programs.FinancingPlan", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    insurance_tier = models.ForeignKey(
        "programs.InsuranceTier", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )

    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-placed_at"]

    def __str__(self):
        return self.reference

    def clean(self):
        if not self.user_id and not self.guest_email:
            raise ValidationError("A guest order must record a contact email (BR-ORD-04).")

    def recompute_total(self, save=False):
        """BR-CHK-06: Order Total = Subtotal - Discount + Shipping + VAT."""
        self.total = self.subtotal - self.discount_amount + self.shipping_cost + self.vat_amount
        if save:
            self.save(update_fields=["total"])
        return self.total

    @staticmethod
    def next_reference():
        """PHL-{YYYY}-{NNNN}, sequential per year (BR-ORD-06)."""
        year = date.today().year
        prefix = f"PHL-{year}-"
        last = Order.objects.filter(reference__startswith=prefix).order_by("-reference").first()
        seq = int(last.reference.rsplit("-", 1)[-1]) + 1 if last else 1
        return f"{prefix}{seq:04d}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.next_reference()
        super().save(*args, **kwargs)

    @property
    def requires_payment_proof(self):
        """Only the transfer-style method settles by uploaded proof."""
        return self.payment_method == PaymentMethod.BARIDIMOB

    @property
    def can_upload_payment_proof(self):
        """
        Whether the upload form should accept a (further) submission.

        Open while awaiting a first proof and re-opened after a rejection --
        a rejected transfer is usually a wrong amount or an unreadable
        screenshot, both of which the customer can fix and resend, the same
        way a P2P counterparty re-submits rather than starting a new trade.
        Closed once a proof is under review (so the queue can't be flooded
        with duplicates of the same payment) or confirmed, and closed on a
        cancelled order.
        """
        return (
            self.requires_payment_proof
            and self.status != OrderStatus.CANCELLED
            and self.payment_state in (PaymentState.AWAITING_PROOF, PaymentState.REJECTED)
        )

    @property
    def latest_payment_proof(self):
        return self.payment_proofs.first()  # PaymentProof.Meta orders newest-first

    @property
    def uses_card_gateway(self):
        """Only CIB/Edahabia settles through Chargily's hosted checkout."""
        return self.payment_method == PaymentMethod.CIB

    @property
    def can_resume_card_checkout(self):
        """The mirror image of can_retry_card_payment: a live checkout exists and just needs a link back to it."""
        return (
            self.uses_card_gateway
            and self.payment_state == PaymentState.PENDING
            and bool(self.chargily_checkout_url)
        )

    @property
    def can_retry_card_payment(self):
        """
        Whether order_payment needs to (re)create a Chargily Checkout
        rather than simply resuming the one already on file.

        True after FAILED/CANCELED/EXPIRED (a declined card, a closed tab,
        or a checkout that simply timed out are ordinary outcomes a
        customer can just try again from) and true when PENDING but with
        no stored checkout_url at all (the placement-time creation attempt
        itself failed, e.g. Chargily was briefly unreachable). False when
        PENDING *with* a stored URL -- that checkout is still live, and the
        view should resume it, not spend an API call creating a second
        one for the same order. False once CONFIRMED, and false on a
        cancelled order.
        """
        if not self.uses_card_gateway or self.status == OrderStatus.CANCELLED:
            return False
        if self.payment_state == PaymentState.PENDING:
            return not self.chargily_checkout_url
        return self.payment_state in (
            PaymentState.FAILED, PaymentState.CANCELED, PaymentState.EXPIRED,
        )


def payment_proof_upload_to(instance, filename):
    """
    media/payment_proofs/<order reference>/<filename>.

    Foldering by reference (rather than by date) is what makes the admin
    side workable: reconciling a transfer means opening the proofs for one
    order, including every earlier rejected attempt, and a reference-named
    folder groups exactly that set without a query.
    """
    return f"payment_proofs/{instance.order.reference}/{filename}"


class PaymentProof(models.Model):
    """
    A customer's evidence that they sent a BaridiMob / CCP / bank transfer,
    held for manual confirmation by the sales team.

    This is the escrow-style handshake the site needs because there is no
    payment gateway in scope: the customer pays out-of-band into the account
    on core.CompanyInfo, uploads the receipt here, and the order's
    payment_state moves AWAITING_PROOF -> UNDER_REVIEW. Someone in the admin
    then confirms or rejects it, which moves the order to CONFIRMED or back
    to REJECTED (re-uploadable), emailing the customer at each hop. Nothing
    auto-confirms -- a screenshot is not a settlement, and only a human
    looking at the real account statement can say the money arrived.

    Rows are append-only in spirit: a rejected attempt is kept rather than
    overwritten, so the full exchange stays auditable if a customer later
    disputes what they sent.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payment_proofs")
    file = models.FileField(
        upload_to=payment_proof_upload_to,
        validators=[validate_payment_proof],
        help_text="Screenshot or PDF receipt of the transfer (PDF, JPG, PNG or WEBP).",
    )
    original_filename = models.CharField(max_length=255, blank=True, editable=False)

    # Self-declared by the sender and never trusted as fact -- they exist so
    # the reviewer can match the claim against the bank statement quickly,
    # which is the slow part of reconciling a transfer by hand.
    amount_declared = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Amount the customer says they transferred, in DZD.",
    )
    transaction_reference = models.CharField(
        max_length=100, blank=True,
        help_text="Transfer/transaction reference shown in the customer's banking app.",
    )
    sender_note = models.TextField(blank=True, help_text="Optional message from the customer.")

    status = models.CharField(
        max_length=20, choices=PaymentProofStatus.choices, default=PaymentProofStatus.PENDING
    )
    review_note = models.TextField(
        blank=True,
        help_text="Shown to the customer verbatim when a proof is rejected — say what to fix.",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_payment_proofs",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Payment Proof"
        verbose_name_plural = "Payment Proofs"

    def __str__(self):
        return f"{self.order.reference} — {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if self.file and not self.original_filename:
            # upload_to can rename on collision; keep what the customer sent
            # so the admin sees the same filename they'd describe on the phone.
            self.original_filename = os.path.basename(self.file.name)[:255]
        super().save(*args, **kwargs)

    @property
    def is_pdf(self):
        return self.file.name.lower().endswith(".pdf")


class OrderItem(models.Model):
    """
    Write-once snapshot of a purchased line (BR-ORD-01) — product_id, name,
    unit price, and full selected options are stored directly here, never
    re-derived later from the current catalog or from parsing a display
    name (the prior prototype's defect, spec 11.3.3).
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.SET_NULL, null=True, related_name="order_items"
    )

    product_name_snapshot = models.CharField(max_length=200)
    unit_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    selected_options_snapshot = models.JSONField(
        default=dict, blank=True, help_text="{'color': ..., 'size': ..., 'upgrades': [...]}"
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity} x {self.product_name_snapshot} ({self.order.reference})"

    @property
    def line_total(self):
        return self.unit_price_snapshot * self.quantity


class ShipmentEvent(models.Model):
    """One stage in an order's shipment timeline (spec 8.4, 6.11)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="shipment_events")
    stage = models.CharField(max_length=30, choices=ShipmentStage.choices)
    carrier = models.CharField(max_length=100, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True, help_text="Null while the stage is still pending.")
    is_complete = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "stage"], name="unique_stage_per_order"),
        ]

    def __str__(self):
        state = "done" if self.is_complete else "pending"
        return f"{self.order.reference} - {self.get_stage_display()} ({state})"
