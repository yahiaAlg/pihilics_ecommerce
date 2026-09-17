"""
management command: seed_full

Comprehensive demo data matching the functional spec: all 11
motorcycles across 4 categories, all 12 accessories across 5 categories,
8 dealers across 7 countries, financing/insurance/service programs, FAQ +
journal content, demo accounts (admin, dealer staff, two customers), and
sample carts/orders/bookings/reviews so every page in the app has
something real to show.

Everything is created via get_or_create on a natural key (slug, username,
code, ...), so running this command again updates nothing and creates
nothing new -- it's safe to re-run. Use --flush to wipe previously-seeded
data first if you want a truly clean re-seed.

Usage:
    python manage.py seed_full
    python manage.py seed_full --no-images   (skip the network image fetch)
    python manage.py seed_full --flush       (wipe seeded data first)
"""

import random
from datetime import timedelta
import base64
from decimal import Decimal

from django.core.files.base import ContentFile

# A genuine (if trivial) 1x1 PNG -- passes validate_payment_proof's
# extension + content-type check for real, unlike an arbitrary byte string,
# so the seeded proof exercises the same validation a real upload would.
SEED_PAYMENT_PROOF_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Address, UserProfile, UserRole
from bookings.models import (
    BookingStatus,
    ServiceBooking,
    ServiceTier,
    ServiceTierName,
    TestRideBooking,
)
from cart.models import Cart, CartItem, PromoCode
from catalog.models import (
    Category,
    Product,
    ProductColor,
    ProductImage,
    ProductSize,
    ProductSpec,
    ProductType,
    Review,
    VariantGroup,
    VariantOption,
)
from content.models import FAQCategory, FAQEntry, Story
from core.constants import time_slot_choices
from core.models import CheckoutSettings, CompanyInfo, ShippingZone
from dealers.models import Dealer
from orders.models import (
    DeliveryMethod,
    Order,
    OrderStatus,
    PaymentMethod,
    ShipmentEvent,
    ShipmentStage,
)
from programs.models import FinancingPlan, InsuranceTier, InsuranceTierName
from support.models import ContactDepartment, ContactMessage

from ._seed_utils import ensure_legal_documents, fetch_placeholder_image

# Algeria applies one national TVA rate, so there is no per-wilaya rate
# table to seed -- CompanyInfo.default_vat_rate covers every order and
# core.utils.get_vat_rate falls back to it. See the VATRate docstring.
STANDARD_TVA_RATE = Decimal("19.00")

# Per-wilaya courier pricing for the wilayas this seed actually uses, plus
# a spread of others so the Checkout delivery step has realistic variation
# north-to-south. Any wilaya without a row falls back to the flat constants
# in core.constants, so checkout works nationwide from the first run.
SHIPPING_ZONES = [
    # (wilaya, home_fee, desk_fee, days_min, days_max)
    ("16", Decimal("500.00"), Decimal("300.00"), 1, 2),  # Alger
    ("09", Decimal("550.00"), Decimal("300.00"), 1, 2),  # Blida
    ("19", Decimal("600.00"), Decimal("350.00"), 2, 3),  # Setif
    ("06", Decimal("600.00"), Decimal("350.00"), 2, 3),  # Bejaia
    ("31", Decimal("650.00"), Decimal("400.00"), 2, 3),  # Oran
    ("25", Decimal("700.00"), Decimal("400.00"), 2, 4),  # Constantine
    ("23", Decimal("700.00"), Decimal("400.00"), 2, 4),  # Annaba
    ("05", Decimal("700.00"), Decimal("400.00"), 2, 4),  # Batna
    ("30", Decimal("1000.00"), Decimal("600.00"), 4, 6),  # Ouargla
    ("47", Decimal("1000.00"), Decimal("600.00"), 4, 6),  # Ghardaia
    ("08", Decimal("1200.00"), Decimal("750.00"), 5, 7),  # Bechar
    ("11", Decimal("1400.00"), Decimal("900.00"), 5, 8),  # Tamanrasset
]

# Standard variant-group template applied to every motorcycle (spec 2.1:
# Battery, Suspension, Wheels, each with priced upgrade options).
VARIANT_GROUP_TEMPLATE = [
    (
        "Battery",
        [
            ("Standard", Decimal("0.00"), True),
            ("Extended Range", Decimal("270000.00"), False),
        ],
    ),
    (
        "Suspension",
        [
            ("Standard", Decimal("0.00"), True),
            ("Off-Road Kit", Decimal("97500.00"), False),
        ],
    ),
    (
        "Wheels",
        [("Alloy", Decimal("0.00"), True), ("Spoked", Decimal("45000.00"), False)],
    ),
]

