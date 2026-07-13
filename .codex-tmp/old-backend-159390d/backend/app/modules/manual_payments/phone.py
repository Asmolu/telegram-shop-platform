import re


def normalize_russian_phone(value: str) -> tuple[str, str]:
    digits = re.sub(r"\D", "", value.strip())
    if len(digits) != 11 or digits[0] not in {"7", "8"}:
        msg = "Phone must be a Russian number with 11 digits"
        raise ValueError(msg)

    national = digits[1:]
    e164 = f"+7{national}"
    display = (
        f"+7 ({national[:3]}) {national[3:6]}-"
        f"{national[6:8]}-{national[8:]}"
    )
    return e164, display
