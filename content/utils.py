"""
content.utils

Merge-field rendering for admin-edited copy that needs a live value spliced
in (Home's test-ride dealer count, the legal pages' company identity).
`str.format` would raise and 500 the page on a stray "{" an admin typed
into a TextField that was never meant to be a template -- `safe_format`
degrades to the raw text instead, exactly like a real CMS's merge-tag
renderer would.
"""


def safe_format(text, **kwargs):
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return text


def merge_company_fields(text, company):
    return safe_format(
        text,
        legal_name=company.legal_name,
        trade_name=company.trade_name or company.legal_name,
        street=company.street,
        postal_code=company.postal_code,
        city=company.city,
        wilaya=company.get_wilaya_display(),
        vat_number=company.vat_number,
    )