MOTORCYCLES = [
    # -- Enduro --------------------------------------------------------
    {
        "slug": "pihilics-rvx",
        "name": "Pihilics RVX",
        "category": "Enduro",
        "price": "1875000.00",
        "badge": "best_seller",
        "description": "Pihilics' flagship enduro: a lightweight electric off-roader built for technical trails.",
        "features": [
            "Adjustable regenerative braking",
            "Removable battery pack",
            "IP67-rated electronics",
        ],
        "specs": {
            "Range": "180 km",
            "Power": "35 kW",
            "Weight": "128 kg",
            "Top Speed": "140 km/h",
            "Battery Capacity": "9.6 kWh",
            "Charge Time": "3.5 h",
        },
        "colors": [("Graphite Black", "#1a1a1a"), ("Racing Red", "#c81e2c")],
        "stock": 30,
        "threshold": 5,
        "pre_order": False,
    },
    {
        "slug": "pihilics-rvx-pro",
        "name": "Pihilics RVX Pro",
        "category": "Enduro",
        "price": "2130000.00",
        "badge": "",
        "description": "The RVX with a bigger pack and a stiffer chassis for serious off-road riders.",
        "features": [
            "Uprated motor cooling",
            "Adjustable suspension",
            "Skid-plate standard",
        ],
        "specs": {
            "Range": "210 km",
            "Power": "42 kW",
            "Weight": "134 kg",
            "Top Speed": "150 km/h",
            "Battery Capacity": "11.4 kWh",
            "Charge Time": "4 h",
        },
        "colors": [("Graphite Black", "#1a1a1a"), ("Matte Olive", "#5b5f42")],
        "stock": 18,
        "threshold": 5,
        "pre_order": False,
    },
    {
        "slug": "enduro-r",
        "name": "Pihilics Enduro R",
        "category": "Enduro",
        "price": "1695000.00",
        "badge": "",
        "description": "A nimble, entry-level enduro tuned for tight singletrack.",
        "features": [
            "Lightweight trellis frame",
            "Trail-tuned suspension",
            "Quick-swap battery",
        ],
        "specs": {
            "Range": "150 km",
            "Power": "28 kW",
            "Weight": "119 kg",
            "Top Speed": "125 km/h",
            "Battery Capacity": "7.8 kWh",
            "Charge Time": "3 h",
        },
        "colors": [("Racing Red", "#c81e2c"), ("Alpine White", "#f2f2f2")],
        "stock": 22,
        "threshold": 5,
        "pre_order": False,
    },
    {
        "slug": "enduro-sport",
        "name": "Pihilics Enduro Sport",
        "category": "Enduro",
        "price": "1590000.00",
        "badge": "new",
        "description": "A sharper, street-legal take on the Enduro R with road-biased tyres.",
        "features": [
            "Street-legal lighting kit",
            "Dual-purpose tyres",
            "Ride-mode selector",
        ],
        "specs": {
            "Range": "160 km",
            "Power": "30 kW",
            "Weight": "122 kg",
            "Top Speed": "130 km/h",
            "Battery Capacity": "8.2 kWh",
            "Charge Time": "3.2 h",
        },
        "colors": [("Alpine White", "#f2f2f2"), ("Graphite Black", "#1a1a1a")],
        "stock": 20,
        "threshold": 5,
        "pre_order": False,
    },
    # -- Trail -----------------------------------------------------------
    {
        "slug": "trail-s",
        "name": "Pihilics Trail S",
        "category": "Trail",
        "price": "1635000.00",
        "badge": "",
        "description": "A friendly, approachable trail bike built for weekend exploring.",
        "features": [
            "Low seat height",
            "Beginner ride mode",
            "Puncture-resistant tyres",
        ],
        "specs": {
            "Range": "165 km",
            "Power": "26 kW",
            "Weight": "115 kg",
            "Top Speed": "120 km/h",
            "Battery Capacity": "7.6 kWh",
            "Charge Time": "3 h",
        },
        "colors": [("Forest Green", "#2f4f3a"), ("Alpine White", "#f2f2f2")],
        "stock": 24,
        "threshold": 5,
        "pre_order": False,
    },
    {
        "slug": "trail-l",
        "name": "Pihilics Trail L",
        "category": "Trail",
        "price": "1815000.00",
        "badge": "",
        "description": "The long-travel version of the Trail S, built for rougher terrain.",
        "features": ["Long-travel suspension", "Bash guard", "Wide footpegs"],
        "specs": {
            "Range": "175 km",
            "Power": "31 kW",
            "Weight": "124 kg",
            "Top Speed": "135 km/h",
            "Battery Capacity": "8.8 kWh",
            "Charge Time": "3.4 h",
        },
        "colors": [("Forest Green", "#2f4f3a"), ("Graphite Black", "#1a1a1a")],
        "stock": 16,
        "threshold": 5,
        "pre_order": False,
    },
    {
        "slug": "trail-xr",
        "name": "Pihilics Trail XR",
        "category": "Trail",
        "price": "2010000.00",
        "badge": "",
        "description": "The range-topping Trail, with the Adventure line's motor in a lighter chassis.",
        "features": [
            "Adventure-spec motor",
            "Lightweight subframe",
            "Larger fuel-tank-style battery shroud",
        ],
        "specs": {
            "Range": "200 km",
            "Power": "38 kW",
            "Weight": "130 kg",
            "Top Speed": "145 km/h",
            "Battery Capacity": "10.6 kWh",
            "Charge Time": "3.8 h",
        },
        "colors": [("Matte Olive", "#5b5f42"), ("Alpine White", "#f2f2f2")],
        "stock": 12,
        "threshold": 5,
        "pre_order": True,
    },
    # -- Adventure ---------------------------------------------------------
    {
        "slug": "adventure-x",
        "name": "Pihilics Adventure X",
        "category": "Adventure",
        "price": "2370000.00",
        "badge": "",
        "description": "A long-range electric adventure bike built for multi-day touring off the grid.",
        "features": ["Long-range battery", "Integrated luggage mounts", "Heated grips"],
        "specs": {
            "Range": "260 km",
            "Power": "40 kW",
            "Weight": "155 kg",
            "Top Speed": "150 km/h",
            "Battery Capacity": "13.2 kWh",
            "Charge Time": "4.5 h",
        },
        "colors": [("Desert Sand", "#c9b28c"), ("Graphite Black", "#1a1a1a")],
        "stock": 14,
        "threshold": 5,
        "pre_order": False,
    },
    {
        "slug": "adventure-l",
        "name": "Pihilics Adventure L",
        "category": "Adventure",
        "price": "2535000.00",
        "badge": "",
        "description": "The top-spec Adventure, with a bigger pack for true multi-day range.",
        "features": [
            "Largest available battery",
            "Full luggage system compatibility",
            "Cruise control",
        ],
        "specs": {
            "Range": "300 km",
            "Power": "44 kW",
            "Weight": "162 kg",
            "Top Speed": "155 km/h",
            "Battery Capacity": "15.6 kWh",
            "Charge Time": "5 h",
        },
        "colors": [("Desert Sand", "#c9b28c"), ("Alpine White", "#f2f2f2")],
        "stock": 3,
        "threshold": 5,
        "pre_order": False,
    },
    # -- Performance -------------------------------------------------------
    {
        "slug": "urban-e",
        "name": "Pihilics Urban E",
        "category": "Performance",
        "price": "1470000.00",
        "old_price": "1575000.00",
        "badge": "sale",
        "description": "Pihilics' most affordable model: a street-legal commuter built for city riding.",
        "features": [
            "Compact frame",
            "Fast-charge capable",
            "App-connected ride stats",
        ],
        "specs": {
            "Range": "120 km",
            "Power": "22 kW",
            "Weight": "108 kg",
            "Top Speed": "110 km/h",
            "Battery Capacity": "6.2 kWh",
            "Charge Time": "2.5 h",
        },
        "colors": [("Racing Red", "#c81e2c"), ("Alpine White", "#f2f2f2")],
        "stock": 40,
        "threshold": 5,
        "pre_order": False,
    },
    {
        "slug": "performance-rs",
        "name": "Pihilics Performance RS",
        "category": "Performance",
        "price": "3225000.00",
        "badge": "limited",
        "description": "A 200-unit limited edition track-focused electric superbike.",
        "features": [
            "Track-tuned motor controller",
            "Carbon bodywork",
            "Numbered plaque, 1 of 200",
        ],
        "specs": {
            "Range": "140 km",
            "Power": "70 kW",
            "Weight": "148 kg",
            "Top Speed": "220 km/h",
            "Battery Capacity": "11.8 kWh",
            "Charge Time": "3 h",
        },
        "colors": [("Racing Red", "#c81e2c"), ("Graphite Black", "#1a1a1a")],
        "stock": 45,
        "threshold": 5,
        "pre_order": False,
    },
]

