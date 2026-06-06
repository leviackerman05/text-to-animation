"""Validate signup emails against known personal/educational providers."""

import re

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

ALLOWED_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "yahoo.com",
    "yahoo.co.in",
    "yahoo.co.uk",
    "yahoo.ca",
    "ymail.com",
    "rocketmail.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "proton.me",
    "protonmail.com",
    "pm.me",
    "aol.com",
    "zoho.com",
    "mail.com",
    "gmx.com",
    "gmx.de",
    "gmx.net",
    "fastmail.com",
    "tutanota.com",
    "tuta.io",
    "hey.com",
    "rediffmail.com",
}

ALLOWED_DOMAIN_SUFFIXES = (".edu", ".ac.uk", ".edu.in", ".edu.au")


def validate_signup_email(email: str) -> tuple[bool, str]:
    normalized = email.strip().lower()
    if not normalized:
        return False, "Email is required"

    if not EMAIL_PATTERN.match(normalized):
        return False, "Enter a valid email address"

    domain = normalized.split("@", 1)[1]
    if domain in ALLOWED_EMAIL_DOMAINS:
        return True, ""

    if any(domain.endswith(suffix) for suffix in ALLOWED_DOMAIN_SUFFIXES):
        return True, ""

    allowed_preview = "Gmail, Outlook, Yahoo, iCloud, Proton, and school (.edu) addresses"
    return False, f"Use a supported email provider ({allowed_preview})"
