from django.db import models
from django.utils.text import slugify


class SingletonContentModel(models.Model):
    """
    Base for a page's copy that must have exactly one row (pk=1) --
    mirrors core.models.CompanyInfo's own singleton pattern (same save()/
    delete()/get_solo() shape) so Home, About, Support, and the 404 page
    each get one admin-editable row instead of an ever-growing table.
    Unlike CompanyInfo, every field below has a real default equal to the
    copy the static reference shipped, so `get_solo()` needs no explicit
    `defaults=` -- Django applies the field defaults on first creation.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # singleton: configuration, not deletable

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class FAQCategory(models.TextChoices):
    ORDERS_DELIVERY = "orders_delivery", "Orders & Delivery"
    BATTERY_CHARGING = "battery_charging", "Battery & Charging"
    WARRANTY_SERVICE = "warranty_service", "Warranty & Service"
    TEST_RIDES_PURCHASING = "test_rides_purchasing", "Test Rides & Purchasing"


class FAQEntry(models.Model):
    """Categorized Support/Help Center content (spec 8.7, 6.20)."""

    category = models.CharField(max_length=30, choices=FAQCategory.choices)
    question = models.CharField(max_length=255)
    answer = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "FAQ Entry"
        verbose_name_plural = "FAQ Entries"
        ordering = ["category", "sort_order", "id"]

    def __str__(self):
        return self.question


class Story(models.Model):
    """Journal article (spec 9.3)."""

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    excerpt = models.CharField(max_length=300, blank=True)
    body = models.TextField()
    cover_image = models.ImageField(upload_to="stories/", blank=True, null=True)
    published_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Home page (CMS dynamization)
# ---------------------------------------------------------------------------


class HomePageContent(SingletonContentModel):
    """Home's editorial copy (spec 9.1). Product grids, categories, the
    flagship split, and testimonials already come from real Product/
    Category/Review rows via content.views.home_view -- only the brand
    copy that has no other model to live on lives here."""

    hero_eyebrow = models.CharField(max_length=60, default="Electric Off-Road")
    hero_title_line1 = models.CharField(max_length=80, default="TERRAIN THAT")
    hero_title_line2 = models.CharField(max_length=80, default="DOESN'T FORGIVE")
    hero_subtitle = models.TextField(
        default="Instant torque. Hot-swap batteries. Zero emissions. Built for "
        "Algerian roads and the tracks beyond them."
    )
    hero_image = models.ImageField(
        upload_to="home/",
        blank=True,
        null=True,
        help_text="Optional. Falls back to the flagship motorcycle's own photo when empty.",
    )

    compare_eyebrow = models.CharField(max_length=60, default="Side by Side")
    compare_title = models.CharField(max_length=100, default="Compare Models")
    compare_body = models.TextField(
        default="Stack up to 4 models side by side. Compare range, power, "
        "weight, and price to find the right bike for your riding style."
    )

    testride_eyebrow = models.CharField(max_length=60, default="Experience Before You Buy")
    testride_title = models.CharField(max_length=100, default="Ride Before You Decide")
    testride_body = models.TextField(
        default="Book a free test ride at any of our {dealer_count} dealers "
        "across the country. Bring your licence, we'll bring the bike.",
        help_text="Use the literal text \"{dealer_count}\" anywhere you want the "
        "live dealer count inserted.",
    )

    # -- Battery swap (landing-page-v1 "04 — BATTERY SWAP") -----------------
    battery_eyebrow = models.CharField(max_length=60, default="Field-Ready Power")
    battery_title_line1 = models.CharField(max_length=60, default="SWAP IN")
    battery_title_line2 = models.CharField(max_length=60, default="30 SECONDS.")
    battery_body = models.TextField(
        default="No cables, no chargers, no waiting at the trailhead. Pull "
        "the spent cell, drop in a charged one, and get back on the line."
    )
    battery_image = models.ImageField(
        upload_to="home/",
        blank=True,
        null=True,
        help_text="Optional. Falls back to the flagship motorcycle's own photo when empty.",
    )

    # -- Cinematic banner (landing-page-v1 "08 — CINEMATIC VIDEO") ----------
    cine_title_line1 = models.CharField(max_length=60, default="GO WHERE")
    cine_title_line2 = models.CharField(max_length=60, default="THE ROAD ENDS.")
    cine_image = models.ImageField(
        upload_to="home/",
        blank=True,
        null=True,
        help_text="Poster/background image. Falls back to the flagship "
        "motorcycle's own photo when empty.",
    )
    cine_video = models.FileField(
        upload_to="home/video/",
        blank=True,
        null=True,
        help_text="Optional. MP4 film played muted-loop behind the banner. "
        "When empty, cine_image is shown as a static banner instead.",
    )

    # -- Final CTA (landing-page-v1 "11 — FINAL CTA") ------------------------
    final_cta_title_line1 = models.CharField(max_length=60, default="YOUR TRAIL")
    final_cta_title_line2 = models.CharField(max_length=60, default="IS WAITING.")
    final_cta_body = models.TextField(
        default="Built for riders who don't need a road to know where "
        "they're going. Reserve yours before the first production run closes."
    )
    final_cta_image = models.ImageField(
        upload_to="home/",
        blank=True,
        null=True,
        help_text="Optional. Falls back to the flagship motorcycle's own photo when empty.",
    )

    class Meta:
        verbose_name = "Home Page Content"
        verbose_name_plural = "Home Page Content"

    def __str__(self):
        return "Home Page Content"


class HomeHeroStat(models.Model):
    """One of the hero's headline claims (e.g. \"120 km / Max Range\"). A
    real relation rather than four fixed columns so admins can add, remove,
    or reorder claims without a migration -- same reasoning as FAQEntry's
    sort_order. These are brand-wide claims across the whole lineup, not
    one product's spec sheet (see home_view), so they stay free text."""

    home = models.ForeignKey(HomePageContent, related_name="hero_stats", on_delete=models.CASCADE)
    value = models.CharField(max_length=30, help_text='e.g. "120 km"')
    label = models.CharField(max_length=40, help_text='e.g. "Max Range"')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Hero Stat"

    def __str__(self):
        return f"{self.value} — {self.label}"