ACCESSORIES = [
    # -- Riding Gear ---------------------------------------------------
    {
        "slug": "riding-jacket",
        "name": "Pihilics Riding Jacket",
        "category": "Riding Gear",
        "price": "52500.00",
        "badge": "best_seller",
        "description": "Abrasion-resistant riding jacket with removable armour and ventilation panels.",
        "features": ["CE-rated armour", "Waterproof liner", "Reflective panels"],
        "specs": {"Material": "600D textile", "Weight": "1.4 kg"},
        "sizes": ["S", "M", "L", "XL"],
        "colors": [("Graphite Black", "#1a1a1a")],
    },
    {
        "slug": "carbon-helmet",
        "name": "Pihilics Carbon Helmet",
        "category": "Riding Gear",
        "price": "64500.00",
        "badge": "new",
        "description": "A lightweight carbon-shell full-face helmet with a drop-down sun visor.",
        "features": [
            "Carbon-fibre shell",
            "Drop-down sun visor",
            "Removable, washable liner",
        ],
        "specs": {"Material": "Carbon fibre", "Weight": "1.3 kg"},
        "sizes": ["S", "M", "L", "XL"],
        "colors": [("Graphite Black", "#1a1a1a"), ("Alpine White", "#f2f2f2")],
    },
    {
        "slug": "adventure-goggles",
        "name": "Pihilics Adventure Goggles",
        "category": "Riding Gear",
        "price": "13500.00",
        "badge": "",
        "description": "Scratch-resistant riding goggles with a tear-off-compatible lens.",
        "features": ["Anti-fog coating", "Tear-off compatible", "Foam-padded frame"],
        "specs": {"Weight": "0.15 kg"},
        "sizes": [],
        "colors": [],
    },
    {
        "slug": "touring-gloves",
        "name": "Pihilics Touring Gloves",
        "category": "Riding Gear",
        "price": "12000.00",
        "badge": "",
        "description": "All-season touring gloves with knuckle protection and touchscreen fingertips.",
        "features": [
            "Knuckle armour",
            "Touchscreen-compatible fingertips",
            "Waterproof membrane",
        ],
        "specs": {"Material": "Leather / textile blend"},
        "sizes": ["S", "M", "L", "XL"],
        "colors": [("Graphite Black", "#1a1a1a")],
    },
    # -- Chargers ----------------------------------------------------------
    {
        "slug": "fast-home-charger",
        "name": "Pihilics Fast Home Charger",
        "category": "Chargers",
        "price": "90000.00",
        "badge": "",
        "description": "A wall-mounted fast charger that cuts home charge times roughly in half.",
        "features": [
            "Full charge in under 2 hours",
            "Weatherproof enclosure",
            "Wi-Fi status app",
        ],
        "specs": {"Output": "7.4 kW", "Weight": "4.2 kg"},
        "sizes": [],
        "colors": [],
    },
    {
        "slug": "portable-charger-kit",
        "name": "Pihilics Portable Charger Kit",
        "category": "Chargers",
        "price": "37500.00",
        "badge": "",
        "description": "A compact charger that packs into the underseat storage for on-the-road top-ups.",
        "features": [
            "Fits underseat storage",
            "Standard household plug",
            "Carry case included",
        ],
        "specs": {"Output": "2.2 kW", "Weight": "1.8 kg"},
        "sizes": [],
        "colors": [],
    },
    # -- Batteries -----------------------------------------------------
    {
        "slug": "extended-battery",
        "name": "Extended Battery Pack",
        "category": "Batteries",
        "price": "330000.00",
        "old_price": "370000.00",
        "badge": "sale",
        "description": "Drop-in extended-capacity battery pack, compatible with the full Pihilics lineup.",
        "features": [
            "+40% range",
            "Same footprint as stock pack",
            "5-year capacity warranty",
        ],
        "specs": {"Capacity": "13.2 kWh", "Weight": "38 kg"},
        "sizes": [],
        "colors": [],
    },
    {
        "slug": "spare-battery-cell",
        "name": "Spare Battery Cell",
        "category": "Batteries",
        "price": "220000.00",
        "badge": "",
        "description": "A standard-capacity spare pack for riders who want a fast swap instead of a wait.",
        "features": ["Hot-swappable", "Standard capacity", "5-year capacity warranty"],
        "specs": {"Capacity": "9.6 kWh", "Weight": "29 kg"},
        "sizes": [],
        "colors": [],
    },
    # -- Protection ----------------------------------------------------
    {
        "slug": "protection-kit",
        "name": "Engine Protection Kit",
        "category": "Protection",
        "price": "28500.00",
        "badge": "",
        "description": "Bolt-on bash guards for the motor casing and lower frame rails.",
        "features": ["Motor casing guard", "Frame rail sliders", "Tool-free install"],
        "specs": {"Material": "Aluminium"},
        "sizes": [],
        "colors": [],
    },
    {
        "slug": "frame-guard-set",
        "name": "Frame Guard Set",
        "category": "Protection",
        "price": "19500.00",
        "badge": "",
        "description": "Adhesive frame and swingarm guards that protect paint from trail debris.",
        "features": ["3M adhesive backing", "Precision-cut fitment", "Matte finish"],
        "specs": {"Material": "Polyurethane film"},
        "sizes": [],
        "colors": [],
    },
    # -- Parts -------------------------------------------------------------
    {
        "slug": "performance-brake-pads",
        "name": "Performance Brake Pads",
        "category": "Parts",
        "price": "15000.00",
        "badge": "",
        "description": "Sintered replacement brake pads for stronger, more consistent stopping power.",
        "features": [
            "Sintered compound",
            "Reduced fade under heavy use",
            "Direct OEM fit",
        ],
        "specs": {"Compound": "Sintered metal"},
        "sizes": [],
        "colors": [],
    },
    {
        "slug": "all-terrain-tire-set",
        "name": "All-Terrain Tire Set",
        "category": "Parts",
        "price": "39000.00",
        "badge": "",
        "description": "A front-and-rear tyre set tuned for mixed on/off-road grip.",
        "features": [
            "50/50 on/off-road tread",
            "Reinforced sidewalls",
            "Front + rear pair",
        ],
        "specs": {"Type": "Dual-sport"},
        "sizes": [],
        "colors": [],
    },
]

DEALERS = [
    {
        "slug": "pihilics-alger",
        "name": "Pihilics Alger",
        "city": "Alger",
        "wilaya": "16",
        "address": "12 Rue Didouche Mourad, 16000 Alger Centre, Alger",
        "phone": "+213 21 55 01 01",
        "lat": "36.753768",
        "lng": "3.058756",
    },
    {
        "slug": "pihilics-setif",
        "name": "Pihilics Setif",
        "city": "Setif",
        "wilaya": "19",
        "address": "Cite des Freres Meslem, Route de Bejaia, 19000 Setif",
        "phone": "+213 36 55 01 02",
        "lat": "36.190073",
        "lng": "5.408341",
    },
    {
        "slug": "pihilics-oran",
        "name": "Pihilics Oran",
        "city": "Oran",
        "wilaya": "31",
        "address": "45 Boulevard de l'ALN, 31000 Oran",
        "phone": "+213 41 55 01 03",
        "lat": "35.699739",
        "lng": "-0.633245",
    },
    {
        "slug": "pihilics-constantine",
        "name": "Pihilics Constantine",
        "city": "Constantine",
        "wilaya": "25",
        "address": "8 Rue Larbi Ben M'hidi, 25000 Constantine",
        "phone": "+213 31 55 01 04",
        "lat": "36.365000",
        "lng": "6.614722",
    },
    {
        "slug": "pihilics-annaba",
        "name": "Pihilics Annaba",
        "city": "Annaba",
        "wilaya": "23",
        "address": "22 Cours de la Revolution, 23000 Annaba",
        "phone": "+213 38 55 01 05",
        "lat": "36.897400",
        "lng": "7.765400",
    },
    {
        "slug": "pihilics-bejaia",
        "name": "Pihilics Bejaia",
        "city": "Bejaia",
        "wilaya": "06",
        "address": "5 Rue de la Liberte, 06000 Bejaia",
        "phone": "+213 34 55 01 06",
        "lat": "36.751200",
        "lng": "5.056000",
    },
    {
        "slug": "pihilics-blida",
        "name": "Pihilics Blida",
        "city": "Blida",
        "wilaya": "09",
        "address": "17 Avenue Ali Boumendjel, 09000 Blida",
        "phone": "+213 25 55 01 07",
        "lat": "36.470100",
        "lng": "2.829000",
    },
    {
        "slug": "pihilics-ouargla",
        "name": "Pihilics Ouargla",
        "city": "Ouargla",
        "wilaya": "30",
        "address": "Route de Ghardaia, 30000 Ouargla",
        "phone": "+213 29 55 01 08",
        "lat": "31.949200",
        "lng": "5.325500",
    },
]

