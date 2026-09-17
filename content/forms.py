"""
content.forms

Spec 6.20 Support/Help Center: "A search box at the top filters FAQ content
live... matches question text, answer text, or category name (case-insensitive
substring)."
"""

from django import forms


class FAQSearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=150, label="Search the Help Center")
