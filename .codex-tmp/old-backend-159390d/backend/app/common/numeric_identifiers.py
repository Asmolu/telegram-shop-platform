from collections.abc import Iterable

from fastapi import status

from app.core.errors import AppError


def allocate_numeric_identifiers(
    existing_values: Iterable[str],
    count: int,
    *,
    min_value: int,
    max_value: int,
    width: int,
    exhausted_message: str,
) -> list[str]:
    used_numbers = {
        value
        for candidate in existing_values
        if (
            value := numeric_identifier_value(
                candidate,
                min_value=min_value,
                max_value=max_value,
                width=width,
            )
        )
        is not None
    }
    generated: list[str] = []

    for value in range(min_value, max_value + 1):
        if value in used_numbers:
            continue
        used_numbers.add(value)
        generated.append(format_numeric_identifier(value, width=width))
        if len(generated) == count:
            return generated

    raise AppError(exhausted_message, status.HTTP_400_BAD_REQUEST)


def numeric_identifier_value(
    candidate: str,
    *,
    min_value: int,
    max_value: int,
    width: int,
) -> int | None:
    if len(candidate) != width or not all("0" <= char <= "9" for char in candidate):
        return None
    value = int(candidate)
    if value < min_value or value > max_value:
        return None
    return value


def format_numeric_identifier(value: int, *, width: int) -> str:
    return f"{value:0{width}d}"