FAQS = {
    FAQCategory.ORDERS_DELIVERY: [
        (
            "How long does delivery take?",
            "Standard delivery typically arrives within 5-10 business days; Express delivery arrives within 2-4 business days.",
        ),
        (
            "Can I change or cancel my order after placing it?",
            "Contact Support as soon as possible. Orders that haven't yet entered manufacturing can usually be changed or cancelled.",
        ),
        (
            "Do you deliver to every wilaya?",
            "Yes. We deliver to all 58 wilayas, either to your address or to your courier's agency (stopdesk). The fee and delivery window depend on the wilaya and are shown at checkout.",
        ),
        (
            "Will I get tracking information?",
            "Yes. Once your order ships, its tracking number and carrier appear on the Order Detail page in your account.",
        ),
    ],
    FAQCategory.BATTERY_CHARGING: [
        (
            "How long does a full charge take?",
            "It depends on the model and charger; most Pihilics packs reach a full charge in 3-5 hours on a standard charger, or under 2 hours with the Fast Home Charger.",
        ),
        (
            "How much range should I expect to lose over time?",
            "Pihilics battery packs are warrantied to retain at least 80% of original capacity for 5 years under normal use.",
        ),
        (
            "Can I swap my battery for a bigger one later?",
            "Yes, the Extended Battery Pack is a drop-in replacement for the standard pack on every current model.",
        ),
        (
            "Is it safe to charge overnight?",
            "Yes. Every Pihilics charger and battery pack includes over-charge and thermal cut-off protection.",
        ),
    ],
    FAQCategory.WARRANTY_SERVICE: [
        (
            "What does the standard warranty cover?",
            "Every new Pihilics motorcycle includes a 2-year manufacturer's warranty covering the motor, controller, and frame.",
        ),
        (
            "How often should I service my motorcycle?",
            "We recommend a Routine Check every 5,000 km, with a Battery Service or Major Service as your Garage page suggests based on usage.",
        ),
        (
            "Can I book a service without owning an Pihilics motorcycle?",
            "Service bookings are tied to a Garage entry, so the motorcycle needs to be registered to your account first.",
        ),
        (
            "Does insurance cover accidental damage?",
            "The Comprehensive and Premium insurance tiers both cover accidental damage; Essential covers liability, theft, and fire/natural disaster only.",
        ),
    ],
    FAQCategory.TEST_RIDES_PURCHASING: [
        (
            "Do I need a motorcycle licence to book a test ride?",
            "Yes, a valid motorcycle licence number is required when booking, and you'll need to bring the physical licence to the appointment.",
        ),
        (
            "Can I test ride any model?",
            "Test rides are available for our current in-stock and pre-order highlight models at each dealer; availability varies by location.",
        ),
        (
            "Is financing available at checkout?",
            "Yes, 12/24/36-month financing plans are selectable at Checkout, alongside the three insurance tiers.",
        ),
        (
            "What happens after I submit a test ride request?",
            "The selected dealer receives your request and confirms an exact time; you'll get a confirmation once it's approved.",
        ),
    ],
}

STORIES = [
    {
        "slug": "200-kilometers-in-silence",
        "title": "200 Kilometers in Silence: A Day on the Pihilics Adventure X",
        "excerpt": "A dawn-to-dusk ride across three mountain passes, without a single stop for fuel.",
        "body": (
            "We left before sunrise, when the valley air was still cold enough to fog the visor. "
            "The Adventure X doesn't announce itself the way a combustion bike does -- there's no "
            "warm-up idle, no smell of exhaust, just a quiet click and then torque. Over the next "
            "eleven hours we crossed three passes, stopped twice to top up at a Fast Home Charger "
            "borrowed from a farmhouse, and never once thought about where the nearest fuel station was. "
            "By the time the sun dropped behind the last ridge, the only sound in the whole ride had been wind."
        ),
    },
    {
        "slug": "how-pihilics-batteries-are-built-to-outlast-the-bike",
        "title": "How Pihilics Batteries Are Built to Outlast the Bike",
        "excerpt": "A look inside the cell chemistry and thermal management behind our 5-year capacity warranty.",
        "body": (
            "Every Pihilics pack starts life in the same qualification rig: thousands of charge cycles under "
            "punishing heat before a single cell is approved for a production bike. That process is why we're "
            "comfortable warrantying 80% capacity retention over five years of normal use. The Extended Battery "
            "Pack shares the exact same cell chemistry as the standard pack -- it's simply built with more of them, "
            "in the same footprint, so upgrading later never means compromising on reliability."
        ),
    },
    {
        "slug": "inside-the-pihilics-test-track",
        "title": "Inside the Pihilics Test Track: Building the RVX",
        "excerpt": "How our engineering team turned three years of trail testing into the RVX's final geometry.",
        "body": (
            "Long before the RVX had a name, it was a folder of geometry spreadsheets and a single mule frame "
            "that got rebuilt eleven times. Our test riders logged over 40,000 kilometers of trail time chasing "
            "one goal: a bike light enough to lift off a stuck rock, but planted enough to trust at speed. The "
            "removable battery pack was the last piece to click into place, and it's the one change that made "
            "every ride after it feel like a different bike."
        ),
    },
]


