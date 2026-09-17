"""
orders.admin

Spec's Order management admin section ("view/filter/update status,
refunds"). BR-ORD-02 ("Orders are immutable except for `status` and their
associated ShipmentEvent records") is enforced directly in the admin: every
Order field except `status` is read-only, orders can't be created here
(they only ever come from Checkout — orders.views module docstring) or
deleted, and `OrderItem` rows are a read-only inline. `ShipmentEvent` is
the one related record Store Admins actively author, to drive the Order
Tracking page.

The "refunds" ask has no separate refund/payment-gateway model in the
spec's data model (Chapter 8) or scope (Chapter 4 lists payment processing
under Out of Scope integrations), so it's realized as the one refund-like
action the data model does support: cancelling an order. The
`cancel_selected_orders` action below saves each Order individually
(rather than a bulk `.update()`) specifically so `orders.signals.
restore_stock_on_cancellation` fires per row, same as any other status
change into CANCELLED (BR-ORD-03).

PaymentProofAdmin is the human half of the BaridiMob settlement flow.
Because there is no gateway to ask, "has this customer paid?" is a
question only a person comparing an uploaded receipt against the real
account statement can answer, so this admin is where that answer gets
recorded. Its two actions save each row individually for the same reason
the cancel action does: `orders.signals.apply_payment_proof_effects` is
what actually advances the order's payment_state and emails the customer,
and a bulk `.update()` would skip it, silently leaving customers waiting
on an email that was never sent.
"""

from django.contrib import admin, messages
from django.utils.html import format_html

from .models import (
    Order,
    OrderItem,
    OrderStatus,
    PaymentProof,
    PaymentProofStatus,
    ShipmentEvent,
)

ORDER_READONLY_FIELDS = (
    "reference", "user", "guest_email", "guest_name", "guest_phone",
    "contact_first_name", "contact_last_name", "contact_email", "contact_phone",
    "delivery_street", "delivery_city", "delivery_postal_code", "delivery_wilaya", "delivery_method",
    "payment_method", "save_payment_method", "payment_state",
    "chargily_checkout_id", "chargily_checkout_url",
    "subtotal", "shipping_cost", "vat_amount", "discount_amount", "total",
    "promo_code", "financing_plan", "insurance_tier",
    "placed_at", "updated_at", "cancelled_at",
)


class OrderItemInline(admin.TabularInline):
    """Read-only: BR-ORD-01 snapshots are write-once at Checkout, never edited after."""

    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product", "product_name_snapshot", "unit_price_snapshot", "quantity", "line_total", "selected_options_snapshot")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class ShipmentEventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0
    fields = ("stage", "carrier", "tracking_number", "occurred_at", "is_complete", "sort_order")


def proof_file_link(obj):
    """Opens the uploaded receipt in a new tab — the one thing a reviewer always needs."""
    if not obj.file:
        return "—"
    return format_html(
        '<a href="{}" target="_blank" rel="noopener">{}</a>',
        obj.file.url, obj.original_filename or "Open file",
    )


class PaymentProofInline(admin.TabularInline):
    """
    Every proof this order has ever had, newest first, including rejected
    attempts — the history is the audit trail for a transfer that was
    argued about, so it's shown in full rather than only the live one.

    `status` and `review_note` are the only editable fields: changing them
    is exactly the review decision, and saving fires the signal that
    advances the order and emails the customer. Adding a proof by hand is
    disabled — proofs come from the customer, and a fabricated one would
    email them a confirmation for a payment they never made.
    """

    model = PaymentProof
    extra = 0
    can_delete = False
    fields = ("file_link", "amount_declared", "transaction_reference", "sender_note",
              "status", "review_note", "reviewed_by", "uploaded_at")
    readonly_fields = ("file_link", "amount_declared", "transaction_reference",
                       "sender_note", "reviewed_by", "uploaded_at")

    @admin.display(description="Proof")
    def file_link(self, obj):
        return proof_file_link(obj)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "contact_name", "status", "payment_state", "total", "delivery_wilaya", "placed_at")
    list_filter = ("status", "payment_state", "delivery_method", "payment_method", "delivery_wilaya")
    search_fields = ("reference", "contact_email", "contact_first_name", "contact_last_name", "guest_email", "guest_name")
    readonly_fields = ORDER_READONLY_FIELDS
    fieldsets = (
        ("Order", {"fields": ("reference", "status", "placed_at", "updated_at", "cancelled_at")}),
        ("Customer", {"fields": (
            "user", "guest_email", "guest_name", "guest_phone",
            "contact_first_name", "contact_last_name", "contact_email", "contact_phone",
        )}),
        ("Delivery", {"fields": ("delivery_street", "delivery_city", "delivery_postal_code", "delivery_wilaya", "delivery_method")}),
        ("Payment", {
            "fields": (
                "payment_method", "payment_state", "save_payment_method",
                "chargily_checkout_id", "chargily_checkout_url",
                "financing_plan", "insurance_tier",
            ),
            "description": "Payment state is never edited here directly — for BaridiMob it's "
                           "advanced by confirming/rejecting a proof below, and for CIB/Edahabia "
                           "it's advanced by Chargily's own webhook the moment the customer pays "
                           "(or the checkout fails/expires). The customer is emailed automatically "
                           "either way.",
        }),
        ("Pricing (BR-CHK-06 snapshot)", {"fields": ("subtotal", "discount_amount", "shipping_cost", "vat_amount", "total", "promo_code")}),
    )
    inlines = [OrderItemInline, ShipmentEventInline, PaymentProofInline]
    actions = ["cancel_selected_orders"]
    date_hierarchy = "placed_at"

    @admin.display(description="Customer")
    def contact_name(self, obj):
        return f"{obj.contact_first_name} {obj.contact_last_name}"

    def has_add_permission(self, request):
        # Orders are only ever created, complete, through Checkout (BR-ORD-01/02).
        return False

    def has_delete_permission(self, request, obj=None):
        # Immutable financial record (BR-ORD-02); cancel instead of deleting.
        return False

    @admin.action(description="Cancel selected orders (restores stock)")
    def cancel_selected_orders(self, request, queryset):
        cancelled = 0
        for order in queryset.exclude(status=OrderStatus.CANCELLED):
            order.status = OrderStatus.CANCELLED
            order.save(update_fields=["status", "cancelled_at"])
            cancelled += 1
        self.message_user(request, f"{cancelled} order(s) cancelled; their stock has been restored.", level=messages.SUCCESS)


