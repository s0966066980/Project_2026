import json


def parse_json_list(value, fallback_csv: bool = False) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError, ValueError):
        if not fallback_csv:
            return []
        return [item.strip() for item in str(value).split(",") if item.strip()]


def parse_non_negative_int(value, default: int = 0) -> int:
    try:
        return max(0, int(value or default))
    except (TypeError, ValueError):
        return default


def parse_int_from_decimal(value, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default
