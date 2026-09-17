"""
Shared enumerations/choice lists used across multiple Pihilics apps, kept in
one place so e.g. "which wilayas do we ship to" is defined once rather than
duplicated in accounts, orders, and dealers.
"""

from decimal import Decimal

# Checkout shipping pricing (BR-CHK-02): free above this subtotal, otherwise
# a flat standard fee; Express adds its surcharge on top of that
# determination, it never replaces it. Amounts are in DZD (Algerian dinar).
FREE_SHIPPING_THRESHOLD = Decimal("150000.00")
STANDARD_SHIPPING_FEE = Decimal("800.00")
EXPRESS_SHIPPING_SURCHARGE = Decimal("700.00")

# The 58 wilayas (provinces) of Algeria, official numeric codes as used by
# every national courier/delivery network (Yalidine, ZR Express, Maystro,
# Noest, ...) -- Pihilics ships nationwide, so this single list backs
# Dealer.wilaya, Address.wilaya, Order.delivery_wilaya, and
# CompanyInfo.wilaya alike (one country, one list, no separate
# "dealer countries" superset needed anymore).
#
# NOTE: a November 2025 / April 2026 reform ("Loi 26-06") promoted 11
# further districts to full wilaya status, bringing Algeria's administrative
# total to 69 -- but the new wilayas' own administrations only take over
# full operation from 1 January 2027, and every national courier network's
# delivery-zone API is still keyed to these original 58 codes as of this
# writing. This list therefore intentionally matches courier reality, not
# the newest administrative map; extending it to 69 is a one-line change to
# this list (plus new Dealer/coverage rows) whenever the couriers catch up.
WILAYA_CHOICES = [
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

# Backwards-compatible aliases. The codebase previously shipped to countries
# and kept a wider "dealer countries" superset; both now resolve to the one
# wilaya list so any import site not yet migrated keeps working.
SHIPPING_WILAYA_CHOICES = WILAYA_CHOICES
DEALER_WILAYA_CHOICES = WILAYA_CHOICES

# Account interface language selector (spec 6.17, Preferences tab). Algeria's
# own languages: Arabic and Tamazight are official, French is the de-facto
# commercial lingua franca, English kept for foreign visitors.
LANGUAGE_CHOICES = [
    ("ar", "العربية"),
    ("fr", "Français"),
    ("en", "English"),
    ("kab", "Tamaziɣt"),
]

# Fixed half-day slots offered by Test Ride / Service booking forms (spec 6.12/6.13).
TIME_SLOT_CHOICES = [
    ("morning", "Morning (9:00 - 13:00)"),
    ("afternoon", "Afternoon (13:00 - 17:00)"),
]