@admin.register(PaymentProof)
class PaymentProofAdmin(admin.ModelAdmin):
    """
    The review queue. Defaults to showing pending proofs first so the
    landing view is the work: everything waiting on a human decision.
    """

    list_display = ("order_reference", "status", "amount_declared", "declared_matches_total",
                    "transaction_reference", "file_link", "uploaded_at", "reviewed_by")
    list_filter = ("status", "uploaded_at")
    search_fields = ("order__reference", "order__contact_email", "transaction_reference",
                     "original_filename")
    readonly_fields = ("order", "file_link", "file", "original_filename", "amount_declared",
                       "transaction_reference", "sender_note", "uploaded_at", "reviewed_by",
                       "reviewed_at")
    fieldsets = (
        ("Order", {"fields": ("order", "uploaded_at")}),
        ("What the customer sent", {
            "fields": ("file_link", "file", "original_filename", "amount_declared",
                       "transaction_reference", "sender_note"),
        }),
        ("Decision", {
            "fields": ("status", "review_note", "reviewed_by", "reviewed_at"),
            "description": "Saving a decision emails the customer immediately. A rejection "
                           "sends them the review note verbatim and re-opens uploading, so "
                           "write what they need to fix.",
        }),
    )
    actions = ["confirm_selected_proofs", "reject_selected_proofs"]
    date_hierarchy = "uploaded_at"
    ordering = ("status", "-uploaded_at")  # "confirmed" < "pending" < "rejected" alphabetically

    @admin.display(description="Order", ordering="order__reference")
    def order_reference(self, obj):
        return obj.order.reference

    @admin.display(description="Proof")
    def file_link(self, obj):
        return proof_file_link(obj)

    @admin.display(description="Matches total", boolean=True)
    def declared_matches_total(self, obj):
        """
        The first thing a reviewer checks, surfaced in the list so obvious
        mismatches (wrong amount, partial transfer) can be spotted without
        opening each row. Only a hint — a declared amount is the customer's
        claim, and the bank statement is still the authority.
        """
        if obj.amount_declared is None:
            return None
        return obj.amount_declared == obj.order.total

    def has_add_permission(self, request):
        # Proofs are uploaded by customers (orders.views.order_payment_view).
        return False

    def has_delete_permission(self, request, obj=None):
        # Financial audit trail: a rejected or superseded proof is kept.
        return False

    def save_model(self, request, obj, form, change):
        """Records who made the call, since the customer-facing outcome is attributable to a person."""
        if "status" in getattr(form, "changed_data", []) and obj.status != PaymentProofStatus.PENDING:
            obj.reviewed_by = request.user
        super().save_model(request, obj, form, change)

    def _apply_decision(self, request, queryset, status, verb):
        """
        Shared body for both actions. Saves row by row (never `.update()`)
        so orders.signals.apply_payment_proof_effects fires for each one —
        that signal, not this action, is what advances the order and sends
        the customer's email.
        """
        changed = 0
        for proof in queryset.exclude(status=status):
            proof.status = status
            proof.reviewed_by = request.user
            proof.save()
            changed += 1
        skipped = queryset.count() - changed
        self.message_user(
            request,
            f"{changed} proof(s) {verb}; the customer has been emailed."
            + (f" {skipped} were already {verb}." if skipped else ""),
            level=messages.SUCCESS if changed else messages.WARNING,
        )

    @admin.action(description="Confirm payment (emails the customer)")
    def confirm_selected_proofs(self, request, queryset):
        self._apply_decision(request, queryset, PaymentProofStatus.CONFIRMED, "confirmed")

    @admin.action(description="Reject proof (emails the customer, re-opens upload)")
    def reject_selected_proofs(self, request, queryset):
        """
        Note this rejects without a per-row note — the bulk path is for
        clear-cut cases. Rejecting from the row's own page lets you write
        the note the customer actually receives, which is nearly always
        the kinder route.
        """
        self._apply_decision(request, queryset, PaymentProofStatus.REJECTED, "rejected")
