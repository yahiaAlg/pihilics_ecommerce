"""
accounts.forms

Spec 6.17 (Account tabs) and 6.18 (Login/Register). Login/Registration are
real (BR-ACC-03): unique email + password-strength enforcement via
accounts.utils.validate_password_strength, replacing the prior prototype's
"any input succeeds" simulation.
"""

import re

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError

from core.constants import LANGUAGE_CHOICES, WILAYA_CHOICES

from .models import Address, UserProfile
from .utils import validate_password_strength


class RegisterForm(forms.Form):
    """
    Spec 6.18 Register: "name, email, password, confirm password, and
    presumably a terms-acceptance checkbox." Split into first/last name to
    match the Profile tab's field shape (spec 6.17.1). The User's
    `username` is set to the email itself (BR-ACC-03 requires a *unique
    email*; the built-in User model still needs some `username`, so email
    is reused there rather than asking the visitor for a second identifier
    the spec never mentions).
    """

    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    terms_accepted = forms.BooleanField(
        error_messages={"required": "You must accept the Terms and Privacy Policy to register."}
    )
    # Reference markup's "Send me product updates and news" checkbox (unchecked
    # by default, unlike UserProfile.marketing_opt_in's own model default of
    # True) -- maps straight onto the same field the Preferences tab manages,
    # applied in save() below. Previously present in the reference page but
    # silently dropped by this form; wiring it is a bugfix, not new scope.
    marketing_opt_in = forms.BooleanField(required=False, initial=False)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        try:
            validate_password_strength(password)
        except DjangoValidationError as exc:
            raise forms.ValidationError(exc.messages)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError({"confirm_password": "Passwords do not match."})
        return cleaned_data

    def save(self):
        """Creates the User (username = email) and lets accounts.signals attach the default UserProfile."""
        email = self.cleaned_data["email"]
        user = User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data["password"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
        )
        # accounts.signals.create_user_profile already ran (post_save, synchronous)
        # by the time create_user() returns, so user.profile exists here.
        user.profile.marketing_opt_in = self.cleaned_data["marketing_opt_in"]
        user.profile.save(update_fields=["marketing_opt_in"])
        return user


class LoginForm(forms.Form):
    """
    Spec 6.18 Login: "email and password... a 'Remember me' option." A real
    credential check replaces the prior "any input succeeds" simulation
    (BR-ACC-03's counterpart on the sign-in side). `authenticate()` is
    attempted against `username=email` since RegisterForm stores the email
    as the User's username.
    """

    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    remember_me = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")
        if email and password:
            # BUG FOUND while wiring login.html against seeded data (not just
            # self-registered accounts): this used to call
            # authenticate(username=email, password=password) directly, which
            # only succeeds when a user's `username` field happens to equal
            # their email -- true for accounts created through RegisterForm
            # (which sets username=email), but NOT true for core/management/
            # commands/seed_full.py's demo users (sophie.martin, marco.rossi,
            # staff.berlin, admin), whose usernames are human-readable handles
            # distinct from their email. Every one of those accounts failed
            # to log in via email+password until now, reproduced live:
            # authenticate(username='sophie.martin@example.com', ...) -> None,
            # authenticate(username='sophie.martin', ...) -> the real user.
            # Fix: resolve the email to its actual username first (BR-ACC-03
            # only promises a unique *email*, never that it equals username),
            # falling back to the raw email so a genuinely unknown address
            # still fails authenticate() cleanly with the same generic error
            # below, rather than leaking whether an email is registered.
            try:
                username = User.objects.get(email__iexact=email).username
            except User.DoesNotExist:
                username = email
            user = authenticate(username=username, password=password)
            if user is None:
                raise forms.ValidationError("Invalid email or password.")
            if not user.is_active:
                raise forms.ValidationError("This account is inactive.")
            cleaned_data["user"] = user
        return cleaned_data

    def get_user(self):
        return self.cleaned_data.get("user")


class ProfileForm(forms.ModelForm):
    """
    Spec 6.17.1: "a form pre-filled with the customer's first/last name,
    email, phone, and date of birth." Spans two models (User + UserProfile)
    so first_name/last_name/email are declared explicitly and written back
    onto `self.instance.user` in save(), while phone/date_of_birth are
    native UserProfile fields.
    """

    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()

    class Meta:
        model = UserProfile
        fields = ["phone", "date_of_birth"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name
            self.fields["email"].initial = self.instance.user.email

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        conflict = User.objects.filter(email__iexact=email).exclude(pk=self.instance.user_id)
        if conflict.exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            profile.save()
        return profile


class PreferencesForm(forms.ModelForm):
    """Spec 6.17.5: three notification toggles plus the interface-language selector."""

    preferred_language = forms.ChoiceField(choices=LANGUAGE_CHOICES)

    class Meta:
        model = UserProfile
        fields = [
            "marketing_opt_in",
            "order_notifications_opt_in",
            "promo_opt_in",
            "preferred_language",
        ]


class AddressForm(forms.ModelForm):
    """
    Spec 6.17.6 (Addresses tab). A saved address exists to prefill
    Checkout's Delivery step, so its wilaya is drawn from the same
    nationwide list Checkout offers.

    `clean` applies a light postal-code shape check (validation table 15.2).
    Algerian postal codes are 5 digits whose first two digits *are* the
    wilaya code, so instead of the old table of per-country regexes there is
    one rule that also cross-checks the code against the selected wilaya --
    a stronger plausibility check than a pure shape match, and still not a
    full address-validation service (out of scope per Chapter 4/16.2).
    """

    wilaya = forms.ChoiceField(choices=WILAYA_CHOICES)

    class Meta:
        model = Address
        fields = ["label", "street", "city", "postal_code", "wilaya", "is_default"]

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
