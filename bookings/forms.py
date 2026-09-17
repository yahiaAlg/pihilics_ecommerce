"""
bookings.forms

Spec 6.12 (Test Ride booking) and 6.13 (Service booking). Both forms
duplicate their model's `clean()` checks (date >= tomorrow) so the error
surfaces as a normal form error rather than an IntegrityError/ValidationError
from `full_clean()`, and add the BR-BK-01/02 slot-conflict check
(bookings.utils.check_slot_conflict) that the model docstrings explicitly
defer to this layer.
"""

from django import forms
from django.utils import timezone

from catalog.models import Product, ProductType
from dealers.models import Dealer

from .models import ServiceBooking, ServiceTier, TestRideBooking
from .utils import check_slot_conflict


class TestRideBookingForm(forms.ModelForm):
    """
    Spec 6.12: "motorcycle model..., dealer..., preferred date..., preferred
    time..., first name, last name, email, phone, motorcycle licence
    number, and a waiver-acknowledgment checkbox."
    """

    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = TestRideBooking
        fields = [
            "product",
            "dealer",
            "date",
            "time_slot",
            "first_name",
            "last_name",
            "email",
            "phone",
            "license_number",
            "waiver_acknowledged",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(
            product_type=ProductType.MOTORCYCLE, is_active=True
        )
        self.fields["dealer"].queryset = Dealer.objects.filter(is_active=True)

    def clean_date(self):
        value = self.cleaned_data["date"]
        if value <= timezone.localdate():
            raise forms.ValidationError("Preferred date must be at least tomorrow.")
        return value

    def clean_waiver_acknowledged(self):
        value = self.cleaned_data["waiver_acknowledged"]
        if not value:
            raise forms.ValidationError("The waiver must be acknowledged to book a test ride.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        dealer = cleaned_data.get("dealer")
        date_ = cleaned_data.get("date")
        time_slot = cleaned_data.get("time_slot")
        if dealer and date_ and time_slot:
            if check_slot_conflict(TestRideBooking, dealer, date_, time_slot, exclude_pk=self.instance.pk):
                self.add_error(
                    "time_slot", "That dealer already has a booking for this date and time — please choose another slot."
                )
        return cleaned_data


class ServiceBookingForm(forms.ModelForm):
    """
    Spec 6.13: a Service Type (tier) selection, motorcycle, preferred date,
    and dealer/time, plus contact details. `garage_entry` is scoped to the
    booking user's own entries when the form is constructed with `user=`
    (spec 6.13 entry point: "'Book Service' action from a Garage entry in
    Account" should pre-select that bike, per the business rule note).
    """

    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = ServiceBooking
        fields = [
            "garage_entry",
            "product",
            "dealer",
            "service_tier",
            "date",
            "time_slot",
            "contact_first_name",
            "contact_last_name",
            "contact_email",
            "contact_phone",
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(
            product_type=ProductType.MOTORCYCLE, is_active=True
        )
        self.fields["dealer"].queryset = Dealer.objects.filter(is_active=True)
        self.fields["service_tier"].queryset = ServiceTier.objects.filter(is_active=True)
        self.fields["garage_entry"].required = False
        if user is not None and user.is_authenticated:
            self.fields["garage_entry"].queryset = user.garage_entries.all()
        else:
            self.fields["garage_entry"].queryset = self.fields["garage_entry"].queryset.none()

    def clean_date(self):
        value = self.cleaned_data["date"]
        if value <= timezone.localdate():
            raise forms.ValidationError("Preferred date must be at least tomorrow.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        dealer = cleaned_data.get("dealer")
        date_ = cleaned_data.get("date")
        time_slot = cleaned_data.get("time_slot")
        if dealer and date_ and time_slot:
            if check_slot_conflict(ServiceBooking, dealer, date_, time_slot, exclude_pk=self.instance.pk):
                self.add_error(
                    "time_slot", "That dealer already has a booking for this date and time — please choose another slot."
                )
        return cleaned_data
