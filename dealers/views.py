"""
dealers.views

Spec 6.14: dealer directory with a map and a live search box.

Djangofication note: the static build's search box filtered the list via a
raw `input` event (re-rendering both the list and the map pins client-side
on every keystroke, with no page reload). That's not one of the
djangofication brief's four whitelisted "minimal AJAX" cases (cart totals,
promo validation, Configurator running total, catalog search-as-you-type),
so it's ported as a normal `<form method="get">` instead: the query lives
in `?q=`, `dealer_list_view` re-filters server-side, and the browser's own
"Enter submits a lone text field" behavior stands in for the old keystroke
handler. Typing no longer live-filters as you go — documented here since
it's the one dealers.html interaction that couldn't be preserved 1:1.
"""

from urllib.parse import quote

from django.db.models import Q
from django.shortcuts import render

from core.constants import wilaya_choices

from .forms import DealerSearchForm
from .models import Dealer


def _map_pin_position(dealer):
    """Ports the static build's `renderDealers()` pin-placement math
    verbatim: percentage coordinates within `#dealerMap`, clamped so a pin
    never renders outside the visible canvas."""
    x = ((float(dealer.longitude) + 25) / 50) * 100
    y = ((70 - float(dealer.latitude)) / 50) * 100
    return max(5, min(95, x)), max(5, min(95, y))


def dealer_list_view(request):
    form = DealerSearchForm(request.GET or None)
    # The map overlay's "N Dealers Across Europe" headline is static copy in
    # the reference build (never re-rendered by the search's JS) — it always
    # reflects the full active network, not the current search's result count.
    total_dealer_count = Dealer.objects.filter(is_active=True).count()
    dealers = Dealer.objects.filter(is_active=True)

    if form.is_valid() and form.cleaned_data["q"]:
        q = form.cleaned_data["q"]
        # `wilaya` stores a 2-digit code; match against the human-readable
        # wilaya name too, since that's what a visitor actually types
        # ("Setif"), and against the code itself, since Algerians routinely
        # refer to a wilaya by its number ("19").
        matching_codes = [code for code, label in wilaya_choices() if q.lower() in label.lower()]
        if q.strip().isdigit():
            matching_codes.append(q.strip().zfill(2))
        dealers = dealers.filter(Q(name__icontains=q) | Q(city__icontains=q) | Q(wilaya__in=matching_codes))

    # Materialize so each dealer can carry its computed map pin position and
    # pre-built "Directions" URL (mirrors `d.address + ' ' + d.city` passed
    # through `encodeURIComponent` in the static build) without per-template
    # arithmetic or a custom filter.
    # Data-shape note (not in the static build): the static mock's `address`
    # field was a street line only, so its card template concatenated
    # `address, city, wilaya` itself. The real `Dealer.address` field is a
    # single free-text mailing address that's *already* "street, postal
    # code, city, wilaya" (see seed_full.py / admin entry) -- so it, alone,
    # is the complete line the design intends to show. Appending `.city`/
    # `.get_wilaya_display()` on top of it would duplicate them. Decision:
    # render `dealer.address` alone wherever the reference concatenated all
    # three, both on the card and when building the Maps "Directions" link.
    dealers = list(dealers)
    for dealer in dealers:
        dealer.map_x, dealer.map_y = _map_pin_position(dealer)
        dealer.maps_url = "https://maps.google.com/?q=" + quote(dealer.address)

    return render(request, "dealers/dealer_list.html", {
        "form": form,
        "dealers": dealers,
        "total_dealer_count": total_dealer_count,
    })
