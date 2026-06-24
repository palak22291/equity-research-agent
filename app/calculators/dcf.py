class DCFCalculator:

    def forecast_cashflows(
        self,
        base_cashflow: float,
        growth_rate: float,
        years: int,
    ) -> list:
        """Returns list of forecasted cashflows for periods 1..years.
        Values are NOT rounded — preserves precision for downstream terminal value and PV arithmetic."""
        return [base_cashflow * (1 + growth_rate) ** t for t in range(1, years + 1)]

    def present_value(
        self,
        cashflow: float,
        discount_rate: float,
        period: int,
    ) -> float:
        """PV of a single cashflow: CF / (1 + r)^t."""
        return round(cashflow / (1 + discount_rate) ** period, 2)

    def terminal_value(
        self,
        last_forecasted_cf: float,
        growth_rate: float,
        discount_rate: float,
    ) -> float:
        """Gordon Growth terminal value: last_cf × (1 + g) / (r - g).
        Raises ValueError if discount_rate <= growth_rate (perpetuity formula undefined)."""
        if discount_rate <= growth_rate:
            raise ValueError(
                f"discount_rate ({discount_rate}) must exceed growth_rate ({growth_rate}) "
                "for the Gordon Growth model to be defined."
            )
        return round(
            last_forecasted_cf * (1 + growth_rate) / (discount_rate - growth_rate), 2
        )

    def pv_of_terminal_value(
        self,
        terminal_value: float,
        discount_rate: float,
        periods: int,
    ) -> float:
        """PV of terminal value discounted back over the forecast horizon: TV / (1 + r)^n."""
        return round(terminal_value / (1 + discount_rate) ** periods, 2)

    def intrinsic_equity_value(
        self,
        forecasted_fcfe: list,
        ke: float,
        terminal_growth_rate: float,
    ) -> float:
        """Sum of PV of all forecasted FCFE cashflows plus PV of Gordon Growth terminal value.
        Uses full precision internally — no intermediate rounding — to avoid accumulated error."""
        if ke <= terminal_growth_rate:
            raise ValueError(
                f"ke ({ke}) must exceed terminal_growth_rate ({terminal_growth_rate})."
            )
        n = len(forecasted_fcfe)
        pv_cashflows = sum(
            cf / (1 + ke) ** t for t, cf in enumerate(forecasted_fcfe, 1)
        )
        tv = forecasted_fcfe[-1] * (1 + terminal_growth_rate) / (ke - terminal_growth_rate)
        pv_tv = tv / (1 + ke) ** n
        return round(pv_cashflows + pv_tv, 2)

    def intrinsic_share_price(
        self,
        equity_value: float,
        shares_outstanding: float,
    ) -> float:
        """Intrinsic share price: equity_value / shares_outstanding.
        Caller must ensure both arguments use consistent units."""
        if shares_outstanding == 0:
            raise ValueError("shares_outstanding cannot be zero.")
        return round(equity_value / shares_outstanding, 2)

    def intrinsic_enterprise_value(
        self,
        forecasted_fcff: list,
        wacc: float,
        terminal_growth_rate: float,
    ) -> float:
        """Sum of PV of all forecasted FCFF cashflows plus PV of Gordon Growth terminal value,
        discounted at WACC. Uses full precision internally."""
        if wacc <= terminal_growth_rate:
            raise ValueError(
                f"wacc ({wacc}) must exceed terminal_growth_rate ({terminal_growth_rate})."
            )
        n = len(forecasted_fcff)
        pv_cashflows = sum(
            cf / (1 + wacc) ** t for t, cf in enumerate(forecasted_fcff, 1)
        )
        tv = forecasted_fcff[-1] * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
        pv_tv = tv / (1 + wacc) ** n
        return round(pv_cashflows + pv_tv, 2)

    def valuation_verdict(
        self,
        intrinsic_price: float,
        market_price: float,
        margin: float = 0.10,
    ) -> str:
        """Returns Undervalued / Overvalued / Fairly Valued based on margin-of-safety band."""
        if intrinsic_price > market_price * (1 + margin):
            return "Undervalued"
        if intrinsic_price < market_price * (1 - margin):
            return "Overvalued"
        return "Fairly Valued"

    def sensitivity_analysis(
        self,
        base_fcfe: float,
        ke_values: list,
        tg_values: list,
        shares_outstanding: float,
        growth_rate: float,
        years: int,
    ) -> dict:
        """Returns 2D dict {ke: {tg: intrinsic_share_price}} for every (ke, tg) combination.
        Cells where ke <= tg are set to None (Gordon Growth undefined)."""
        forecasted = self.forecast_cashflows(base_fcfe, growth_rate, years)
        result = {}
        for ke in ke_values:
            result[ke] = {}
            for tg in tg_values:
                if ke <= tg:
                    result[ke][tg] = None
                    continue
                eq_val = self.intrinsic_equity_value(forecasted, ke, tg)
                result[ke][tg] = self.intrinsic_share_price(eq_val, shares_outstanding)
        return result