class HomeMarqueeItem(models.Model):
    """One claim in the scrolling marquee band (e.g. \"FREE EU DELIVERY\").
    The live dealer-count claim is appended by the template itself, since
    it's computed, not admin copy -- see templates/content/home.html."""

    home = models.ForeignKey(HomePageContent, related_name="marquee_items", on_delete=models.CASCADE)
    text = models.CharField(max_length=60)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Marquee Item"

    def __str__(self):
        return self.text


class HomeCarouselSlide(models.Model):
    """One frame of the Home "Every Angle" detail carousel (landing-page-v1
    "09 — CAROUSEL"). Same FK + sort_order shape as HomeHeroStat/
    HomeMarqueeItem so admins can add, remove, or reorder frames without a
    migration. When no admin rows exist, home_view falls back to the
    flagship product's own gallery so a fresh install still has something
    to show -- see that view's comment."""

    home = models.ForeignKey(HomePageContent, related_name="carousel_slides", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="home/carousel/")
    caption = models.CharField(max_length=80, blank=True, help_text='e.g. "Studio · Front"')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Carousel Slide"

    def __str__(self):
        return self.caption or f"Slide {self.pk}"


class HomeShowcasePanel(models.Model):
    """One panel of the Home horizontal feature showcase (landing-page-v1
    "05 — HORIZONTAL FEATURES", e.g. "Ride in silence" / "Instant torque").
    Each panel pairs one media asset with its own claim, so -- like
    HomeCarouselSlide -- it is modeled as admin-manageable rows rather than
    a fixed set of columns."""

    home = models.ForeignKey(HomePageContent, related_name="showcase_panels", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="home/showcase/")
    title = models.CharField(max_length=60, help_text='e.g. "Instant torque."')
    body = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Showcase Panel"

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# About page (CMS dynamization)
# ---------------------------------------------------------------------------


