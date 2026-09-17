"""
orders.views

Spec 6.9 (Checkout) and 6.11 (Order history/detail/tracking). Checkout
state is held in the session across the 3 data-collecting steps
(`request.session["checkout"]`) — Decimal/model values are normalized to
JSON-safe primitives (strings/ids) before being stored, since Django's
session backend serializes with JSON. Nothing is written to the database
until "Place Order" succeeds on the Review step (BR-ORD-01/02: an Order is
only ever created complete, never as a partial draft).
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from cart.utils import clear_promo_from_session, get_applied_promo_code, get_cart
from core.constants import get_wilaya_name
from core.utils import get_shipping_zone
from core.models import CheckoutSettings, CompanyInfo
from programs.models import FinancingPlan, InsuranceTier

from .chargily import ChargilyError, WEBHOOK_EVENT_STATES, create_checkout_for_order, verify_webhook_signature
from .forms import (
    CheckoutDeliveryForm,
    CheckoutInformationForm,
    CheckoutPaymentForm,
    GuestOrderLookupForm,
    OrderStatusFilterForm,
    PaymentProofForm,
)
from .models import DeliveryMethod, Order, PaymentMethod, PaymentState
from .utils import CheckoutValidationError, build_order_pricing, create_order_from_cart

CHECKOUT_SESSION_KEY = "checkout"
GUEST_ACCESS_SESSION_KEY = "accessible_guest_orders"


def _checkout_data(request):
    return request.session.get(CHECKOUT_SESSION_KEY, {})


def _save_checkout_step(request, step, data):
    checkout = _checkout_data(request)
    checkout[step] = data
    request.session[CHECKOUT_SESSION_KEY] = checkout


def _current_pricing_preview(request, cart):
    """Powers the persistent order-summary sidebar (spec 6.9) at every step once Delivery is known."""
    checkout = _checkout_data(request)
    delivery = checkout.get("delivery")
    if not delivery:
        return None
    return build_order_pricing(
        subtotal=cart.subtotal,
        promo_code=get_applied_promo_code(request),
        delivery_method=delivery["delivery_method"],
        destination_wilaya=delivery["wilaya"],
    )


def checkout_information_view(request):
    """Spec 6.9 Step 1."""
    cart = get_cart(request)
    if cart.item_count == 0:
        messages.info(request, "Your cart is empty.")
        return redirect("cart:cart_detail")

    initial = _checkout_data(request).get("information", {})
    if not initial and request.user.is_authenticated:
        initial = {
            "first_name": request.user.first_name, "last_name": request.user.last_name,
            "email": request.user.email, "phone": request.user.profile.phone,
        }

    if request.method == "POST":
        form = CheckoutInformationForm(request.POST)
        if form.is_valid():
            _save_checkout_step(request, "information", form.cleaned_data)
            return redirect("orders:checkout_delivery")
    else:
        form = CheckoutInformationForm(initial=initial)

    return render(request, "orders/checkout_information.html", {"form": form, "cart": cart, "step": 1})


def checkout_delivery_view(request):
    """Spec 6.9 Step 2."""
    cart = get_cart(request)
    if "information" not in _checkout_data(request):
        return redirect("orders:checkout_information")

    initial = _checkout_data(request).get("delivery", {})
    if not initial and request.user.is_authenticated:
        default_address = request.user.addresses.filter(is_default=True).first()
        if default_address:
            initial = {
                "street": default_address.street, "city": default_address.city,
                "postal_code": default_address.postal_code, "wilaya": default_address.wilaya,
            }

    if request.method == "POST":
        form = CheckoutDeliveryForm(request.POST)
        if form.is_valid():
            _save_checkout_step(request, "delivery", form.cleaned_data)
            return redirect("orders:checkout_payment")
    else:
        form = CheckoutDeliveryForm(initial=initial)

    # The Delivery step quotes a real price per method, and Algerian couriers
    # price by wilaya -- so hand the template the selected wilaya's own
    # ShippingZone row (None until one is configured, in which case the
    # template falls back to the flat constants, same as get_shipping_cost).
    selected_wilaya = (
        form.data.get("wilaya") if request.method == "POST" else initial.get("wilaya")
    )
    # Flat fallback fees, for the wilayas with no ShippingZone row of their
    # own -- read from the CheckoutSettings singleton so the quoted price
    # and what get_shipping_cost actually charges can't drift apart.
    checkout_settings = CheckoutSettings.get_safe()
    return render(request, "orders/checkout_delivery.html", {
        "form": form, "cart": cart, "step": 2, "pricing": _current_pricing_preview(request, cart),
        "delivery_zone": get_shipping_zone(selected_wilaya) if selected_wilaya else None,
        "standard_fee": checkout_settings.standard_shipping_fee,
        "express_fee": checkout_settings.standard_shipping_fee + checkout_settings.express_shipping_surcharge,
    })


def checkout_payment_view(request):
    """Spec 6.9 Step 3. Card fields are validated for shape only and never saved (see module docstring in orders.forms)."""
    cart = get_cart(request)
    checkout = _checkout_data(request)
    if "delivery" not in checkout:
        return redirect("orders:checkout_delivery")

    if request.method == "POST":
        form = CheckoutPaymentForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            _save_checkout_step(request, "payment", {
                "payment_method": cd["payment_method"],
                "save_payment_method": cd["save_payment_method"],
                "financing_plan_id": cd["financing_plan"].pk if cd["financing_plan"] else None,
                "insurance_tier_id": cd["insurance_tier"].pk if cd["insurance_tier"] else None,
            })
            return redirect("orders:checkout_review")
    else:
        payment = checkout.get("payment", {})
        form = CheckoutPaymentForm(initial={
            "payment_method": payment.get("payment_method"),
            "save_payment_method": payment.get("save_payment_method", True),
            "financing_plan": payment.get("financing_plan_id"),
            "insurance_tier": payment.get("insurance_tier_id"),
        })

    return render(request, "orders/checkout_payment.html", {
        "form": form, "cart": cart, "step": 3, "pricing": _current_pricing_preview(request, cart),
        # Drives the greyed-out "coming soon" state of the CIB/Edahabia
        # option. The form has already removed it from the accepted choices
        # when this is False -- the template only decides how to *say* so.
        "checkout_settings": CheckoutSettings.get_safe(),
    })


def checkout_review_view(request):
    """
    Spec 6.9 Step 4. GET renders the full summary and snapshots each cart
    line's current unit price into the session so the "Place Order" POST
    can detect a price change in between (BR-CHK-01, expected_prices).
    """
    cart = get_cart(request)
    checkout = _checkout_data(request)
    if "payment" not in checkout:
        return redirect("orders:checkout_payment")

    pricing = _current_pricing_preview(request, cart)

    # Resolved once and reused for both the GET render below (the Review
    # template needs real plan/tier objects and human-readable delivery
    # labels, not the raw ids/codes the session stores) and the POST branch
    # (which already needed these for create_order_from_cart) — was
    # previously only computed inside the POST branch, so a plain GET of
    # this page had no way to display what the visitor actually chose on
    # Step 3 (spec 6.9 Step 4: "an itemized list... and a read-only summary
    # of the delivery address" implies showing what was captured, not just
    # re-deriving it silently at submit time).
    financing_plan = FinancingPlan.objects.filter(
        pk=checkout["payment"].get("financing_plan_id"), is_active=True
    ).first() if checkout["payment"].get("financing_plan_id") else None
    insurance_tier = InsuranceTier.objects.filter(
        pk=checkout["payment"].get("insurance_tier_id"), is_active=True
    ).first() if checkout["payment"].get("insurance_tier_id") else None

    if request.method == "POST":
        promo_code = get_applied_promo_code(request)
        info, delivery, payment = checkout["information"], checkout["delivery"], checkout["payment"]
        expected_prices = {item.pk: str(item.unit_price) for item in cart.items.all()}

        try:
            order = create_order_from_cart(
                cart,
                user=request.user if request.user.is_authenticated else None,
                guest_email="" if request.user.is_authenticated else info["email"],
                guest_name="" if request.user.is_authenticated else f'{info["first_name"]} {info["last_name"]}',
                guest_phone="" if request.user.is_authenticated else info["phone"],
                contact_first_name=info["first_name"], contact_last_name=info["last_name"],
                contact_email=info["email"], contact_phone=info["phone"],
                delivery_street=delivery["street"], delivery_city=delivery["city"],
                delivery_postal_code=delivery["postal_code"], delivery_wilaya=delivery["wilaya"],
                delivery_method=delivery["delivery_method"],
                payment_method=payment["payment_method"], save_payment_method=payment["save_payment_method"],
                promo_code=promo_code, financing_plan=financing_plan, insurance_tier=insurance_tier,
                expected_prices=expected_prices,
            )
        except CheckoutValidationError as exc:
            for issue in exc.issues:
                messages.error(request, issue.message)
            return redirect("cart:cart_detail")

        del request.session[CHECKOUT_SESSION_KEY]
        clear_promo_from_session(request)
        request.session["last_order_reference"] = order.reference
        if not request.user.is_authenticated:
            request.session.setdefault(GUEST_ACCESS_SESSION_KEY, []).append(order.reference)
            request.session.modified = True
        messages.success(request, f"Order {order.reference} placed successfully.")

        if order.uses_card_gateway:
            # The common case: skip our own success page entirely and put
            # the customer straight on Chargily's hosted page while the
            # moment is fresh, the same way the tutorial's own pay_view
            # does it. orders.signals.initialise_payment_state already set
            # payment_state to PENDING at creation; this call is what
            # actually gets a checkout_url to redirect to.
            try:
                checkout_url = create_checkout_for_order(order)
                return redirect(checkout_url)
            except ChargilyError:
                # Chargily unreachable or erroring -- the order itself is
                # safely created either way (BR-ORD-01/02), so degrade to
                # the success page rather than losing it. can_retry_card_payment
                # is True here (PENDING, no stored URL), so the "Complete
                # Payment" CTA already on that page offers a retry.
                messages.warning(
                    request,
                    "Your order was placed, but we couldn't reach the payment provider just now. "
                    "You can complete your card payment from the button below.",
                )
        return redirect("orders:order_success", reference=order.reference)

    return render(request, "orders/checkout_review.html", {
        "cart": cart, "checkout": checkout, "pricing": pricing, "step": 4,
        "financing_plan": financing_plan, "insurance_tier": insurance_tier,
        "delivery_wilaya_display": get_wilaya_name(checkout["delivery"]["wilaya"]),
        # Rendered from the real DeliveryMethod/PaymentMethod choices rather
        # than a hardcoded if/elif chain -- the old two-way delivery check
        # silently had no case for "desk" (stopdesk), and the old payment
        # chain still matched "card"/"paypal", which no longer exist as
        # choices, so a real Algerian order would have rendered blank for
        # both. dict(...Method.choices) is the same pattern already used
        # for delivery_wilaya_display just above.
        "delivery_method_display": dict(DeliveryMethod.choices).get(
            checkout["delivery"]["delivery_method"], checkout["delivery"]["delivery_method"]
        ),
        "payment_method_display": dict(PaymentMethod.choices).get(
            checkout["payment"]["payment_method"], checkout["payment"]["payment_method"]
        ),
    })


def order_success_view(request, reference):
    order = get_object_or_404(Order, reference=reference)
    if not _can_access_order(request, order):
        messages.error(request, "That order confirmation is no longer accessible.")
        return redirect("content:home")
    return render(request, "orders/order_success.html", {"order": order})


def _can_access_order(request, order):
    if request.user.is_authenticated and order.user_id == request.user.id:
        return True
    if not request.user.is_authenticated and order.reference in request.session.get(GUEST_ACCESS_SESSION_KEY, []):
        return True
    return False


@login_required
def order_list_view(request):
    """Spec 6.11: registered customers only — guests use the reference+email lookup instead (BR-ORD-04)."""
    form = OrderStatusFilterForm(request.GET or None)
    orders = Order.objects.filter(user=request.user)
    if form.is_valid() and form.cleaned_data["status"] not in ("", "all"):
        orders = orders.filter(status=form.cleaned_data["status"])
    return render(request, "orders/order_list.html", {"orders": orders, "form": form})


def order_payment_view(request, reference):
    """
    The one payment-completion page for both online methods, branching by
    order.payment_method:

    - BaridiMob: shows the sales account to transfer to and takes the
      receipt back afterwards (unchanged from before Chargily existed).
    - CIB/Edahabia: shows a "Pay Now" / "Try Again" button. POSTing it
      calls create_checkout_for_order and redirects straight to Chargily's
      hosted page; a live, unfinished checkout is resumed via its stored
      URL rather than recreated. `?from=chargily_success` /
      `?from=chargily_failure` (Chargily's own success_url/failure_url,
      see orders.chargily._return_url) drive a transient banner only --
      never payment_state, which only the webhook is trusted to set.

    Reachable by the same rule as every other per-order page
    (`_can_access_order`) — a registered owner or a guest whose session
    holds this reference — because a guest has to be able to pay for the
    order they just placed, and gating this behind a login would strand
    every guest order permanently.
    """
    order = get_object_or_404(Order, reference=reference)
    if not _can_access_order(request, order):
        return redirect("orders:guest_order_lookup")

    if order.uses_card_gateway:
        if request.method == "POST" and order.can_retry_card_payment:
            try:
                checkout_url = create_checkout_for_order(order)
                return redirect(checkout_url)
            except ChargilyError:
                messages.error(
                    request,
                    "We couldn't reach the payment provider just now. Please try again in a moment.",
                )
        return render(request, "orders/order_payment.html", {
            "order": order,
            "company": CompanyInfo.get_solo(),
            "PaymentState": PaymentState,
            "chargily_return": request.GET.get("from", ""),
        })

    # Orders on any other method have nothing to do here; send them to the
    # order they were actually looking for rather than showing an empty page.
    if not order.requires_payment_proof:
        return redirect("orders:order_detail", reference=order.reference)

    form = None
    if order.can_upload_payment_proof:
        if request.method == "POST":
            form = PaymentProofForm(request.POST, request.FILES, order=order)
            if form.is_valid():
                proof = form.save(commit=False)
                proof.order = order
                # Saving is the trigger for everything else: the post_save
                # signal moves the order into review and sends both emails.
                proof.save()
                messages.success(
                    request,
                    "Payment proof received. We'll confirm it by email, usually within one business day.",
                )
                return redirect("orders:order_payment", reference=order.reference)
        else:
            form = PaymentProofForm(order=order)

    return render(request, "orders/order_payment.html", {
        "order": order,
        "form": form,
        "company": CompanyInfo.get_solo(),
        "latest_proof": order.latest_payment_proof,
        "proofs": order.payment_proofs.all(),
        "PaymentState": PaymentState,
    })


@csrf_exempt
@require_POST
def chargily_webhook_view(request):
    """
    Server-to-server notice from Chargily that a checkout's status changed
    -- the only signal this app trusts to actually mark an order paid (see
    the module docstring on orders.chargily for why the browser redirect
    alone never does this).

    csrf_exempt because Chargily's server, not a browser with our own
    session, is the caller -- there is no CSRF token for it to send.
    require_POST since a GET here would just be someone's browser
    (Chargily itself never GETs this URL) and doesn't need a view at all.

    Always returns 200 once the payload is authenticated and parsed, even
    for a checkout this app doesn't recognise or an event type it doesn't
    branch on -- Chargily retries on non-2xx, and retrying a webhook we
    understood fine but chose not to act on would just be noise.
    """
    payload = request.body  # raw bytes -- must not be reserialized, see orders.chargily
    signature = request.headers.get("signature", "")

    if not verify_webhook_signature(payload, signature):
        return HttpResponse(status=403)

    try:
        event = json.loads(payload)
        data = event["data"]
        event_type = event["type"]
    except (ValueError, KeyError):
        return HttpResponse(status=400)

    new_state = WEBHOOK_EVENT_STATES.get(event_type)
    if new_state is None:
        # checkout.pending / checkout.processing, or any future event type
        # this integration doesn't need to act on.
        return JsonResponse({}, status=200)

    order = Order.objects.filter(chargily_checkout_id=data.get("id")).first()
    if order is None:
        # Don't 500/4xx -- Chargily will retry a failing webhook, and a
        # missing local match almost always means a race (the order's own
        # save hasn't committed yet) rather than fraud. See orders.chargily
        # module docstring / the tutorial's own webhook view for the same
        # reasoning applied to BR-CHK's BaridiMob-side signals.
        return JsonResponse({}, status=200)

    if order.payment_state == new_state:
        # Idempotency: Chargily retries webhooks, so a duplicate delivery
        # of the same event must not re-fire the confirmation/failure email
        # a second time. orders.signals only emits mail on an actual
        # transition (see stash_previous_payment_state), so this check is
        # belt-and-suspenders, but it also skips a needless write.
        return JsonResponse({}, status=200)

    order.payment_state = new_state
    order.save(update_fields=["payment_state"])
    return JsonResponse({}, status=200)


def order_detail_view(request, reference):
    order = get_object_or_404(Order.objects.prefetch_related("items", "shipment_events"), reference=reference)
    if not _can_access_order(request, order):
        return redirect("orders:guest_order_lookup")
    return render(request, "orders/order_detail.html", {"order": order})


def order_track_view(request, reference):
    """Spec 6.11: the shipment-stage timeline for one order."""
    order = get_object_or_404(
        Order.objects.prefetch_related("shipment_events", "items__product__images"), reference=reference
    )
    if not _can_access_order(request, order):
        return redirect("orders:guest_order_lookup")

    # The static build recomputed "which stage is current" inside its render
    # loop by counting completed stages. Decided here instead so the template
    # stays declarative (rule 4's spirit — no per-template derived logic):
    # exactly one stage, the first not-yet-complete one, is marked current.
    events = list(order.shipment_events.all())
    current_marked = False
    for event in events:
        event.is_current = False
        if not event.is_complete and not current_marked:
            event.is_current = True
            current_marked = True

    # Carrier/tracking number live on the individual ShipmentEvent, not the
    # Order, and are blank until it ships — surface the first event that
    # actually has them rather than assuming (as the mockup's data did) that
    # they always exist.
    carrier_event = next((e for e in events if e.carrier and e.tracking_number), None)

    return render(request, "orders/order_track.html", {
        "order": order, "events": events, "carrier_event": carrier_event,
    })


def order_invoice_view(request, reference):
    """
    "Documents" key requirement: a printable order confirmation/invoice at
    its own URL, rendered as plain HTML with print-specific CSS — no PDF
    library involved. Same access rule as order_detail_view; company
    identity (name, address, TVA/VAT number) comes from core.CompanyInfo.
    """
    order = get_object_or_404(Order.objects.prefetch_related("items"), reference=reference)
    if not _can_access_order(request, order):
        return redirect("orders:guest_order_lookup")
    return render(request, "orders/order_invoice.html", {
        "order": order, "company": CompanyInfo.get_solo(),
    })


def guest_order_lookup_view(request):
    """BR-ORD-04: retrieve a guest order by reference + purchase email."""
    if request.method == "POST":
        form = GuestOrderLookupForm(request.POST)
        if form.is_valid():
            order = form.get_order()
            request.session.setdefault(GUEST_ACCESS_SESSION_KEY, []).append(order.reference)
            request.session.modified = True
            return redirect("orders:order_detail", reference=order.reference)
    else:
        form = GuestOrderLookupForm()
    return render(request, "orders/guest_order_lookup.html", {"form": form})