class Command(BaseCommand):
    help = (
        "Seed a comprehensive, spec-matching demo dataset for the Pihilics storefront."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-images",
            action="store_true",
            help="Skip fetching placeholder product photos.",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete previously-seeded data before reseeding.",
        )

    def handle(self, *args, **options):
        self.with_images = not options["no_images"]
        self.rng = random.Random(
            2026
        )  # fixed seed -> reproducible reviews/demo content

        with transaction.atomic():
            if options["flush"]:
                self.flush_seeded_data()

            self.seed_company_and_vat()
            categories = self.seed_categories()
            products = self.seed_products(categories)
            self.seed_reviews(products)
            dealers = self.seed_dealers()
            self.seed_financing_and_insurance()
            service_tiers = self.seed_service_tiers()
            self.seed_faqs()
            self.seed_stories()
            self.seed_promo_codes()
            users = self.seed_users(dealers)
            self.seed_carts(users, products)
            self.seed_orders(users, products)
            self.seed_bookings(users, products, dealers, service_tiers)
            self.seed_contact_messages(users)
            # Restores /terms/ and /privacy/ if their rows are missing --
            # see _seed_utils.ensure_legal_documents. Matters most right
            # after --flush, which is the exact path that stranded them.
            ensure_legal_documents(self.stdout)

        self.stdout.write(self.style.SUCCESS("Full seed data created."))

    # -- flush -------------------------------------------------------------

    def flush_seeded_data(self):
        Order.objects.all().delete()  # cascades OrderItem, ShipmentEvent
        TestRideBooking.objects.all().delete()
        ServiceBooking.objects.all().delete()
        # Demo users first: GarageEntry.product and TestRideBooking/
        # ServiceBooking.dealer are PROTECT, and GarageEntry.user is CASCADE,
        # so removing the users clears their GarageEntry rows before we try
        # to delete the Products/Dealers those rows point at.
        get_user_model().objects.filter(username__in=self._demo_usernames()).delete()
        Cart.objects.all().delete()  # cascades CartItem (catches guest carts too)
        Review.objects.all().delete()
        Product.objects.all().delete()  # cascades images/colors/sizes/specs/variants/related
        Category.objects.all().delete()
        Dealer.objects.all().delete()
        ServiceTier.objects.all().delete()
        FinancingPlan.objects.all().delete()
        InsuranceTier.objects.all().delete()
        FAQEntry.objects.all().delete()
        Story.objects.all().delete()
        ContactMessage.objects.all().delete()
        PromoCode.objects.all().delete()
        ShippingZone.objects.all().delete()
        self.stdout.write("  flushed previously-seeded data")

    @staticmethod
    def _demo_usernames():
        return ["staff.alger", "amina.benali", "yacine.haddad"]

    # -- core / programs -----------------------------------------------

    def seed_company_and_vat(self):
        company = CompanyInfo.get_solo()
        company.legal_name = "Pihilics SARL"
        company.trade_name = "Pihilics"
        company.tagline = "Electric bikes built for Algerian roads."
        company.registration_number = "RC 19/00-1234567 B 24"
        company.vat_number = "000119012345678"
        company.street = "Cite des Freres Meslem, Route de Bejaia"
        company.city = "Setif"
        company.postal_code = "19000"
        company.wilaya = "19"
        company.email = "contact@pihilics.dz"
        company.phone = "+213 36 55 01 00"
        company.website = "https://pihilics.dz"
        company.bank_name = "Banque Exterieure d'Algerie (BEA)"
        company.iban = "DZ5800400019123456789101"
        company.bic_swift = "BEXADZAL"
        company.invoice_footer_note = "Pihilics SARL - registered in Setif, Algeria."
        company.default_currency = "DZD"
        company.default_vat_rate = STANDARD_TVA_RATE
        # Sales receiving account for BaridiMob/CCP transfers -- shown to
        # customers at checkout and emailed with every transfer order.
        # Distinct from bank_name/iban/bic_swift above (the company's own
        # banking identity, printed on invoices, never customer-facing).
        company.sales_account_holder = "Pihilics SARL"
        company.sales_bank_name = "Algérie Poste"
        company.sales_rip = "00799999001234567890"
        company.sales_ccp_number = "1234567 89"
        # pihilics-product.com -- the SMTP relay's own domain (matches
        # settings.EMAIL_HOST_USER / ADMIN_NOTIFICATION_EMAIL), not
        # company.email above, which is the customer-facing pihilics.dz
        # contact address for general enquiries.
        company.sales_payment_email = "sales@pihilics-product.com"
        company.sales_payment_note = (
            "Transfers usually clear same-day. If you're paying by BaridiMob, "
            "the reference field accepts letters, so enter the order number exactly."
        )
        company.save()

        for wilaya, home_fee, desk_fee, days_min, days_max in SHIPPING_ZONES:
            ShippingZone.objects.get_or_create(
                wilaya=wilaya,
                defaults={
                    "home_fee": home_fee,
                    "desk_fee": desk_fee,
                    "delivery_days_min": days_min,
                    "delivery_days_max": days_max,
                },
            )
        self.stdout.write("  company info + shipping zones")

    def seed_financing_and_insurance(self):
        plans = [
            {
                "term_months": 12,
                "apr": Decimal("4.90"),
                "zero_down_option": False,
                "is_featured": False,
                "description": "Short-term financing with a fixed 4.90% APR.",
            },
            {
                "term_months": 24,
                "apr": Decimal("0.00"),
                "zero_down_option": True,
                "is_featured": True,
                "description": "Our most popular plan: 0% APR with a zero-down option.",
            },
            {
                "term_months": 36,
                "apr": Decimal("3.90"),
                "zero_down_option": False,
                "is_featured": False,
                "description": "Lower monthly payments over a longer term at 3.90% APR.",
            },
        ]
        for data in plans:
            FinancingPlan.objects.get_or_create(
                term_months=data["term_months"], defaults=data
            )

        tiers = [
            {
                "name": InsuranceTierName.ESSENTIAL,
                "monthly_price": Decimal("2900.00"),
                "is_featured": False,
                "excess_amount": None,
                "features": [
                    "Liability coverage",
                    "Theft protection",
                    "Fire & natural disaster cover",
                ],
            },
            {
                "name": InsuranceTierName.COMPREHENSIVE,
                "monthly_price": Decimal("5800.00"),
                "is_featured": True,
                "excess_amount": Decimal("37000.00"),
                "features": [
                    "Everything in Essential",
                    "Battery degradation cover",
                    "Accidental damage cover (37,000 DA excess)",
                ],
            },
            {
                "name": InsuranceTierName.PREMIUM,
                "monthly_price": Decimal("8800.00"),
                "is_featured": False,
                "excess_amount": Decimal("0.00"),
                "features": [
                    "Everything in Comprehensive",
                    "Zero-excess accidental damage",
                    "Up to 220,000 DA helmet & gear cover",
                ],
            },
        ]
        for data in tiers:
            InsuranceTier.objects.get_or_create(name=data["name"], defaults=data)
        self.stdout.write("  financing plans + insurance tiers")

    def seed_service_tiers(self):
        tiers = [
            {
                "name": ServiceTierName.ROUTINE_CHECK,
                "price": Decimal("13000.00"),
                "description": "Brakes, tyres, and software check.",
            },
            {
                "name": ServiceTierName.BATTERY_SERVICE,
                "price": Decimal("19000.00"),
                "description": "Battery health check and cell balancing.",
            },
            {
                "name": ServiceTierName.MAJOR_SERVICE,
                "price": Decimal("37000.00"),
                "description": "Full inspection and tune.",
            },
        ]
        result = {}
        for data in tiers:
            tier, _ = ServiceTier.objects.get_or_create(
                name=data["name"], defaults=data
            )
            result[data["name"]] = tier
        self.stdout.write("  service tiers")
        return result

    # -- catalog -------------------------------------------------------

    def seed_categories(self):
        categories = {}
        for name in ["Enduro", "Trail", "Adventure", "Performance"]:
            categories[name] = Category.objects.get_or_create(
                name=name, product_type=ProductType.MOTORCYCLE
            )[0]
        for name in ["Riding Gear", "Chargers", "Batteries", "Protection", "Parts"]:
            categories[name] = Category.objects.get_or_create(
                name=name, product_type=ProductType.ACCESSORY
            )[0]
        self.stdout.write("  categories")
        return categories

    def seed_products(self, categories):
        products = {}
        for data in MOTORCYCLES:
            products[data["slug"]] = self._create_product(
                data, ProductType.MOTORCYCLE, categories, with_variants=True
            )
        for data in ACCESSORIES:
            products[data["slug"]] = self._create_product(
                data, ProductType.ACCESSORY, categories, with_variants=False
            )
        self.stdout.write(
            f"  {len(products)} products ({len(MOTORCYCLES)} motorcycles, {len(ACCESSORIES)} accessories)"
        )
        return products

    def _create_product(self, data, product_type, categories, with_variants):
        product, created = Product.objects.get_or_create(
            slug=data["slug"],
            defaults={
                "name": data["name"],
                "product_type": product_type,
                "category": categories[data["category"]],
                "price": Decimal(data["price"]),
                "old_price": (
                    Decimal(data["old_price"]) if data.get("old_price") else None
                ),
                "description": data["description"],
                "features": data["features"],
                "badge": data.get("badge", ""),
                "stock_quantity": data.get("stock", 20),
                "low_stock_threshold": data.get("threshold", 5),
                "is_pre_order": data.get("pre_order", False),
            },
        )
        if not created:
            return product

        for color_name, hex_value in data.get("colors", []):
            ProductColor.objects.get_or_create(
                product=product, name=color_name, defaults={"hex_value": hex_value}
            )

        for label in data.get("sizes", []):
            ProductSize.objects.get_or_create(product=product, label=label)

        for sort_order, (key, value) in enumerate(data["specs"].items()):
            ProductSpec.objects.get_or_create(
                product=product,
                key=key,
                defaults={"value": value, "sort_order": sort_order},
            )

        if with_variants:
            for group_sort, (group_name, options) in enumerate(VARIANT_GROUP_TEMPLATE):
                group = VariantGroup.objects.create(
                    product=product, name=group_name, sort_order=group_sort
                )
                for opt_sort, (label, delta, is_default) in enumerate(options):
                    VariantOption.objects.create(
                        variant_group=group,
                        label=label,
                        price_delta=delta,
                        is_default=is_default,
                        sort_order=opt_sort,
                    )

        if self.with_images:
            for i in range(2):
                image_file = fetch_placeholder_image(
                    f"{data['slug']}-{i}", width=1000, height=750
                )
                if image_file:
                    ProductImage.objects.create(
                        product=product,
                        image=image_file,
                        alt_text=data["name"],
                        sort_order=i,
                    )

        return product

    def seed_reviews(self, products):
        authors = [
            "Lena Fischer",
            "Tom Bergmann",
            "Julia Novak",
            "Marcus Reid",
            "Ana Ferreira",
            "Chris Nolan",
            "Ines Duval",
            "Sam Okafor",
        ]
        motorcycle_titles = [
            "Exceeded expectations",
            "My daily rider",
            "Worth every dinar",
            "Great on the trail",
            "Solid first EV bike",
        ]
        accessory_titles = [
            "Does the job well",
            "Great fit and finish",
            "Would buy again",
            "Good value",
        ]
        bodies = [
            "Been using this for a few months now and it's held up better than I expected.",
            "Exactly as described. Delivery was quick and setup was painless.",
            "A little pricier than alternatives but the build quality justifies it.",
            "Recommended by a friend who owns one already, and I get why now.",
            "Does exactly what it says, no complaints so far.",
        ]

        motorcycles = [p for p in products.values() if p.is_motorcycle]
        accessories = [p for p in products.values() if p.is_accessory]
        created_count = 0

        for product in motorcycles:
            # Guard on existing reviews rather than a per-review natural key
            # (Review has none) -- keeps re-running this command from piling
            # up duplicate reviews on top of a previous seed run.
            if product.reviews.exists():
                continue
            for _ in range(2):
                Review.objects.create(
                    product=product,
                    author_name=self.rng.choice(authors),
                    rating=self.rng.choice([4, 4, 5, 5, 5]),
                    title=self.rng.choice(motorcycle_titles),
                    body=self.rng.choice(bodies),
                    is_approved=True,
                    is_verified_purchase=self.rng.choice([True, False]),
                )
                created_count += 1

        for product in accessories[
            ::2
        ]:  # every other accessory, to keep this proportionate
            if product.reviews.exists():
                continue
            Review.objects.create(
                product=product,
                author_name=self.rng.choice(authors),
                rating=self.rng.choice([3, 4, 4, 5]),
                title=self.rng.choice(accessory_titles),
                body=self.rng.choice(bodies),
                is_approved=True,
                is_verified_purchase=self.rng.choice([True, False]),
            )
            created_count += 1
        self.stdout.write(
            f"  reviews ({created_count} created)"
            if created_count
            else "  reviews already exist, skipped"
        )

    # -- dealers / content ---------------------------------------------

    def seed_dealers(self):
        dealers = {}
        for data in DEALERS:
            dealer, _ = Dealer.objects.get_or_create(
                slug=data["slug"],
                defaults={
                    "name": data["name"],
                    "city": data["city"],
                    "wilaya": data["wilaya"],
                    "address": data["address"],
                    "phone": data["phone"],
                    "email": f"{data['city'].lower()}@pihilics.dz",
                    "latitude": Decimal(data["lat"]),
                    "longitude": Decimal(data["lng"]),
                    "hours": "Mon-Fri 9:00-18:00, Sat 10:00-14:00",
                },
            )
            dealers[data["slug"]] = dealer
        self.stdout.write(f"  {len(dealers)} dealers")
        return dealers

    def seed_faqs(self):
        count = 0
        for category, entries in FAQS.items():
            for sort_order, (question, answer) in enumerate(entries):
                FAQEntry.objects.get_or_create(
                    category=category,
                    question=question,
                    defaults={"answer": answer, "sort_order": sort_order},
                )
                count += 1
        self.stdout.write(f"  {count} FAQ entries")

    def seed_stories(self):
        now = timezone.now()
        for i, data in enumerate(STORIES):
            Story.objects.get_or_create(
                slug=data["slug"],
                defaults={
                    "title": data["title"],
                    "excerpt": data["excerpt"],
                    "body": data["body"],
                    "is_published": True,
                    "published_at": now - timedelta(days=(len(STORIES) - i) * 14),
                },
            )
        self.stdout.write(f"  {len(STORIES)} journal stories")

    def seed_promo_codes(self):
        now = timezone.now()
        PromoCode.objects.get_or_create(
            code="WELCOME10",
            defaults={
                "discount_percent": Decimal("10.00"),
                "valid_from": now - timedelta(days=30),
                "valid_until": now + timedelta(days=335),
                "min_order_value": Decimal("0.00"),
            },
        )
        PromoCode.objects.get_or_create(
            code="SUMMER15",
            defaults={
                "discount_percent": Decimal("15.00"),
                "valid_from": now - timedelta(days=10),
                "valid_until": now + timedelta(days=80),
                "min_order_value": Decimal("5000.00"),
            },
        )
        self.stdout.write("  promo codes")

    # -- accounts --------------------------------------------------------

    def seed_users(self, dealers):
        User = get_user_model()
        users = {}

        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                username="admin",
                email="admin@pihilics-product.com",
                password="Pihilics#Admin2026",
            )
            self.stdout.write(
                "  superuser  ->  username: admin  /  password: Pihilics#Admin2026"
            )

        staff, created = User.objects.get_or_create(
            username="staff.alger",
            defaults={
                "email": "staff.alger@pihilics.dz",
                "first_name": "Karim",
                "last_name": "Belkacem",
            },
        )
        if created:
            staff.set_password("Pihilics#Staff2026")
            staff.save()
        profile = staff.profile
        profile.role = UserRole.DEALER_STAFF
        profile.dealer = dealers["pihilics-alger"]
        profile.phone = "+213 21 55 01 99"
        profile.save()
        users["staff"] = staff

        amina, created = User.objects.get_or_create(
            username="amina.benali",
            defaults={
                "email": "amina.benali@example.dz",
                "first_name": "Amina",
                "last_name": "Benali",
            },
        )
        if created:
            amina.set_password("Pihilics#Demo2026")
            amina.save()
        profile = amina.profile
        profile.phone = "+213 21 55 09 11"
        profile.preferred_language = "en"
        profile.marketing_opt_in = True
        profile.order_notifications_opt_in = True
        profile.save()
        Address.objects.get_or_create(
            user=amina,
            street="12 Rue Didouche Mourad",
            city="Alger Centre",
            postal_code="16000",
            wilaya="16",
            defaults={"label": "Home", "is_default": True},
        )
        users["amina"] = amina

        yacine, created = User.objects.get_or_create(
            username="yacine.haddad",
            defaults={
                "email": "yacine.haddad@example.dz",
                "first_name": "Yacine",
                "last_name": "Haddad",
            },
        )
        if created:
            yacine.set_password("Pihilics#Demo2026")
            yacine.save()
        profile = yacine.profile
        profile.phone = "+39 02 5559922"
        profile.preferred_language = "it"
        profile.save()
        Address.objects.get_or_create(
            user=yacine,
            street="45 Boulevard de l'ALN",
            city="Oran",
            postal_code="31000",
            wilaya="31",
            defaults={"label": "Home", "is_default": True},
        )
        users["yacine"] = yacine

        self.stdout.write(
            "  demo users (staff.alger, amina.benali, yacine.haddad)  ->  password: Pihilics#Demo2026 / Pihilics#Staff2026"
        )
        return users

    # -- cart / orders / bookings ----------------------------------------

    @staticmethod
    def _get_or_create_cart_item(
        cart,
        product,
        quantity,
        selected_color="",
        selected_size="",
        selected_upgrades=None,
    ):
        """
        CartItem's real identity is (cart, product, options_key), where
        options_key is a hash computed in CartItem.save() -- not something
        we can pass as a plain get_or_create() lookup value up front. Compute
        it the same way CartItem does, so re-running this command finds the
        existing line instead of colliding with its unique constraint.
        """
        selected_upgrades = selected_upgrades or []
        probe = CartItem(
            selected_color=selected_color,
            selected_size=selected_size,
            selected_upgrades=selected_upgrades,
        )
        options_key = probe.compute_options_key()
        item, _ = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            options_key=options_key,
            defaults={
                "quantity": quantity,
                "selected_color": selected_color,
                "selected_size": selected_size,
                "selected_upgrades": selected_upgrades,
            },
        )
        return item

    def seed_carts(self, users, products):
        cart, _ = Cart.objects.get_or_create(user=users["amina"])
        self._get_or_create_cart_item(
            cart, products["touring-gloves"], quantity=1, selected_size="M"
        )

        guest_cart, _ = Cart.objects.get_or_create(
            session_key="demo-guest-session", user=None
        )
        self._get_or_create_cart_item(
            guest_cart, products["carbon-helmet"], quantity=1, selected_size="L"
        )
        self.stdout.write("  carts (1 account cart, 1 guest cart)")

    def seed_orders(self, users, products):
        if Order.objects.exists():
            self.stdout.write("  orders already exist, skipped")
            return

        # Mirrors core.utils.get_vat_rate / get_shipping_cost rather than
        # re-deriving them: one national TVA rate, and a per-wilaya shipping
        # fee that falls back to the flat constant for an unpriced wilaya.
        zone_fees = {
            z.wilaya: z.home_fee for z in ShippingZone.objects.filter(is_active=True)
        }
        checkout_settings = CheckoutSettings.get_solo()

        def make_order(
            *,
            user,
            guest_email,
            guest_name,
            wilaya,
            city,
            street,
            postal_code,
            status,
            payment_method,
            lines,
            financing=None,
            insurance=None,
            days_ago=10,
        ):
            subtotal = sum(products[slug].price * qty for slug, qty, _ in lines)
            vat_rate = STANDARD_TVA_RATE
            vat_amount = (subtotal * vat_rate / Decimal("100")).quantize(
                Decimal("0.01")
            )
            shipping_cost = (
                Decimal("0.00")
                if subtotal >= checkout_settings.free_shipping_threshold
                else zone_fees.get(wilaya, checkout_settings.standard_shipping_fee)
            )

            order = Order.objects.create(
                user=user,
                guest_email=guest_email,
                guest_name=guest_name,
                status=status,
                contact_first_name=(
                    user.first_name if user else guest_name.split(" ")[0]
                ),
                contact_last_name=(
                    user.last_name if user else guest_name.split(" ")[-1]
                ),
                contact_email=(user.email if user else guest_email),
                contact_phone="+213 21 55 09 11",
                delivery_street=street,
                delivery_city=city,
                delivery_postal_code=postal_code,
                delivery_wilaya=wilaya,
                delivery_method=DeliveryMethod.STANDARD,
                payment_method=payment_method,
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                vat_amount=vat_amount,
                discount_amount=Decimal("0.00"),
                total=Decimal("0.00"),
                financing_plan=financing,
                insurance_tier=insurance,
            )
            for slug, qty, options in lines:
                product = products[slug]
                order.items.create(
                    product=product,
                    product_name_snapshot=product.name,
                    unit_price_snapshot=product.price,
                    quantity=qty,
                    selected_options_snapshot=options,
                )
            order.recompute_total(save=True)
            order.placed_at = timezone.now() - timedelta(days=days_ago)
            order.save(update_fields=["placed_at"])
            return order

        financing_24 = FinancingPlan.objects.filter(term_months=24).first()
        insurance_comprehensive = InsuranceTier.objects.filter(
            name=InsuranceTierName.COMPREHENSIVE
        ).first()

        # Delivered order for Amina: a motorcycle + an accessory, financed, insured.
        order_a = make_order(
            user=users["amina"],
            guest_email="",
            guest_name="",
            wilaya="16",
            city="Alger Centre",
            street="12 Rue Didouche Mourad",
            postal_code="16000",
            status=OrderStatus.DELIVERED,
            payment_method=PaymentMethod.CIB,
            lines=[
                ("pihilics-rvx", 1, {"color": "Graphite Black", "upgrades": []}),
                ("riding-jacket", 1, {"size": "M"}),
            ],
            financing=financing_24,
            insurance=insurance_comprehensive,
            days_ago=45,
        )
        # orders.signals.seed_shipment_timeline already created one ShipmentEvent
        # row per ShipmentStage the moment order_a was saved above (Order Tracking,
        # spec 6.11) -- update those existing rows with this order's richer demo
        # detail (carrier/tracking number, real per-stage timestamps, all complete)
        # rather than creating new ones, which would collide with the
        # unique_stage_per_order constraint those signal-created rows already hold.
        for i, (stage_value, _label) in enumerate(ShipmentStage.choices):
            ShipmentEvent.objects.filter(order=order_a, stage=stage_value).update(
                carrier="Yalidine Express",
                tracking_number="YAL-88451203",
                occurred_at=order_a.placed_at + timedelta(days=i * 4),
                is_complete=True,
            )

        # Processing order for Amina: a battery pack, partially shipped.
        order_b = make_order(
            user=users["amina"],
            guest_email="",
            guest_name="",
            wilaya="16",
            city="Alger Centre",
            street="12 Rue Didouche Mourad",
            postal_code="16000",
            status=OrderStatus.PROCESSING,
            payment_method=PaymentMethod.MANUAL,
            lines=[("extended-battery", 1, {})],
            days_ago=2,
        )
        # Same reasoning as order_a above: update the signal-seeded rows for the
        # first two stages to "complete"; the remaining stages are left exactly
        # as the signal already set them (pending, no timestamp) -- no update
        # needed there, since that's already the default state.
        for i, (stage_value, _label) in enumerate(list(ShipmentStage.choices)[:2]):
            ShipmentEvent.objects.filter(order=order_b, stage=stage_value).update(
                occurred_at=order_b.placed_at + timedelta(days=i),
                is_complete=True,
            )

        # Shipped order for Yacine: a motorcycle, delivered to Oran.
        make_order(
            user=users["yacine"],
            guest_email="",
            guest_name="",
            wilaya="31",
            city="Oran",
            street="45 Boulevard de l'ALN",
            postal_code="31000",
            status=OrderStatus.SHIPPED,
            payment_method=PaymentMethod.MANUAL,
            lines=[("trail-s", 1, {"color": "Forest Green", "upgrades": []})],
            days_ago=6,
        )

        # Guest checkout order: no account, just an accessory.
        make_order(
            user=None,
            guest_email="guest.rider@example.com",
            guest_name="Guest Rider",
            wilaya="25",
            city="Constantine",
            street="8 Rue Larbi Ben M'hidi",
            postal_code="25000",
            status=OrderStatus.PROCESSING,
            payment_method=PaymentMethod.CIB,
            lines=[("touring-gloves", 1, {"size": "L"})],
            days_ago=1,
        )

        # BaridiMob order for Yacine, transfer proof already uploaded and
        # sitting in the review queue -- gives the admin's PaymentProof list
        # (orders/admin.py) and the customer's /orders/<ref>/payment/ page
        # something real to render without anyone having to walk through
        # checkout by hand first.
        order_d = make_order(
            user=users["yacine"],
            guest_email="",
            guest_name="",
            wilaya="31",
            city="Oran",
            street="45 Boulevard de l'ALN",
            postal_code="31000",
            status=OrderStatus.PROCESSING,
            payment_method=PaymentMethod.BARIDIMOB,
            lines=[("touring-gloves", 1, {"size": "L"})],
            days_ago=1,
        )
        # orders.signals.initialise_payment_state already set order_d to
        # AWAITING_PROOF on creation; uploading the demo proof below drives
        # it on to UNDER_REVIEW through the real signal, the same as a
        # customer's own upload would.
        order_d.payment_proofs.create(
            file=ContentFile(SEED_PAYMENT_PROOF_PNG, name="baridimob-receipt.png"),
            amount_declared=order_d.total,
            transaction_reference="BM-2026-771402",
            sender_note="Sent via BaridiMob this morning, let me know if anything else is needed.",
        )

        self.stdout.write(
            "  orders (5, including shipment timelines + one BaridiMob proof)"
        )

    def seed_bookings(self, users, products, dealers, service_tiers):
        # Looked up by who/what rather than by date: date/time_slot are
        # relative to "today" (spec requires at least tomorrow), so a lookup
        # that included them would create a fresh duplicate every time this
        # command is re-run on a different day.
        tomorrow_plus = lambda days: timezone.localdate() + timedelta(days=days)

        # Slots come from the bookings.TimeSlot table now, not a constant,
        # so take the first two active ones rather than assuming any code.
        slots = [code for code, _label in time_slot_choices()]
        morning_slot, afternoon_slot = slots[0], slots[1 if len(slots) > 1 else 0]

        TestRideBooking.objects.get_or_create(
            product=products["pihilics-rvx"],
            dealer=dealers["pihilics-alger"],
            first_name="Nadia",
            last_name="Cherif",
            defaults={
                "date": tomorrow_plus(7),
                "time_slot": morning_slot,
                "email": "nadia.cherif@example.dz",
                "phone": "+213 21 55 12 34",
                "license_number": "DZ-LIC-88213",
                "waiver_acknowledged": True,
                "status": BookingStatus.REQUESTED,
            },
        )

        garage_entry = (
            users["amina"].garage_entries.filter(product__slug="pihilics-rvx").first()
        )
        ServiceBooking.objects.get_or_create(
            product=products["pihilics-rvx"],
            dealer=dealers["pihilics-alger"],
            contact_email=users["amina"].email,
            defaults={
                "date": tomorrow_plus(14),
                "time_slot": afternoon_slot,
                "garage_entry": garage_entry,
                "service_tier": service_tiers[ServiceTierName.ROUTINE_CHECK],
                "user": users["amina"],
                "contact_first_name": "Amina",
                "contact_last_name": "Benali",
                "contact_phone": "+213 21 55 09 11",
                "status": BookingStatus.CONFIRMED,
            },
        )
        self.stdout.write("  bookings (1 test ride, 1 service)")

    def seed_contact_messages(self, users):
        ContactMessage.objects.get_or_create(
            email="prospect@example.com",
            subject="Fleet pricing for 5 units",
            defaults={
                "department": ContactDepartment.SALES,
                "name": "Priya Shah",
                "message": "Interested in a small fleet purchase for a rental business -- is bulk pricing available?",
            },
        )
        ContactMessage.objects.get_or_create(
            email=users["amina"].email,
            subject="Question about my Battery Service booking",
            defaults={
                "department": ContactDepartment.SUPPORT,
                "name": "Amina Martin",
                "user": users["amina"],
                "message": "Can I move my upcoming service appointment to the following week instead?",
            },
        )
        self.stdout.write("  contact messages")
