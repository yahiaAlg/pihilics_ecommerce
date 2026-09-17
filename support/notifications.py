"""
support.notifications

Contact-form emails, sent via core.emails and triggered from
support/signals.py on ContactMessage creation. Fires identically whether
the submission came from the dedicated Contact page or the Help Center's
embedded form (support.views.handle_contact_submission is the one save
path both go through — see that module's docstring).
"""

from core.emails import send_admin_email, send_branded_email


def send_contact_acknowledgement(message):
    """Lets the customer know their message was received, with a copy of what they sent."""
    send_branded_email(
        to=message.email,
        subject="We've Received Your Message",
        template_name="contact_ack_customer",
        context={"message": message},
    )


def send_contact_admin_alert(message):
    """Routes the submission to the admin inbox, reply-to'd straight back to the customer."""
    send_admin_email(
        subject=f"New Contact Message — {message.get_department_display()}",
        template_name="contact_alert_admin",
        context={"message": message},
        reply_to=message.email,
    )
