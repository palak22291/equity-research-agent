from abc import ABC, abstractmethod


class FinancialDataProvider(ABC):

    @abstractmethod
    def get_financial_statements(self, ticker: str) -> dict:
        """Return income statement, balance sheet, and cash flow data."""

    @abstractmethod
    def get_market_data(self, ticker: str) -> dict:
        """Return current market price, shares outstanding, beta, and market cap."""

    @abstractmethod
    def get_sector_growth_rate(self, sector: str) -> float:
        """Return the expected long-run nominal growth rate for the given sector."""