class AboutPageContent(SingletonContentModel):
    """About's editorial copy (spec 9.2). Model counts (motorcycle_count,
    dealer_count) stay computed in about_view, not stored here, so they can
    never drift from the real catalog/dealer network -- see that view's
    own comment on why only the two unbacked stats are admin copy."""

    hero_eyebrow = models.CharField(max_length=60, default="Our Story")
    hero_title_line1 = models.CharField(max_length=80, default="BUILT TO BREAK")
    hero_title_line2 = models.CharField(max_length=80, default="THE SILENCE")
    hero_subtitle = models.TextField(
        default="Founded in 2021 in Setif, we build electric motorcycles "
        "for riders who go where the road ends. No noise. No emissions. No compromise."
    )
    hero_image = models.ImageField(
        upload_to="about/",
        blank=True,
        null=True,
        help_text="Optional. Falls back to the flagship motorcycle's own photo when empty.",
    )

    mission_eyebrow = models.CharField(max_length=60, default="The Mission")
    mission_title = models.CharField(max_length=120, default="Terrain Doesn't Forgive. Neither Do We.")
    mission_paragraph_1 = models.TextField(
        default="We started this company because electric motorcycles were either "
        "street scooters or expensive prototypes. We wanted a bike that "
        "could handle a hard enduro stage on Saturday and commute to work "
        "on Monday — all electric, all silent, all torque."
    )
    mission_paragraph_2 = models.TextField(
        default="Every bike is designed and assembled in our Setif "
        "facility. We forge our own frames, wind our own motors, and test "
        "every bike in the Babor mountains before it ships."
    )
    mission_paragraph_3 = models.TextField(
        default="We believe electric is not a compromise — it's an "
        "advantage. Instant torque. Zero maintenance. Silent operation "
        "that lets you hear the trail instead of the engine."
    )
    mission_image = models.ImageField(
        upload_to="about/",
        blank=True,
        null=True,
        help_text="Optional. Falls back to the flagship motorcycle's own photo when empty.",
    )

    stats_eyebrow = models.CharField(max_length=60, default="By the Numbers")
    stats_title = models.CharField(max_length=100, default="By the Numbers, 2026")
    riders_stat_value = models.CharField(max_length=20, default="15K+")
    riders_stat_label = models.CharField(max_length=40, default="Riders Nationwide")
    co2_stat_value = models.CharField(max_length=20, default="0g")
    co2_stat_label = models.CharField(max_length=40, default="CO2 Per Km")

    values_eyebrow = models.CharField(max_length=60, default="What We Believe")
    values_title = models.CharField(max_length=100, default="Our Values")

    timeline_eyebrow = models.CharField(max_length=60, default="The Journey")
    timeline_title = models.CharField(max_length=100, default="Our Timeline")

    team_eyebrow = models.CharField(max_length=60, default="The People")
    team_title = models.CharField(max_length=100, default="Leadership")

    cta_eyebrow = models.CharField(max_length=60, default="Join the Ride")
    cta_title = models.CharField(max_length=100, default="Ready to Go Electric?")
    cta_body = models.TextField(
        default="Book a test ride at your nearest dealer and feel the "
        "instant torque for yourself."
    )

    class Meta:
        verbose_name = "About Page Content"
        verbose_name_plural = "About Page Content"

    def __str__(self):
        return "About Page Content"


class ValueProp(models.Model):
    """One "Our Values" card."""

    about = models.ForeignKey(AboutPageContent, related_name="values", on_delete=models.CASCADE)
    icon = models.CharField(max_length=40, default="bx-bolt", help_text='Boxicons class, e.g. "bx-bolt"')
    title = models.CharField(max_length=80)
    body = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Value"

    def __str__(self):
        return self.title


