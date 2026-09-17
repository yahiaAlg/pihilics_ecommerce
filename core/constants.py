"""
core.constants

Historically this module *was* the configuration: hardcoded choice lists
and hardcoded shipping prices that could only be changed by editing the
file and redeploying. That is no longer true. The live values now live in
ordinary editable models --

    core.Wilaya           the provinces we deliver to
    core.Language         the interface languages offered on Preferences
    core.CheckoutSettings the shipping thresholds/fees (a singleton)
    bookings.TimeSlot     the booking slots offered by Test Ride / Service

-- and this module is the thin accessor layer over them, plus the seed
data those tables are populated from.

Two reasons the FALLBACK_* lists below still exist rather than being
deleted into a data migration:

1. They are the seed. The data migrations and `seed_minimal` /`seed_full`
   read them, so "what a fresh install starts with" is written down once.
2. They are the floor. Model fields take these choice lists as *callables*
   (Django 5.0+), which means Django will ask the database for them at
   moments where the database may not be able to answer: during `migrate`
   on an empty database, during `manage.py check` before the tables
   exist, in a test harness mid-teardown. Every accessor below degrades to
   its fallback instead of raising, so a missing table can never take the
   site (or a migration) down.

Consequence worth knowing: because the fields declare a callable, editing
a Wilaya row in the admin does **not** produce a model change and does
**not** need a migration. That is the entire point of the change.
"""

from decimal import Decimal

# --------------------------------------------------------------------------
# Seed / fallback data
# --------------------------------------------------------------------------

# The 58 wilayas (provinces) of Algeria, official numeric codes as used by
# every national courier/delivery network (Yalidine, ZR Express, Maystro,
# Noest, ...).
#
# NOTE: a November 2025 / April 2026 reform ("Loi 26-06") promoted 11
# further districts to full wilaya status, bringing Algeria's
# administrative total to 69 -- but those administrations only take over
# full operation from 1 January 2027, and every courier's delivery-zone API
# is still keyed to these 58 codes. This seed therefore matches courier
# reality, not the newest administrative map. Adding the other 11 is now an
# admin task (Core > Wilayas > Add), not a code change.
FALLBACK_WILAYAS = [
    ("01", "Adrar"), ("02", "Chlef"), ("03", "Laghouat"), ("04", "Oum El Bouaghi"),
    ("05", "Batna"), ("06", "Béjaïa"), ("07", "Biskra"), ("08", "Béchar"),
    ("09", "Blida"), ("10", "Bouïra"), ("11", "Tamanrasset"), ("12", "Tébessa"),
    ("13", "Tlemcen"), ("14", "Tiaret"), ("15", "Tizi Ouzou"), ("16", "Alger"),
    ("17", "Djelfa"), ("18", "Jijel"), ("19", "Sétif"), ("20", "Saïda"),
    ("21", "Skikda"), ("22", "Sidi Bel Abbès"), ("23", "Annaba"), ("24", "Guelma"),
    ("25", "Constantine"), ("26", "Médéa"), ("27", "Mostaganem"), ("28", "M'Sila"),
    ("29", "Mascara"), ("30", "Ouargla"), ("31", "Oran"), ("32", "El Bayadh"),
    ("33", "Illizi"), ("34", "Bordj Bou Arréridj"), ("35", "Boumerdès"), ("36", "El Tarf"),
    ("37", "Tindouf"), ("38", "Tissemsilt"), ("39", "El Oued"), ("40", "Khenchela"),
    ("41", "Souk Ahras"), ("42", "Tipaza"), ("43", "Mila"), ("44", "Aïn Defla"),
    ("45", "Naâma"), ("46", "Aïn Témouchent"), ("47", "Ghardaïa"), ("48", "Relizane"),
    ("49", "Timimoun"), ("50", "Bordj Badji Mokhtar"), ("51", "Ouled Djellal"), ("52", "Béni Abbès"),
    ("53", "In Salah"), ("54", "In Guezzam"), ("55", "Touggourt"), ("56", "Djanet"),
    ("57", "El M'Ghair"), ("58", "El Meniaa"),
]

# Account interface language selector (spec 6.17, Preferences tab).
# Arabic and Tamazight are official, French is the de-facto commercial
# lingua franca, English kept for foreign visitors.
FALLBACK_LANGUAGES = [
    ("ar", "العربية"),
    ("fr", "Français"),
    ("en", "English"),
    ("kab", "Tamaziɣt"),
]

