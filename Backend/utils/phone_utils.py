"""Normalize phone numbers for Retell (E.164-style with leading +)."""


def to_e164(phone: str, default_country_code: str = "91") -> str:
    raw = (phone or "").strip().replace(" ", "").replace("-", "")
    if not raw:
        raise ValueError("Phone number is required")
    if raw.startswith("+"):
        return raw
    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        raise ValueError("Invalid phone number")
    if len(digits) == 10:
        return f"+{default_country_code}{digits}"
    return f"+{digits}"