class TimelineEvent(models.Model):
    """One "Our Timeline" milestone."""

    about = models.ForeignKey(AboutPageContent, related_name="timeline_events", on_delete=models.CASCADE)
    year = models.CharField(max_length=10)
    title = models.CharField(max_length=100)
    body = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Timeline Event"

    def __str__(self):
        return f"{self.year} — {self.title}"


class TeamMember(models.Model):
    """One "Leadership" card."""

    about = models.ForeignKey(AboutPageContent, related_name="team_members", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    photo = models.ImageField(upload_to="team/", blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Team Member"

    def __str__(self):
        return f"{self.name} — {self.role}"


# ---------------------------------------------------------------------------
# Support page (CMS dynamization)
# ---------------------------------------------------------------------------


class SupportPageContent(SingletonContentModel):
    """Support/Help Center's contact-panel copy (spec 6.20, 9). Phone/email
    used elsewhere as the company's general line stay on core.CompanyInfo
    (single source of truth); the two *department* mailboxes shown here and
    the hours/live-chat copy have no other home."""

    email_support = models.EmailField(default="support@pihilics.dz")
    email_sales = models.EmailField(default="sales@pihilics.dz")
    email_response_note = models.CharField(max_length=120, default="Get a response within 24 hours.")
    # Algeria's working week runs Sunday to Thursday (Friday/Saturday is the
    # weekend), so the inherited "Mon-Fri ... CET" line advertised the wrong
    # days. The zone itself is right -- Algeria is UTC+1 year-round, with no
    # daylight saving -- but it reads as foreign here, so it's dropped.
    hours_text = models.CharField(max_length=80, default="Sun–Thu 9:00–17:00")
    livechat_text = models.CharField(max_length=80, default="Live chat available 24/7")

    class Meta:
        verbose_name = "Support Page Content"
        verbose_name_plural = "Support Page Content"

    def __str__(self):
        return "Support Page Content"


# ---------------------------------------------------------------------------
# Legal pages (CMS dynamization)
# ---------------------------------------------------------------------------


class LegalDocument(models.Model):
    """Terms of Service / Privacy Policy (spec 9.4/9.5). Legal text is one
    editorial blob, not a set of structured fields -- `body` holds the full
    HTML for everything between the page header and the closing wrapper
    (table of contents included), same shape a real CMS's rich-text field
    would give an admin. Company identity is merged in via `{legal_name}`-
    style placeholders (see content.utils.merge_company_fields) rather than
    hardcoded, so a registered-address or VAT change never leaves the page
    stale -- see the reasoning already captured in the old inline template
    comment this model replaces."""

    slug = models.SlugField(max_length=40, unique=True, help_text='e.g. "terms", "privacy"')
    title = models.CharField(max_length=100)
    last_updated = models.DateField()
    body = models.TextField(
        help_text="Full HTML. Available merge fields: {legal_name}, {trade_name}, "
        "{street}, {postal_code}, {city}, {wilaya}, {vat_number}."
    )

    class Meta:
        verbose_name = "Legal Document"
        ordering = ["slug"]

    def __str__(self):
        return self.title


# ---------------------------------------------------------------------------
# 404 page (CMS dynamization)
# ---------------------------------------------------------------------------


class NotFoundPageContent(SingletonContentModel):
    """The 404 page's heading/body copy (spec 9.6). The quick-link tiles
    stay structural site navigation, not editorial content, so they're not
    modeled here -- same distinction the spec draws elsewhere between real
    content and fixed nav."""

    heading = models.CharField(max_length=100, default="This Trail Has No End")
    body = models.TextField(
        default="The page you're looking for has gone off-road and we "
        "can't find it. Let's get you back on track."
    )

    class Meta:
        verbose_name = "404 Page Content"
        verbose_name_plural = "404 Page Content"

    def __str__(self):
        return "404 Page Content"
