"""
orders.signals

Automated side effects of placing / cancelling an order:

- BR-ORD-03: placing an order decrements stock_quantity on each purchased
  product; cancelling an order restores it.
- BR-CAT-07: stock_quantity can never go negative (defensive floor here;
  the authoritative check is the server-side re-validation at "Place Order"
  time, BR-CHK-01, which happens in the checkout view, not here).
- BR-ORD-05: purchasing a motorcycle auto-creates a GarageEntry linked to
  the customer's account, for registered customers only (VIN generation
  itself lives in accounts.utils, since GarageEntry is an accounts model).
- Order Tracking (spec 6.11) needs a ShipmentEvent row to exist the moment
  an order is placed — otherwise order_track_view has nothing to render
  until a Store Admin manually adds one. Placing an order therefore seeds
  the full shipment-stage timeline: "Order Placed" complete and stamped
  now, every later stage present but pending, so the tracking page always
  has the complete stage list to render against (spec 6.11 "Tracking
  Timeline"), not just whichever stages an admin has gotten around to.
- Mailing (orders/notifications.py): placing an order emails the customer
  a receipt plus the admin inbox a new-order alert; any later admin-driven
  status change (list_editable in the admin, or the cancel action) emails
  the customer an update. Both key off the same `_previous_status` stash
  already used by restore_stock_on_cancellation below.
- BaridiMob settlement: an order's `payment_state` is derived from its
  payment_method at placement (only a transfer waits on a proof; cash on
  delivery and card orders never enter the queue), and is then driven
  entirely by PaymentProof rows -- uploading one moves the order into
  review, and a reviewer confirming or rejecting it moves the order on and
  emails the customer. Keeping those transitions here, rather than in the
  admin action or the upload view, is what makes them identical whichever
  side triggers them: a proof confirmed by a script, by the admin, or from
  a shell all emit the same state change and the same email.

Stock/GarageEntry effects key off OrderItem creation (rather than Order
creation) since, procedurally, the checkout view creates the Order row
first and then its OrderItem rows — by the time each OrderItem exists, its
product and quantity are final and ready to act on. The ShipmentEvent seed
below keys off Order creation itself, since it's a property of the order
as a whole, not of any one line item.
"""

from django.db.models import F
from django.db.models.functions import Greatest
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from accounts.models import GarageEntry
from accounts.utils import generate_unique_vin
from catalog.models import Product, ProductType

from .models import (
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    PaymentProof,
    PaymentProofStatus,
    PaymentState,
    ShipmentEvent,
    ShipmentStage,
)


@receiver(post_save, sender=OrderItem)
def apply_order_item_placement_effects(sender, instance, created, **kwargs):
    """BR-ORD-03 stock decrement and BR-ORD-05 GarageEntry creation, run once per purchased line."""
    if not created or not instance.product_id:
        return

    product = instance.product

    # BR-ORD-03 / BR-CAT-07: decrement stock, floored at zero.
    Product.objects.filter(pk=product.pk).update(
        stock_quantity=Greatest(F("stock_quantity") - instance.quantity, 0)
    )

    # BR-ORD-05: registered-customer motorcycle purchases create one Garage
    # entry per unit purchased (each physical bike gets its own VIN).
    order = instance.order
    if product.product_type == ProductType.MOTORCYCLE and order.user_id:
        GarageEntry.objects.bulk_create(
            [
                GarageEntry(
                    user_id=order.user_id,
                    product=product,
                    order_item=instance,
                    vin=generate_unique_vin(),
                )
                for _ in range(instance.quantity)
            ]
        )


@receiver(post_save, sender=Order)
def seed_shipment_timeline(sender, instance, created, **kwargs):
    """
    Spec 6.11 / 12.8: the Order Success and Order Tracking pages need a
    shipment-stage timeline to render from the moment an order is placed,
    not only once a Store Admin has started adding ShipmentEvent rows by
    hand. Seeds every ShipmentStage once, in order, with "Order Placed"
    already complete and timestamped and every later stage pending.
    """
    if not created:
        return
    ShipmentEvent.objects.bulk_create(
        [
            ShipmentEvent(
                order=instance,
                stage=stage,
                occurred_at=timezone.now() if stage == ShipmentStage.ORDER_PLACED else None,
                is_complete=stage == ShipmentStage.ORDER_PLACED,
                sort_order=index,
            )
            for index, stage in enumerate(ShipmentStage.values)
        ]
    )


