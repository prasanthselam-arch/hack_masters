"""Email and mobile-number validation. Mobile numbers are stored in E.164 form (+919876543210)."""

import re

# Dial code -> (ISO country, allowed national-number lengths, mobile pattern). Kept in step with frontend/src/lib/phone.ts.
COUNTRIES: dict[str, tuple[str, tuple[int, ...], str]] = {
    "91": ("IN", (10,), r"[6-9]\d{9}"),
    "1": ("US", (10,), r"[2-9]\d{9}"),
    "44": ("GB", (10,), r"7\d{9}"),
    "971": ("AE", (9,), r"5\d{8}"),
    "966": ("SA", (9,), r"5\d{8}"),
    "974": ("QA", (8,), r"[3-7]\d{7}"),
    "965": ("KW", (8,), r"[569]\d{7}"),
    "968": ("OM", (8,), r"[79]\d{7}"),
    "973": ("BH", (8,), r"[36]\d{7}"),
    "65": ("SG", (8,), r"[89]\d{7}"),
    "60": ("MY", (9, 10), r"1\d{8,9}"),
    "61": ("AU", (9,), r"4\d{8}"),
    "64": ("NZ", (8, 9, 10), r"2\d{7,9}"),
    "977": ("NP", (10,), r"9[78]\d{8}"),
    "94": ("LK", (9,), r"7\d{8}"),
    "880": ("BD", (10,), r"1[3-9]\d{8}"),
    "49": ("DE", (10, 11), r"1[5-7]\d{8,9}"),
    "33": ("FR", (9,), r"[67]\d{8}"),
    "353": ("IE", (9,), r"8\d{8}"),
    "27": ("ZA", (9,), r"[6-8]\d{8}"),
}
NAMES = {"IN": "India", "US": "the US and Canada", "GB": "the UK", "AE": "the UAE", "SA": "Saudi Arabia", "QA": "Qatar",
         "KW": "Kuwait", "OM": "Oman", "BH": "Bahrain", "SG": "Singapore", "MY": "Malaysia", "AU": "Australia",
         "NZ": "New Zealand", "NP": "Nepal", "LK": "Sri Lanka", "BD": "Bangladesh", "DE": "Germany", "FR": "France",
         "IE": "Ireland", "ZA": "South Africa"}
DEFAULT_DIAL = "91"
_EMAIL = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


class ContactError(ValueError):
    pass


def normalize_email(raw: str) -> str:
    s = raw.strip()
    if len(s) > 254 or not _EMAIL.match(s) or ".." in s:
        raise ContactError("Enter a valid email address, like name@example.com")
    return s.lower()


def normalize_phone(raw: str, default_dial: str = DEFAULT_DIAL) -> str:
    """'+91 98765 43210', '09876543210', '9876543210' -> '+919876543210'. Numbers without a country code use India."""
    s = re.sub(r"[\s\-().]", "", raw.strip())
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("+"):
        digits = s[1:]
        if not digits.isdigit():
            raise ContactError("A mobile number can only contain digits")
        dial = next((digits[:n] for n in (3, 2, 1) if digits[:n] in COUNTRIES), None)
        if dial is None:
            if not 8 <= len(digits) <= 15:
                raise ContactError("Enter a valid mobile number with its country code")
            return "+" + digits
        national = digits[len(dial):]
    else:
        if not s.isdigit():
            raise ContactError("A mobile number can only contain digits")
        dial = default_dial
        national = s
        if dial == "91" and len(national) == 12 and national.startswith("91"):
            national = national[2:]
    national = national.lstrip("0") if len(national) > max(COUNTRIES[dial][1]) else national
    iso, lengths, pattern = COUNTRIES[dial]
    if len(national) not in lengths:
        want = " or ".join(str(n) for n in lengths)
        raise ContactError(f"Mobile numbers in {NAMES[iso]} have {want} digits after +{dial} (you entered {len(national)})")
    if not re.fullmatch(pattern, national):
        raise ContactError(f"This doesn't look like a valid mobile number for {NAMES[iso]}")
    return f"+{dial}{national}"


def normalize_login(raw: str) -> str:
    """An account login is an email address or a mobile number."""
    s = raw.strip()
    if not s:
        raise ContactError("Enter your email address or mobile number")
    if "@" in s or re.search(r"[A-Za-z]", s):
        return normalize_email(s)
    return normalize_phone(s)
