"""
support.forms

Spec 6.20: shared by the Support page's contact form and the Contact page's
department-routed form ("a set of selectable tabs — e.g., Sales, Support,
Press, Partnerships — exactly one active at a time... alongside a contact
form (name, email, subject, message)"). Submitting now creates a real,
persisted ContactMessage, replacing the prior prototype's toast-only no-op
(spec 11.3.11).
"""

from django import forms

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["department", "name", "email", "subject", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}
