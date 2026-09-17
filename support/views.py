"""
support.views

Spec 6.20's dedicated Contact page (department-routed tabs + form). The
same form is embedded at the bottom of the Help Center page
(content.views.support_view), so the POST-handling logic lives here once
and content.views calls into it rather than duplicating it.
"""

from django.contrib import messages
from django.shortcuts import redirect, render

from core.models import CompanyInfo

from .forms import ContactForm


def handle_contact_submission(request):
    """
    Validates and saves a ContactMessage POST — replacing the prior
    prototype's toast-only no-op (spec 11.3.11) with a persisted record.
    Returns the bound (invalid) form so the caller can re-render it, or
    None on success so the caller can redirect (PRG).
    """
    form = ContactForm(request.POST)
    if form.is_valid():
        message = form.save(commit=False)
        if request.user.is_authenticated:
            message.user = request.user
        message.save()
        messages.success(request, "Thanks — we've received your message and will be in touch soon.")
        return None
    messages.error(request, "Please correct the errors below.")
    return form


def contact_view(request):
    """Spec 6.20: department-routed tabs (Sales/Support/Press/Partnerships), exactly one active at a time."""
    if request.method == "POST":
        form = handle_contact_submission(request)
        if form is None:
            return redirect("support:contact")
    else:
        form = ContactForm()
    return render(request, "support/contact.html", {"form": form, "company": CompanyInfo.get_solo()})
