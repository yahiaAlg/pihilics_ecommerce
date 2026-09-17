"""
dealers.forms

Spec 6.14: "A search box filters the dealer list live by matching the
visitor's input against dealer name, city, or wilaya (case-insensitive,
substring match)."
"""

from django import forms


class DealerSearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=100, label="Search dealers")
