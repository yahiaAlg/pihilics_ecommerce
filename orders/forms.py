"""
orders.forms

Spec 6.9 (Checkout's 4-step flow) and 6.11 (Order history). Checkout is
split into one form per step (Information / Delivery / Payment) to mirror
the stepper UI (spec 6.9: "Back"/"Continue" between steps); the Review step
(step 4) renders the cart and the data already captured by these three
forms rather than collecting anything new. CheckoutPaymentForm no longer
captures any raw card data — every payment method (CIB/Edahabia,
BaridiMob/CCP transfer, Manual Order) is confirmed off-platform via the
mailing flow (core.emails) rather than a card gateway, so this form only
records the customer's choice. PaymentProofForm, at the bottom, is the
one exception that collects anything after checkout: the receipt a
BaridiMob customer uploads once they've made the transfer.
"""

import re

from django import forms

from core.constants import WILAYA_CHOICES
from programs.models import FinancingPlan, InsuranceTier

from .models import (
    PAYMENT_PROOF_CONTENT_TYPES,
    DeliveryMethod,
    Order,
    OrderStatus,
    PaymentMethod,
    PaymentProof,
)


class CheckoutInformationForm(forms.Form):
    """Spec 6.9 Step 1: "first name, last name, email, phone (all required)."""

    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    email = forms.EmailField()
    phone = forms.CharField(max_length=30)


class CheckoutDeliveryForm(forms.Form):
    """
    Spec 6.9 Step 2: a delivery address form plus exactly one delivery
    method. Delivery is offered to every wilaya; the chosen wilaya also
    drives the shipping fee (core.ShippingZone) and the TVA rate.

    The postal-code rule mirrors AddressForm's: 5 digits whose first two
    are the wilaya code.
    """

    street = forms.CharField(max_length=255)
    city = forms.CharField(max_length=100, label="Commune / City")
    postal_code = forms.CharField(max_length=20)
    wilaya = forms.ChoiceField(choices=WILAYA_CHOICES)
    delivery_method = forms.ChoiceField(
        choices=DeliveryMethod.choices, widget=forms.RadioSelect, initial=DeliveryMethod.STANDARD
    )

    def clean(self):
        cleaned_data = super().clean()
        wilaya = cleaned_data.get("wilaya")
        postal_code = (cleaned_data.get("postal_code") or "").strip()
        if postal_code:
            if not re.match(r"^\d{5}$", postal_code):
                self.add_error("postal_code", "An Algerian postal code is 5 digits.")
            elif wilaya and postal_code[:2] != wilaya:
                self.add_error(
                    "postal_code",
                    "This postal code doesn't belong to the selected wilaya "
                    "(the first two digits are the wilaya code).",
                )
        return cleaned_data


class CheckoutPaymentForm(forms.Form):
    """
    Spec 6.9 Step 3: exactly one payment method — CIB/Edahabia, BaridiMob
    transfer, or Manual Order — and an opt-in "save payment method"
    checkbox (checked by default). No method captures card data on this
    site: CIB/Edahabia is settled through Chargily's hosted checkout (the
    customer is redirected to Chargily immediately after placing the
    order, and the real "did they pay" signal is Chargily's webhook, not
    the redirect back — see orders/chargily.py), BaridiMob is settled by
    transferring to the sales account on core.CompanyInfo and uploading
    proof afterwards (orders.views.order_payment_view), and Manual Order
    (cash on delivery / bank transfer) is confirmed by email with the
    transfer/COD details. Financing/Insurance selection (BR-CHK-08) is
    folded into this step since both attach to the Order at Payment time,
    not as separate pages.
    """

    payment_method = forms.ChoiceField(choices=PaymentMethod.choices, widget=forms.RadioSelect)
    save_payment_method = forms.BooleanField(required=False, initial=True)
    financing_plan = forms.ModelChoiceField(
        queryset=FinancingPlan.objects.filter(is_active=True), required=False
    )
    insurance_tier = forms.ModelChoiceField(
        queryset=InsuranceTier.objects.filter(is_active=True), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # BaridiMob asks the customer to transfer money to a specific
        # account. Until someone has entered that account in the admin
        # there is nowhere for the money to go, so the option is withdrawn
        # rather than offered and then dead-ended -- and withdrawing it
        # here, not just in the template, means a hand-crafted POST can't
        # select it either.
        from core.models import CompanyInfo

        if not CompanyInfo.get_solo().has_sales_account:
            self.fields["payment_method"].choices = [
                choice for choice in PaymentMethod.choices if choice[0] != PaymentMethod.BARIDIMOB
            ]

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get("payment_method")

        # Edge case 15.1: "Financing plan selected but payment method is not
        # compatible... restricted to compatible payment methods only (e.g.
        # card-based)."
        if cleaned_data.get("financing_plan") and payment_method != PaymentMethod.CIB:
            self.add_error(
                "financing_plan", "A financing plan requires a CIB / Edahabia card as the payment method."
            )

        return cleaned_data


class GuestOrderLookupForm(forms.Form):
    """BR-ORD-04: "a guest can retrieve an order only via its reference plus the email used at purchase."""

    reference = forms.CharField(max_length=20)
    email = forms.EmailField()

    def clean(self):
        cleaned_data = super().clean()
        reference = cleaned_data.get("reference")
        email = cleaned_data.get("email")
        if reference and email:
            order = Order.objects.filter(reference=reference, guest_email__iexact=email).first()
            if order is None:
                raise forms.ValidationError("No matching order was found for that reference and email.")
            cleaned_data["order"] = order
        return cleaned_data

    def get_order(self):
        return self.cleaned_data.get("order")


class OrderStatusFilterForm(forms.Form):
    """Spec 6.11: "A filter control lets the visitor narrow the list to a specific status, or view all orders."""

    status = forms.ChoiceField(
        choices=[("all", "All Orders")] + list(OrderStatus.choices), required=False, initial="all"
    )


class PaymentProofForm(forms.ModelForm):
    """
    The BaridiMob settlement handshake: a customer who has already made the
    transfer uploads their receipt here and the order moves into the review
    queue (orders.views.order_payment_view).

    `file` is required with no exceptions — the whole point of this step is
    the document, and an "I paid, trust me" submission would put an
    unreviewable row in front of the sales team. The two identifying fields
    are optional because banking apps differ in what they show and a
    customer who can't find a transaction reference must still be able to
    submit; they speed up reconciliation when present rather than gating it.
    """

    class Meta:
        model = PaymentProof
        fields = ("file", "amount_declared", "transaction_reference", "sender_note")
        widgets = {
            "sender_note": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "file": "Payment proof (PDF or image)",
            "amount_declared": "Amount transferred (DA)",
            "transaction_reference": "Transaction reference",
            "sender_note": "Note for our team (optional)",
        }

    def __init__(self, *args, order=None, **kwargs):
        self.order = order
        super().__init__(*args, **kwargs)
        self.fields["file"].required = True
        self.fields["file"].widget.attrs["accept"] = ",".join(PAYMENT_PROOF_CONTENT_TYPES)

    def clean_amount_declared(self):
        amount = self.cleaned_data.get("amount_declared")
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Enter the amount you actually transferred.")
        return amount

    def clean(self):
        cleaned_data = super().clean()
        # Re-checked here as well as in the view: the view guards the happy
        # path, this guards against a stale form left open in a tab and
        # submitted after the proof was already confirmed.
        if self.order is not None and not self.order.can_upload_payment_proof:
            raise forms.ValidationError(
                "This order isn't waiting for a payment proof right now."
            )
        return cleaned_data
