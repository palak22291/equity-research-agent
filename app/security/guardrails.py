"""Input validation guardrails for the equity research pipeline.

All user-supplied inputs are sanitised here before reaching the LLM or any calculator.
"""
import re

VALID_SECTORS = {
    'pharmaceuticals', 'it', 'banking', 'fmcg',
    'automobiles', 'oil_gas', 'telecom', 'metals',
    'cement', 'power', 'healthcare', 'default',
}


def validate_ticker(ticker: str) -> str:
    clean = ticker.upper().strip()
    if not clean or len(clean) > 20 or not re.fullmatch(r'[A-Z0-9.\-]+', clean):
        raise ValueError(
            f"Invalid ticker: '{ticker}'. Must be alphanumeric, max 20 chars."
        )
    return clean


def validate_sector(sector: str) -> str:
    clean = sector.lower().strip()
    if clean not in VALID_SECTORS:
        raise ValueError(
            f"Invalid sector: '{sector}'. Valid sectors: {sorted(VALID_SECTORS)}"
        )
    return clean


def validate_beta(beta) -> float | None:
    if beta is None:
        return None
    try:
        b = float(beta)
    except (TypeError, ValueError):
        raise ValueError(f"Beta must be a number, got: {beta}")
    if not (0.0 < b < 5.0):
        raise ValueError(f"Beta {b} outside reasonable range (0.0 to 5.0)")
    return b


def validate_numeric_output(
    value: float,
    name: str,
    min_val: float = None,
    max_val: float = None,
) -> float:
    if value is None:
        raise ValueError(f"{name} is None — calculation failed")
    if isinstance(value, float) and value != value:
        raise ValueError(f"{name} produced NaN")
    if min_val is not None and value < min_val:
        raise ValueError(f"{name} = {value} below minimum {min_val}")
    if max_val is not None and value > max_val:
        raise ValueError(f"{name} = {value} above maximum {max_val}")
    return value
