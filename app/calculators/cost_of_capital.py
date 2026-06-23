class CostOfCapitalCalculator:

    def capm_cost_of_equity(
        self,
        risk_free_rate: float,
        beta: float,
        market_return: float,
    ) -> float:
        """Cost of Equity via CAPM: Rf + Beta × (Rm - Rf).
        Returns rate rounded to 6 decimal places for downstream DCF precision."""
        return round(risk_free_rate + beta * (market_return - risk_free_rate), 6)

    def post_tax_cost_of_debt(
        self,
        pre_tax_cost_of_debt: float,
        tax_rate: float,
    ) -> float:
        """Post-tax cost of debt: Kd × (1 - tax_rate).
        Returns rate rounded to 6 decimal places for downstream DCF precision."""
        return round(pre_tax_cost_of_debt * (1 - tax_rate), 6)

    def weight_of_debt(
        self,
        book_value_debt: float,
        book_value_equity: float,
    ) -> float:
        """Proportion of total capital financed by debt: Debt / (Debt + Equity)."""
        total = book_value_debt + book_value_equity
        if total == 0:
            raise ValueError(
                "book_value_debt + book_value_equity cannot be zero"
            )
        return round(book_value_debt / total, 6)

    def weight_of_equity(
        self,
        book_value_debt: float,
        book_value_equity: float,
    ) -> float:
        """Proportion of total capital financed by equity: Equity / (Debt + Equity)."""
        total = book_value_debt + book_value_equity
        if total == 0:
            raise ValueError(
                "book_value_debt + book_value_equity cannot be zero"
            )
        return round(book_value_equity / total, 6)

    def wacc(
        self,
        weight_of_debt: float,
        cost_of_debt: float,
        weight_of_equity: float,
        cost_of_equity: float,
    ) -> float:
        """Weighted Average Cost of Capital: (Wd × Kd) + (We × Ke).
        Returns rate rounded to 6 decimal places for downstream DCF precision."""
        return round(
            weight_of_debt * cost_of_debt + weight_of_equity * cost_of_equity,
            6,
        )
