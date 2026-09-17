"""
management command: seed_minimal

Creates the smallest data set the storefront needs to actually work end to
end: a couple of categories, a handful of products with real photos, one
dealer, VAT/financing/insurance so Checkout has something to offer, and one
admin login. Everything is get_or_create'd on a natural key, so running the
command again is a no-op rather than a pile of duplicates.

Usage:
    python manage.py seed_minimal
    python manage.py seed_minimal --no-images   (skip the network image fetch)
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from bookings.models import ServiceTier, ServiceTierName
from catalog.models import (
    Category,
    Product,
    ProductColor,
    ProductImage,
    ProductSize,
    ProductSpec,
    ProductType,
    VariantGroup,
    VariantOption,
)
from core.models import CompanyInfo, ShippingZone
from dealers.models import Dealer
from programs.models import FinancingPlan, InsuranceTier, InsuranceTierName

from ._seed_utils import ensure_legal_documents, fetch_placeholder_image

# Algeria applies one national TVA rate, so there is no per-wilaya rate table
# to seed: CompanyInfo.default_vat_rate (19%) covers every order, and
# core.utils.get_vat_rate falls back to it whenever a wilaya has no explicit
# VATRate row -- which, here, is all of them. See the VATRate docstring.
STANDARD_TVA_RATE = Decimal("19.00")

# A starter shipping zone per seeded dealer wilaya. Real Algerian courier
# pricing: the north is cheap and fast, the far south costs more and takes
# longer. Wilayas with no row fall back to the flat constants in
# core.constants, so checkout still works before an admin prices the rest.
SHIPPING_ZONES = [
    # (wilaya, home_fee, desk_fee, days_min, days_max)
    ("16", Decimal("500.00"), Decimal("300.00"), 1, 2),   # Alger
    ("19", Decimal("600.00"), Decimal("350.00"), 2, 3),   # Setif
    ("31", Decimal("650.00"), Decimal("400.00"), 2, 3),   # Oran
    ("25", Decimal("700.00"), Decimal("400.00"), 2, 4),   # Constantine
    ("30", Decimal("1000.00"), Decimal("600.00"), 4, 6),  # Ouargla
    ("11", Decimal("1400.00"), Decimal("900.00"), 5, 8),  # Tamanrasset
]


class Command(BaseCommand):
    help = "Seed the minimum data needed to browse and check out the storefront."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-images",
            action="store_true",
            help="Skip fetching placeholder product photos (faster, works offline).",
        )

    def handle(self, *args, **options):
        self.with_images = not options["no_images"]
        with transaction.atomic():
            self.seed_company_and_vat()
            categories = self.seed_categories()
            self.seed_products(categories)
            self.seed_dealer()
            self.seed_financing_and_insurance()
            self.seed_service_tiers()
            self.seed_admin_user()
            # Restores /terms/ and /privacy/ if their rows are missing --
            # see _seed_utils.ensure_legal_documents for why seeding, not
            # only the 0003/0008 migrations, has to own this.
            ensure_legal_documents(self.stdout)
        self.stdout.write(self.style.SUCCESS("Minimal seed data created."))

    # -- steps -----------------------------------------------------------

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
        company.default_currency = "DZD"
        company.default_vat_rate = STANDARD_TVA_RATE
        company.sales_account_holder = "Pihilics SARL"
        company.sales_bank_name = "Algérie Poste"
        company.sales_rip = "00799999001234567890"
        company.sales_ccp_number = "1234567 89"
        # Deliberately the SMTP relay's own pihilics-product.com domain
        # (settings.EMAIL_HOST_USER / ADMIN_NOTIFICATION_EMAIL), matching
        # the mailbox that already receives and sends this account's mail
        # -- not company.email above, which is the customer-facing
        # pihilics.dz contact address for general enquiries.
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
                    "home_fee": home_fee, "desk_fee": desk_fee,
                    "delivery_days_min": days_min, "delivery_days_max": days_max,
                },
            )
        self.stdout.write("  company info + shipping zones")

    def seed_categories(self):
        specs = [
            ("Enduro", ProductType.MOTORCYCLE),
            ("Adventure", ProductType.MOTORCYCLE),
            ("Riding Gear", ProductType.ACCESSORY),
            ("Batteries", ProductType.ACCESSORY),
        ]
        categories = {}
        for name, product_type in specs:
            category, _ = Category.objects.get_or_create(name=name, product_type=product_type)
            categories[name] = category
        self.stdout.write("  categories")
        return categories

    def seed_products(self, categories):
        motorcycles = [
            {
                "slug": "pihilics-rvx",
                "name": "Pihilics RVX",
                "category": categories["Enduro"],
                "price": Decimal("1875000.00"),
                "description": "Pihilics' flagship enduro: a lightweight electric off-roader built for technical trails.",
                "features": ["Adjustable regenerative braking", "Removable battery pack", "IP67-rated electronics"],
                "specs": {
                    "Range": "180 km", "Power": "35 kW", "Weight": "128 kg",
                    "Top Speed": "140 km/h", "Battery Capacity": "9.6 kWh", "Charge Time": "3.5 h",
                },
                "colors": [("Graphite Black", "#1a1a1a"), ("Racing Red", "#c81e2c")],
            },
            {
                "slug": "pihilics-adventure-x",
                "name": "Pihilics Adventure X",
                "category": categories["Adventure"],
                "price": Decimal("2370000.00"),
                "description": "A long-range electric adventure bike built for multi-day touring off the grid.",
                "features": ["Long-range battery", "Integrated luggage mounts", "Heated grips"],
                "specs": {
                    "Range": "260 km", "Power": "40 kW", "Weight": "155 kg",
                    "Top Speed": "150 km/h", "Battery Capacity": "13.2 kWh", "Charge Time": "4.5 h",
                },
                "colors": [("Desert Sand", "#c9b28c"), ("Graphite Black", "#1a1a1a")],
            },
        ]
        accessories = [
            {
                "slug": "riding-jacket",
                "name": "Pihilics Riding Jacket",
                "category": categories["Riding Gear"],
                "price": Decimal("52000.00"),
                "description": "Abrasion-resistant riding jacket with removable armour and ventilation panels.",
                "features": ["CE-rated armour", "Waterproof liner", "Reflective panels"],
                "specs": {"Material": "600D textile", "Weight": "1.4 kg"},
                "sizes": ["S", "M", "L", "XL"],
            },
            {
                "slug": "extended-battery",
                "name": "Extended Battery Pack",
                "category": categories["Batteries"],
                "price": Decimal("330000.00"),
                "description": "Drop-in extended-capacity battery pack, compatible with the full Pihilics lineup.",
                "features": ["+40% range", "Same footprint as stock pack", "5-year capacity warranty"],
                "specs": {"Capacity": "13.2 kWh", "Weight": "38 kg"},
                "sizes": [],
            },
        ]

        for data in motorcycles:
            self._create_product(data, ProductType.MOTORCYCLE, with_variants=True)
        for data in accessories:
            self._create_product(data, ProductType.ACCESSORY, with_variants=False)
        self.stdout.write("  products")

    def _create_product(self, data, product_type, with_variants):
        product, created = Product.objects.get_or_create(
            slug=data["slug"],
            defaults={
                "name": data["name"],
                "product_type": product_type,
                "category": data["category"],
                "price": data["price"],
                "description": data["description"],
                "features": data["features"],
                "stock_quantity": 25,
                "low_stock_threshold": 5,
            },
        )
        if not created:
            return product

        for i, (color_name, hex_value) in enumerate(data.get("colors", [])):
            ProductColor.objects.get_or_create(product=product, name=color_name, defaults={"hex_value": hex_value})

        for label in data.get("sizes", []):
            ProductSize.objects.get_or_create(product=product, label=label)

        for sort_order, (key, value) in enumerate(data["specs"].items()):
            ProductSpec.objects.get_or_create(product=product, key=key, defaults={"value": value, "sort_order": sort_order})

        if with_variants:
            battery = VariantGroup.objects.create(product=product, name="Battery", sort_order=0)
            VariantOption.objects.create(variant_group=battery, label="Standard", is_default=True, sort_order=0)
            VariantOption.objects.create(variant_group=battery, label="Extended Range", price_delta=Decimal("270000.00"), sort_order=1)

        if self.with_images:
            image_file = fetch_placeholder_image(data["slug"], width=900, height=675)
            if image_file:
                ProductImage.objects.create(product=product, image=image_file, alt_text=data["name"], sort_order=0)

        return product

    def seed_dealer(self):
        Dealer.objects.get_or_create(
            slug="pihilics-setif",
            defaults={
                "name": "Pihilics Setif",
                "city": "Setif",
                "wilaya": "19",
                "address": "Cite des Freres Meslem, Route de Bejaia, 19000 Setif",
                "phone": "+213 36 55 01 01",
                "email": "setif@pihilics.dz",
                "latitude": Decimal("36.190073"),
                "longitude": Decimal("5.408341"),
                "hours": "Sat-Thu 9:00-18:00, closed Friday",
            },
        )
        self.stdout.write("  dealer")

    def seed_financing_and_insurance(self):
        FinancingPlan.objects.get_or_create(
            term_months=24,
            defaults={
                "apr": Decimal("0.00"),
                "description": "24-month plan with a 0% APR, zero-down promotional option.",
                "zero_down_option": True,
                "is_featured": True,
            },
        )
        InsuranceTier.objects.get_or_create(
            name=InsuranceTierName.COMPREHENSIVE,
            defaults={
                "monthly_price": Decimal("5800.00"),
                "features": ["Liability, theft, fire & natural disaster", "Battery degradation cover", "Accidental damage (37,000 DA excess)"],
                "excess_amount": Decimal("37000.00"),
                "is_featured": True,
            },
        )
        self.stdout.write("  financing + insurance")

    def seed_service_tiers(self):
        ServiceTier.objects.get_or_create(
            name=ServiceTierName.ROUTINE_CHECK,
            defaults={"price": Decimal("13000.00"), "description": "Brakes, tyres, and software check."},
        )
        self.stdout.write("  service tier")

    def seed_admin_user(self):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(username="admin", email="admin@pihilics.dz", password="Pihilics#Admin2026")
            self.stdout.write("  superuser  ->  username: admin  /  password: Pihilics#Admin2026")
        else:
            self.stdout.write("  superuser 'admin' already exists, skipped")
