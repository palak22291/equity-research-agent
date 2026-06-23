class CashFlowCalculator:

    # --- Helper ---

    def nopat(self, ebit: float, tax_rate: float) -> float:
        """Net Operating Profit After Tax — operating earnings available to all capital providers."""
        return round(ebit * (1 - tax_rate), 2)

    # --- FCFF ---

    def fcff_from_net_income(
        self,
        net_income: float,
        non_cash_expenses: float,
        increase_in_current_assets: float,
        increase_in_current_liabilities: float,
        interest: float,
        tax_rate: float,
        capex: float,
    ) -> float:
        """FCFF via Net Income: NI + NonCash - ΔCA + ΔCL + Interest×(1-TaxRate) - CapEx."""
        after_tax_interest = interest * (1 - tax_rate)
        return round(
            net_income
            + non_cash_expenses
            - increase_in_current_assets
            + increase_in_current_liabilities
            + after_tax_interest
            - capex,
            2,
        )

    def fcff_from_nopat(
        self,
        nopat: float,
        non_cash_expenses: float,
        increase_in_current_assets: float,
        increase_in_current_liabilities: float,
        capex: float,
    ) -> float:
        """FCFF via NOPAT: NOPAT + NonCash - ΔCA + ΔCL - CapEx."""
        return round(
            nopat
            + non_cash_expenses
            - increase_in_current_assets
            + increase_in_current_liabilities
            - capex,
            2,
        )

    def fcff_from_cfo(
        self,
        cfo: float,
        interest: float,
        tax_rate: float,
        capex: float,
    ) -> float:
        """FCFF via CFO: CFO + Interest×(1-TaxRate) - CapEx."""
        after_tax_interest = interest * (1 - tax_rate)
        return round(cfo + after_tax_interest - capex, 2)

    def validated_fcff(
        self,
        net_income: float,
        non_cash_expenses: float,
        increase_in_current_assets: float,
        increase_in_current_liabilities: float,
        interest: float,
        tax_rate: float,
        capex: float,
        cfo: float,
        ebit: float,
        tolerance: float = 0.10,
    ) -> float:
        """Computes FCFF via all 3 methods and raises ValueError if they disagree beyond tolerance.
        Returns the average of the three results when they agree."""
        v1 = self.fcff_from_net_income(
            net_income, non_cash_expenses, increase_in_current_assets,
            increase_in_current_liabilities, interest, tax_rate, capex,
        )
        v2 = self.fcff_from_nopat(
            self.nopat(ebit, tax_rate), non_cash_expenses,
            increase_in_current_assets, increase_in_current_liabilities, capex,
        )
        v3 = self.fcff_from_cfo(cfo, interest, tax_rate, capex)

        spread = max(v1, v2, v3) - min(v1, v2, v3)
        if spread > tolerance:
            raise ValueError(
                f"FCFF cross-validation failed: methods returned {v1}, {v2}, {v3} "
                f"(spread {spread:.4f} exceeds tolerance {tolerance}). "
                "Check input data for inconsistencies."
            )
        return round((v1 + v2 + v3) / 3, 2)

    # --- FCFE ---

    def fcfe_from_net_income(
        self,
        net_income: float,
        non_cash_expenses: float,
        increase_in_current_assets: float,
        increase_in_current_liabilities: float,
        capex: float,
        net_borrowing: float,
    ) -> float:
        """FCFE via Net Income: NI + NonCash - ΔCA + ΔCL - CapEx + NetBorrowing."""
        return round(
            net_income
            + non_cash_expenses
            - increase_in_current_assets
            + increase_in_current_liabilities
            - capex
            + net_borrowing,
            2,
        )

    def fcfe_from_fcff(
        self,
        fcff: float,
        interest: float,
        tax_rate: float,
        net_borrowing: float,
    ) -> float:
        """FCFE via FCFF: FCFF - Interest×(1-TaxRate) + NetBorrowing."""
        after_tax_interest = interest * (1 - tax_rate)
        return round(fcff - after_tax_interest + net_borrowing, 2)

    def fcfe_from_ocf(
        self,
        ocf: float,
        capex: float,
        net_borrowing: float,
    ) -> float:
        """FCFE via OCF: OCF - CapEx + NetBorrowing."""
        return round(ocf - capex + net_borrowing, 2)

    def validated_fcfe(
        self,
        net_income: float,
        non_cash_expenses: float,
        increase_in_current_assets: float,
        increase_in_current_liabilities: float,
        interest: float,
        tax_rate: float,
        capex: float,
        cfo: float,
        ebit: float,
        ocf: float,
        net_borrowing: float,
        tolerance: float = 0.10,
    ) -> float:
        """Computes FCFE via all 3 methods and raises ValueError if they disagree beyond tolerance.
        Returns the average of the three results when they agree."""
        fcff = self.validated_fcff(
            net_income, non_cash_expenses, increase_in_current_assets,
            increase_in_current_liabilities, interest, tax_rate, capex, cfo, ebit,
            tolerance=tolerance,
        )
        v1 = self.fcfe_from_net_income(
            net_income, non_cash_expenses, increase_in_current_assets,
            increase_in_current_liabilities, capex, net_borrowing,
        )
        v2 = self.fcfe_from_fcff(fcff, interest, tax_rate, net_borrowing)
        v3 = self.fcfe_from_ocf(ocf, capex, net_borrowing)

        spread = max(v1, v2, v3) - min(v1, v2, v3)
        if spread > tolerance:
            raise ValueError(
                f"FCFE cross-validation failed: methods returned {v1}, {v2}, {v3} "
                f"(spread {spread:.4f} exceeds tolerance {tolerance}). "
                "Check input data for inconsistencies."
            )
        return round((v1 + v2 + v3) / 3, 2)
