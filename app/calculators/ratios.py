class RatioCalculator:

    # --- Liquidity ---

    def current_ratio(self, current_assets: float, current_liabilities: float) -> float:
        """Measures ability to cover short-term obligations with short-term assets."""
        if current_liabilities == 0:
            raise ValueError("current_liabilities cannot be zero")
        return round(current_assets / current_liabilities, 2)

    def quick_ratio(self, cash_and_equivalents: float, accounts_receivable: float, current_liabilities: float) -> float:
        """Measures ability to meet short-term obligations using only cash and receivables (excludes inventory and other less-liquid assets)."""
        if current_liabilities == 0:
            raise ValueError("current_liabilities cannot be zero")
        return round((cash_and_equivalents + accounts_receivable) / current_liabilities, 2)

    def cash_ratio(self, cash_and_equivalents: float, current_liabilities: float) -> float:
        """Measures ability to cover short-term obligations using only cash and cash equivalents."""
        if current_liabilities == 0:
            raise ValueError("current_liabilities cannot be zero")
        return round(cash_and_equivalents / current_liabilities, 2)

    # --- Solvency ---

    def debt_to_equity(self, current_liabilities: float, total_debt: float, shareholders_equity: float) -> float:
        """Measures total financial obligations (current liabilities + long-term debt) relative to shareholders' equity."""
        if shareholders_equity == 0:
            raise ValueError("shareholders_equity cannot be zero")
        return round((current_liabilities + total_debt) / shareholders_equity, 2)

    def interest_coverage(self, ebit: float, interest_expense: float) -> float:
        """Measures how easily a company can pay interest on outstanding debt from operating earnings."""
        if interest_expense == 0:
            raise ValueError("interest_expense cannot be zero")
        return round(ebit / interest_expense, 2)

    def debt_to_assets(self, total_debt: float, total_assets: float) -> float:
        """Measures the proportion of a company's assets that are financed by debt."""
        if total_assets == 0:
            raise ValueError("total_assets cannot be zero")
        return round(total_debt / total_assets, 2)

    # --- Profitability ---

    def net_profit_margin(self, net_income: float, revenue: float) -> float:
        """Measures the percentage of revenue that translates into net profit after all expenses."""
        if revenue == 0:
            raise ValueError("revenue cannot be zero")
        return round(net_income / revenue, 2)

    def return_on_equity(self, net_income: float, shareholders_equity: float) -> float:
        """Measures how much profit a company generates for each unit of shareholders' equity."""
        if shareholders_equity == 0:
            raise ValueError("shareholders_equity cannot be zero")
        return round(net_income / shareholders_equity, 2)

    def return_on_assets(self, net_income: float, total_assets: float) -> float:
        """Measures how efficiently a company uses its assets to generate profit."""
        if total_assets == 0:
            raise ValueError("total_assets cannot be zero")
        return round(net_income / total_assets, 2)

    def ebitda_margin(self, ebitda: float, revenue: float) -> float:
        """Measures operating profitability as a percentage of revenue before interest, tax, depreciation, and amortisation."""
        if revenue == 0:
            raise ValueError("revenue cannot be zero")
        return round(ebitda / revenue, 2)

    # --- Efficiency ---

    def asset_turnover(self, revenue: float, total_assets: float) -> float:
        """Measures how efficiently a company uses its assets to generate revenue.
        Revenue here = Total Revenue including other income (28,409.49 for Cipla FY2025)"""
        if total_assets == 0:
            raise ValueError("total_assets cannot be zero")
        return round(revenue / total_assets, 2)

    def inventory_turnover(self, cogs: float, inventory: float) -> float:
        """Measures how many times inventory is sold and replaced over a period."""
        if inventory == 0:
            raise ValueError("inventory cannot be zero")
        return round(cogs / inventory, 2)

    def receivables_turnover(self, revenue: float, accounts_receivable: float) -> float:
        """Measures how efficiently a company collects revenue owed by customers.
        Revenue here = Total Revenue including other income (28,409.49 for Cipla FY2025)"""
        if accounts_receivable == 0:
            raise ValueError("accounts_receivable cannot be zero")
        return round(revenue / accounts_receivable, 2)

    # --- DuPont ---

    def dupont_roe(self, net_profit_margin: float, asset_turnover: float, equity_multiplier: float) -> float:
        """Decomposes ROE into profitability, efficiency, and leverage components (margin × turnover × multiplier)."""
        return round(net_profit_margin * asset_turnover * equity_multiplier, 2)
