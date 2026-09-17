"""
core.emails

Shared mailing layer behind every notification the site sends: order
confirmation/status, BaridiMob payment instructions and the
proof-received/confirmed/rejected cycle, test-ride/service booking
received/approved, and contact-form acknowledgement/alert (see orders/notifications.py,
bookings/notifications.py, support/notifications.py). Each of those
modules calls send_branded_email() / send_admin_email() rather than
building an EmailMultiAlternatives itself, so template selection, the
branded HTML wrapper (templates/emails/base_email.html, matching the
site's own ink/volt/bone theme), and failure handling all live in one
place.

Mail is best-effort: a broken SMTP config or a transient send failure
must never break checkout, a booking, or a contact-form submission. Every
send goes through send_branded_email(), which logs and swallows any
exception rather than propagating it into the request/signal that
triggered it -- deliberately mirroring settings.py's EMAIL_BACKEND
fallback (console backend when no SMTP password is configured), so mail
is always "fire and forget" from the caller's point of view.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger("core.emails")


def _brand_context():
    """CompanyInfo-derived values every email template needs (site name, address, contact email)."""
    from core.models import CompanyInfo

    company = CompanyInfo.get_solo()
    return {
        "site_name": company.trade_name or company.legal_name,
        "company": company,
        "site_url": settings.SITE_URL,
    }


def send_branded_email(*, to, subject, template_name, context, reply_to=None, attachments=None):
    """
    Renders templates/emails/{template_name}.html (which extends
    emails/base_email.html) with the brand context merged in, sends it
    with a plain-text fallback derived from the same HTML, and never
    raises. Returns True/False so a caller can log a warning if it cares,
    but nothing in this codebase should ever let that failure surface to
    the customer.

    `to` may be a single address or an iterable of addresses. `reply_to`
    lets the customer's own reply route straight back to whichever mailbox
    is relevant (e.g. admin_email for admin-facing alerts) instead of the
    no-reply-style sending identity.

    `attachments` is an iterable of (filename, content, mimetype) tuples.
    It exists for the payment-proof alert: whoever reconciles a BaridiMob
    transfer needs the receipt itself in front of them, and making them
    follow a link into the admin to see it turns a ten-second check into a
    login. Attachments are read into memory, so this is for the small files
    orders.models.validate_payment_proof already caps, not arbitrary media.
    """
    if not to:
        return False
    recipients = [to] if isinstance(to, str) else [addr for addr in to if addr]
    if not recipients:
        return False

    ctx = {**_brand_context(), **context}
    try:
        html_body = render_to_string(f"emails/{template_name}.html", ctx)
        text_body = strip_tags(html_body)
        message = EmailMultiAlternatives(
            subject=f"{ctx['site_name']} — {subject}",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
            reply_to=[reply_to] if reply_to else None,
        )
        message.attach_alternative(html_body, "text/html")
        for filename, content, mimetype in attachments or ():
            message.attach(filename, content, mimetype)
        message.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send '%s' email to %s", template_name, recipients)
        return False


def send_admin_email(*, subject, template_name, context, reply_to=None, attachments=None):
    """Same as send_branded_email, addressed to the fixed internal inbox (settings.ADMIN_NOTIFICATION_EMAIL)."""
    return send_branded_email(
        to=settings.ADMIN_NOTIFICATION_EMAIL,
        subject=subject,
        template_name=template_name,
        context=context,
        reply_to=reply_to,
        attachments=attachments,
    )
