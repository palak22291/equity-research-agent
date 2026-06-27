"""Tests for app/security/guardrails.py input validation."""
import pytest

from app.security.guardrails import validate_beta, validate_sector, validate_ticker


# ---------------------------------------------------------------------------
# validate_ticker
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ticker", ["CIPLA", "INFY", "RELIANCE"])
def test_valid_ticker(ticker):
    assert validate_ticker(ticker) == ticker


@pytest.mark.parametrize("ticker", [
    "'; DROP TABLE",
    "",
    "A" * 21,
])
def test_invalid_ticker(ticker):
    with pytest.raises(ValueError):
        validate_ticker(ticker)


# ---------------------------------------------------------------------------
# validate_sector
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sector", [
    'pharmaceuticals', 'it', 'banking', 'fmcg',
    'automobiles', 'oil_gas', 'telecom', 'metals',
    'cement', 'power', 'healthcare',
])
def test_valid_sector(sector):
    assert validate_sector(sector) == sector


@pytest.mark.parametrize("sector", ["crypto", "unknown"])
def test_invalid_sector(sector):
    with pytest.raises(ValueError):
        validate_sector(sector)


# ---------------------------------------------------------------------------
# validate_beta
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("beta", [0.1, 1.0, 4.9])
def test_valid_beta(beta):
    assert validate_beta(beta) == pytest.approx(beta)


@pytest.mark.parametrize("beta", [-1, 0, 6, "abc"])
def test_invalid_beta(beta):
    with pytest.raises(ValueError):
        validate_beta(beta)


def test_beta_none_passthrough():
    assert validate_beta(None) is None
