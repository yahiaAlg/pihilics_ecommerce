"""
accounts.utils
"""

import re
import secrets
import string

from django.core.exceptions import ValidationError

from .models import GarageEntry

# BR-ACC-03: "a password meeting minimum strength criteria (length,
# uppercase, digit, special character)". The spec names the criteria but
# not an exact minimum length; 8 is used here as ARKO's configured minimum.
MIN_PASSWORD_LENGTH = 8
_SPECIAL_CHAR_RE = re.compile(r"""[!@#$%^&*(),.?":{}|<>_\-+=\[\]/\\~`]""")


def validate_password_strength(password):
    """
    BR-ACC-03. Raises ValidationError with one message per unmet criterion
    if `password` doesn't satisfy ARKO's minimum strength. Written as a
    plain function (rather than an AUTH_PASSWORD_VALIDATORS class) so the
    Registration form can call it directly and show all failing criteria
    at once, in the coming Forms phase.
    """
    errors = []
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if not any(char.isupper() for char in password):
        errors.append("Password must contain at least one uppercase letter.")
    if not any(char.isdigit() for char in password):
        errors.append("Password must contain at least one digit.")
    if not _SPECIAL_CHAR_RE.search(password):
        errors.append("Password must contain at least one special character.")
    if errors:
        raise ValidationError(errors)


# Excludes I, O, Q (easily confused with 1 / 0) — mirrors real-world VIN character sets.
_VIN_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "IOQ")


def generate_unique_vin():
    """
    Spec 6.17.2: a Garage card shows "a generated VIN". ARKO has no real
    manufacturing VIN registry to call, so this synthesizes a unique,
    plausibly-shaped 17-character VIN. Used by orders.signals when a
    motorcycle purchase auto-creates a GarageEntry (BR-ORD-05).
    """
    while True:
        candidate = "ARK" + "".join(secrets.choice(_VIN_ALPHABET) for _ in range(14))
        if not GarageEntry.objects.filter(vin=candidate).exists():
            return candidate
