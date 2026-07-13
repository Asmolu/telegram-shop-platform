class InventoryValidationError(ValueError):
    pass


def validate_inventory_quantities(stock_quantity: int, reserved_quantity: int) -> None:
    if stock_quantity < 0:
        raise InventoryValidationError("stock_quantity cannot be negative")
    if reserved_quantity < 0:
        raise InventoryValidationError("reserved_quantity cannot be negative")
    if reserved_quantity > stock_quantity:
        raise InventoryValidationError("reserved_quantity cannot exceed stock_quantity")


def calculate_available_quantity(stock_quantity: int, reserved_quantity: int) -> int:
    validate_inventory_quantities(stock_quantity, reserved_quantity)
    return stock_quantity - reserved_quantity
