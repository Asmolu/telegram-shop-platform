from __future__ import annotations

from collections.abc import Iterable

from app.db.models import ProductSizeGrid

CLOTHING_ALPHA_SIZES = ("XS", "S", "M", "L", "XL", "XXL", "3XL", "ONE_SIZE")
SHOES_RU_SIZES = tuple(str(size) for size in range(35, 47))

ALLOWED_SIZES_BY_GRID: dict[ProductSizeGrid, tuple[str, ...]] = {
    ProductSizeGrid.CLOTHING_ALPHA: CLOTHING_ALPHA_SIZES,
    ProductSizeGrid.SHOES_RU: SHOES_RU_SIZES,
}


class SizeGridValidationError(ValueError):
    pass


def normalize_size(grid: ProductSizeGrid | str, value: str) -> str:
    size_grid = ProductSizeGrid(grid)
    normalized = value.strip()
    if size_grid == ProductSizeGrid.CLOTHING_ALPHA:
        normalized = normalized.upper()
    if normalized not in ALLOWED_SIZES_BY_GRID[size_grid]:
        allowed = ", ".join(ALLOWED_SIZES_BY_GRID[size_grid])
        raise SizeGridValidationError(
            f"Size '{value}' is not valid for {size_grid.value}. Allowed sizes: {allowed}"
        )
    return normalized


def incompatible_sizes(
    grid: ProductSizeGrid | str,
    values: Iterable[str],
) -> list[str]:
    invalid: list[str] = []
    for value in values:
        try:
            normalize_size(grid, value)
        except (SizeGridValidationError, ValueError):
            if value not in invalid:
                invalid.append(value)
    return invalid


def size_sort_key(grid: ProductSizeGrid | str, value: str) -> tuple[int, str]:
    size_grid = ProductSizeGrid(grid)
    try:
        return (ALLOWED_SIZES_BY_GRID[size_grid].index(normalize_size(size_grid, value)), value)
    except (SizeGridValidationError, ValueError):
        return (len(ALLOWED_SIZES_BY_GRID[size_grid]), value)


def format_size_for_display(grid: ProductSizeGrid | str, value: str) -> str:
    size_grid = ProductSizeGrid(grid)
    if size_grid == ProductSizeGrid.SHOES_RU:
        return f"RU {value}"
    if value == "ONE_SIZE":
        return "Единый размер"
    return value
