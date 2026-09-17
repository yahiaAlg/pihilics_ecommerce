"""
orders.notifications

Order-related emails, sent via core.emails.send_branded_email /
send_admin_email and triggered from orders/signals.py. The events:

- Order placed: one email to the customer (receipt + payment-method
  next-step — a secure-link promise for CIB/Edahabia, COD/transfer
  details for Manual Order, since neither goes through a card gateway
  here), one to the admin inbox. Always sent regardless of
  UserProfile.order_notifications_opt_in — this is the transactional
  receipt confirming the order was taken, not an optional update.
- Order status changed (admin-initiated only — customers have no
  self-service cancel/status action, see orders/views.py): one email to
  the customer, gated by order_notifications_opt_in for registered users.
  Guests have no profile/opt-in to check, so they're always notified —
  the order's own guest_email is the only channel they have.

The rest cover BaridiMob settlement, which has no gateway to call back and
so is driven entirely by mail. The cycle deliberately mirrors a P2P
escrow handshake, with one email per hop so neither side is ever waiting
without knowing it:

- Payment instructions: sent alongside the receipt when the order is
  placed, carrying the sales account to transfer to and the link to come
  back and upload the receipt.
- Proof uploaded: acknowledgement to the customer ("we have it, sit
  tight") plus an admin alert with the receipt *attached*, so a transfer
  can be reconciled against the bank statement without logging in.
- Proof confirmed / rejected: the outcome, to the customer. A rejection
  carries the reviewer's note and the re-upload link, because a rejected
  transfer is nearly always a fixable mistake rather than a dead order.

These payment emails ignore order_notifications_opt_in for the same reason
the receipt does: they are not status updates, they are the transaction
itself -- an opted-out customer who never learns their proof was rejected
has simply lost their money's worth of goods.
"""

import logging

from django.urls import reverse

from core.emails import send_admin_email, send_branded_email

logger = logging.getLogger("orders.notifications")


def _track_url(order):
    from django.conf import settings

    return f"{settings.SITE_URL}{reverse('orders:order_track', args=[order.reference])}"


def _payment_url(order):
    from django.conf import settings

    return f"{settings.SITE_URL}{reverse('orders:order_payment', args=[order.reference])}"


def _payment_context(order, **extra):
    """Shared context for every BaridiMob email: the order, where to pay, and where to come back to."""
    from core.models import CompanyInfo

    from django.conf import settings

    return {
        "order": order,
        "company": CompanyInfo.get_solo(),
        "payment_url": _payment_url(order),
        # Deep-link into the proof's own admin change page rather than the
        # changelist: the alert's whole value is that a reviewer can go from
        # "email arrived" to "confirmed" without hunting for the row.
        "admin_url": f"{settings.SITE_URL}{reverse('admin:orders_paymentproof_changelist')}",
        **extra,
    }


def _customer_should_be_notified(order):
    """Registered users can opt out of order-status updates; guests can't opt out of their own receipt."""
    if not order.user_id:
        return True
    profile = getattr(order.user, "profile", None)
    return profile is None or profile.order_notifications_opt_in


def send_order_confirmation(order):
    """Fired once, when the order is first placed — see orders/signals.py."""
    recipient = order.contact_email
    context = {
        "order": order,
        "items": order.items.select_related("product").all(),
        "track_url": _track_url(order),
    }
    send_branded_email(
        to=recipient,
        subject=f"Order Confirmed — {order.reference}",
        template_name="order_confirmation_customer",
        context=context,
    )
    send_admin_email(
        subject=f"New Order — {order.reference}",
        template_name="order_confirmation_admin",
        context=context,
        reply_to=recipient,
    )


def send_order_status_update(order):
    """Fired on every genuine status transition after placement — see orders/signals.py."""
    if not _customer_should_be_notified(order):
        return
    send_branded_email(
        to=order.contact_email,
        subject=f"Order {order.reference} — {order.get_status_display()}",
        template_name="order_status_update_customer",
        context={"order": order, "track_url": _track_url(order)},
    )


def send_payment_instructions(order):
    """
    Fired with the receipt when a BaridiMob order is placed — carries the
    sales account to transfer to, so the customer has the details in their
    inbox rather than only on a checkout page they've navigated away from.
    """
    send_branded_email(
        to=order.contact_email,
        subject=f"Payment Instructions — {order.reference}",
        template_name="payment_instructions_customer",
        context=_payment_context(order),
    )


def send_payment_proof_received(proof):
    """
    Fired when a customer uploads a proof: acknowledgement to them, alert
    (with the file attached) to the team who will reconcile it.

    The attachment is read defensively — storage can fail, and a missing
    file must not cost the team the alert itself, only the convenience of
    not having to open the admin.
    """
    order = proof.order
    context = _payment_context(order, proof=proof)

    send_branded_email(
        to=order.contact_email,
        subject=f"Payment Proof Received — {order.reference}",
        template_name="payment_proof_received_customer",
        context=context,
    )

    attachments = []
    try:
        with proof.file.open("rb") as handle:
            attachments.append((
                proof.original_filename or "payment-proof",
                handle.read(),
                "application/pdf" if proof.is_pdf else "image/jpeg",
            ))
    except Exception:  # noqa: BLE001 — the alert matters more than the attachment
        logger.warning("Could not attach payment proof %s to the admin alert", proof.pk)

    send_admin_email(
        subject=f"Payment Proof to Review — {order.reference}",
        template_name="payment_proof_admin",
        context=context,
        reply_to=order.contact_email,
        attachments=attachments,
    )


def send_payment_confirmed(order, proof=None):
    """Fired when a reviewer confirms a proof — the customer's 'money received' receipt."""
    send_branded_email(
        to=order.contact_email,
        subject=f"Payment Confirmed — {order.reference}",
        template_name="payment_confirmed_customer",
        context=_payment_context(order, proof=proof, track_url=_track_url(order)),
    )


def send_payment_rejected(order, proof=None):
    """
    Fired when a reviewer rejects a proof. Carries the reviewer's note
    verbatim: "rejected" with no reason gives the customer nothing to act
    on, and the order stays re-uploadable precisely so they can act.
    """
    send_branded_email(
        to=order.contact_email,
        subject=f"Payment Proof Needs Attention — {order.reference}",
        template_name="payment_rejected_customer",
        context=_payment_context(order, proof=proof),
    )


def send_card_payment_incomplete(order):
    """
    Fired when a CIB/Edahabia checkout resolves to FAILED, CANCELED, or
    EXPIRED (orders.views.chargily_webhook_view). All three are ordinary,
    recoverable outcomes -- a declined card, a closed tab, a checkout that
    simply timed out -- so this reads as "try again", not as a rejection;
    Order.can_retry_card_payment is already True by the time this fires,
    and the email's button leads straight back to that retry.
    """
    send_branded_email(
        to=order.contact_email,
        subject=f"Payment Not Completed — {order.reference}",
        template_name="card_payment_incomplete_customer",
        context=_payment_context(order),
    )
