ORDER_NUMBER_PREFIX = "ORD"
ORDER_NUMBER_WIDTH = 6
ORDER_NUMBER_MAX = 999_999


def format_order_number(sequence_value: int) -> str:
    if sequence_value < 1 or sequence_value > ORDER_NUMBER_MAX:
        raise ValueError("Order number sequence exhausted")
    return f"{ORDER_NUMBER_PREFIX}-{sequence_value:0{ORDER_NUMBER_WIDTH}d}"