@receiver(pre_save, sender=Order)
def stash_previous_status_and_stamp_cancellation(sender, instance, **kwargs):
    """
    Records the pre-save status on the instance so the post_save handler
    below can detect a genuine transition into CANCELLED (as opposed to a
    save that leaves status unchanged). Also auto-stamps `cancelled_at`
    the first time status flips to CANCELLED, so callers only need to set
    `status`, not the timestamp.
    """
    if instance.pk:
        instance._previous_status = (
            Order.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    else:
        instance._previous_status = None

    if instance.status == OrderStatus.CANCELLED and not instance.cancelled_at:
        instance.cancelled_at = timezone.now()


@receiver(post_save, sender=Order)
def restore_stock_on_cancellation(sender, instance, created, **kwargs):
    """BR-ORD-03: cancelling an order restores the stock it had decremented."""
    if created:
        return
    previous_status = getattr(instance, "_previous_status", None)
    if instance.status != OrderStatus.CANCELLED or previous_status == OrderStatus.CANCELLED:
        return

    for item in instance.items.filter(product__isnull=False).select_related("product"):
        Product.objects.filter(pk=item.product_id).update(
            stock_quantity=F("stock_quantity") + item.quantity
        )

    # NOTE: per spec (13.7 edge cases), whether a GarageEntry created from
    # this order should be flagged or removed on cancellation is left to
    # admin policy and is intentionally not automated here.


@receiver(post_save, sender=Order)
def send_order_mail(sender, instance, created, **kwargs):
    """
    Mailing: a receipt (+ admin alert) the moment an order is placed, or a
    status-change email to the customer on every later genuine transition
    (admin-driven only — see orders/notifications.py). Reuses the
    `_previous_status` stash from stash_previous_status_and_stamp_cancellation
    above rather than re-querying. Mail failures never raise (core.emails
    swallows them), so this never blocks the save that triggered it.
    """
    from . import notifications

    if created:
        notifications.send_order_confirmation(instance)
        return

    previous_status = getattr(instance, "_previous_status", None)
    if previous_status is not None and previous_status != instance.status:
        notifications.send_order_status_update(instance)


@receiver(pre_save, sender=Order)
def initialise_payment_state(sender, instance, **kwargs):
    """
    Derives `payment_state` from the chosen payment method as the order is
    first written.

    Two methods settle online and start in a "not resolved yet" state:
    BaridiMob starts AWAITING_PROOF (a transfer the customer proves by
    upload), CIB/Edahabia starts PENDING (a Chargily checkout the customer
    completes on Chargily's hosted page, settled by webhook -- see
    orders/chargily.py). Manual Order (COD / bank transfer) is settled by
    the courier or by hand outside any queue here, so it starts and stays
    NOT_REQUIRED.

    Set on create only. After that the state belongs to the proof/webhook
    lifecycle below, and re-deriving it on every save would silently undo
    a confirmation the moment anything else touched the row.
    """
    if instance.pk:
        return
    if instance.payment_method == PaymentMethod.BARIDIMOB:
        instance.payment_state = PaymentState.AWAITING_PROOF
    elif instance.payment_method == PaymentMethod.CIB:
        instance.payment_state = PaymentState.PENDING
    else:
        instance.payment_state = PaymentState.NOT_REQUIRED


@receiver(post_save, sender=Order)
def send_payment_instructions_mail(sender, instance, created, **kwargs):
    """Transfer orders get the sales account details emailed alongside their receipt."""
    if not created or not instance.requires_payment_proof:
        return
    from . import notifications

    notifications.send_payment_instructions(instance)


@receiver(pre_save, sender=Order)
def stash_previous_payment_state(sender, instance, **kwargs):
    """
    Same stash pattern as stash_previous_status_and_stamp_cancellation,
    but for payment_state -- lets send_card_payment_update_mail below tell
    a genuine transition (a webhook flipping PENDING -> CONFIRMED, say)
    apart from a save that leaves it unchanged (an admin editing the
    shipping address, for instance), so a customer is never emailed a
    payment update twice for the same event.

    Runs regardless of what initialise_payment_state above does: on
    create, instance.pk is still unset here (Django assigns it only after
    the INSERT), so this always resolves to None on create, same as the
    equivalent _previous_status stash -- there's no "previous" state for a
    row that doesn't exist yet.
    """
    if instance.pk:
        instance._previous_payment_state = (
            Order.objects.filter(pk=instance.pk).values_list("payment_state", flat=True).first()
        )
    else:
        instance._previous_payment_state = None


@receiver(post_save, sender=Order)
def send_card_payment_update_mail(sender, instance, created, **kwargs):
    """
    Emails the customer when a CIB/Edahabia order's payment_state changes
    into CONFIRMED / FAILED / CANCELED / EXPIRED. orders.views.
    chargily_webhook_view is what actually performs that update -- this
    just turns "the field changed" into "the customer is told", the same
    division of labour as apply_payment_proof_effects below does for
    BaridiMob's proof-review decisions.
    """
    if created or not instance.uses_card_gateway:
        return
    previous = getattr(instance, "_previous_payment_state", None)
    if previous is None or previous == instance.payment_state:
        return

    from . import notifications

    if instance.payment_state == PaymentState.CONFIRMED:
        notifications.send_payment_confirmed(instance)
    elif instance.payment_state in (PaymentState.FAILED, PaymentState.CANCELED, PaymentState.EXPIRED):
        notifications.send_card_payment_incomplete(instance)


@receiver(pre_save, sender=PaymentProof)
def stash_previous_proof_status(sender, instance, **kwargs):
    """
    Same stash pattern as stash_previous_status_and_stamp_cancellation: lets
    the post_save handler below tell a genuine review decision apart from a
    save that left the verdict alone (an admin fixing a typo in the review
    note, say), so a customer is never emailed "rejected" twice.

    Also stamps `reviewed_at` the first time a verdict is reached, so
    callers -- the admin actions, a shell, anything -- only have to set
    `status`.
    """
    if instance.pk:
        instance._previous_status = (
            PaymentProof.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
        )
    else:
        instance._previous_status = None

    if instance.status != PaymentProofStatus.PENDING and not instance.reviewed_at:
        instance.reviewed_at = timezone.now()


@receiver(post_save, sender=PaymentProof)
def apply_payment_proof_effects(sender, instance, created, **kwargs):
    """
    Moves the order's payment_state in step with the proof, and emails the
    customer at each hop.

    On upload: AWAITING_PROOF/REJECTED -> UNDER_REVIEW, acknowledgement to
    the customer, alert with the file attached to the team.
    On a verdict: -> CONFIRMED or back to REJECTED (which re-opens
    uploading, see Order.can_upload_payment_proof), with the outcome
    emailed either way.

    The order is saved with update_fields=["payment_state"] so this can
    never disturb the BR-ORD-01 snapshot fields, and so the Order post_save
    handlers above see an unchanged `status` and stay quiet -- a payment
    decision is not a fulfilment status change and must not emit one.
    """
    from . import notifications

    order = instance.order

    if created:
        order.payment_state = PaymentState.UNDER_REVIEW
        order.save(update_fields=["payment_state"])
        notifications.send_payment_proof_received(instance)
        return

    previous_status = getattr(instance, "_previous_status", None)
    if previous_status is None or previous_status == instance.status:
        return

    if instance.status == PaymentProofStatus.CONFIRMED:
        order.payment_state = PaymentState.CONFIRMED
        order.save(update_fields=["payment_state"])
        notifications.send_payment_confirmed(order, instance)
    elif instance.status == PaymentProofStatus.REJECTED:
        order.payment_state = PaymentState.REJECTED
        order.save(update_fields=["payment_state"])
        notifications.send_payment_rejected(order, instance)