# Half-day slots offered by Test Ride / Service booking forms (spec 6.12/6.13).
FALLBACK_TIME_SLOTS = [
    ("morning", "Morning (9:00 - 13:00)"),
    ("afternoon", "Afternoon (13:00 - 17:00)"),
]

# Checkout shipping pricing (BR-CHK-02), used as the *defaults* of the
# CheckoutSettings singleton's fields and as the fallback if that row can't
# be read. Amounts are in DZD.
DEFAULT_FREE_SHIPPING_THRESHOLD = Decimal("150000.00")
DEFAULT_STANDARD_SHIPPING_FEE = Decimal("800.00")
DEFAULT_EXPRESS_SHIPPING_SURCHARGE = Decimal("700.00")


# --------------------------------------------------------------------------
# Accessors
# --------------------------------------------------------------------------
#
# A choice list is read once per process and then held until something
# changes it. Without this, every `get_wilaya_display()`, every rendered
# <select>, and every model-field validation would be its own query --
# these lists are read constantly and written about once a year.
#
# Invalidated by post_save/post_delete receivers registered in
# core.apps.CoreConfig.ready (see core/signals.py), so an admin edit takes
# effect on the next request without a restart.

_CHOICE_CACHE = {}


def clear_choice_cache(key=None):
    """Drop one cached choice list, or all of them."""
    if key is None:
        _CHOICE_CACHE.clear()
    else:
        _CHOICE_CACHE.pop(key, None)


def _cached_choices(key, loader, fallback):
    if key in _CHOICE_CACHE:
        return _CHOICE_CACHE[key]
    try:
        choices = list(loader())
    except Exception:
        # Table not created yet (fresh `migrate`), database unavailable,
        # apps not loaded: fall back rather than break. Deliberately not
        # cached, so the first successful read still wins.
        return list(fallback)
    if not choices:
        # An empty table means nobody has seeded it. An empty <select> is
        # worse than a stale one.
        return list(fallback)
    _CHOICE_CACHE[key] = choices
    return choices


def wilaya_choices():
    """Active wilayas as (code, name), ordered by code. Callable on purpose — see module docstring."""

    def _load():
        from core.models import Wilaya

        return Wilaya.objects.filter(is_active=True).values_list("code", "name")

    return _cached_choices("wilaya", _load, FALLBACK_WILAYAS)


def language_choices():
    """Active interface languages as (code, name)."""

    def _load():
        from core.models import Language

        return Language.objects.filter(is_active=True).values_list("code", "name")

    return _cached_choices("language", _load, FALLBACK_LANGUAGES)


def time_slot_choices():
    """Active booking slots as (code, label)."""

    def _load():
        from bookings.models import TimeSlot

        return TimeSlot.objects.filter(is_active=True).values_list("code", "label")

    return _cached_choices("time_slot", _load, FALLBACK_TIME_SLOTS)


def get_wilaya_name(code):
    """Human name for a wilaya code, or the code itself if it's unknown."""
    return dict(wilaya_choices()).get(code, code)


# Backwards-compatible aliases: the codebase previously shipped to countries
# and kept a wider "dealer countries" superset. Both now resolve to the one
# wilaya accessor, so any import site not yet migrated keeps working.
shipping_wilaya_choices = wilaya_choices
dealer_wilaya_choices = wilaya_choices


# --------------------------------------------------------------------------
# Frozen aliases — historical migrations only
# --------------------------------------------------------------------------
#
# Migrations already applied in the wild (accounts.0002, dealers.0002,
# orders.0002, core.0003) import these names and bake them into an
# AlterField. Django replays those files verbatim on a fresh database, so
# they must keep importing successfully and must keep returning the same
# literal list they returned when they were written -- a migration's job is
# to reproduce a past state, not to reflect the current one.
#
# The later migration that swaps these fields onto the callable accessors
# is what makes the live choices dynamic. Nothing new should import the
# three names below; use wilaya_choices() / language_choices() /
# time_slot_choices() instead.
WILAYA_CHOICES = FALLBACK_WILAYAS
LANGUAGE_CHOICES = FALLBACK_LANGUAGES
TIME_SLOT_CHOICES = FALLBACK_TIME_SLOTS
