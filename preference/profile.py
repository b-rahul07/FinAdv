"""
User Financial Profile Model (UserProfile)
============================================
This file defines the UserProfile dataclass, which acts as the core standardized
data contract between the onboarding questionnaire and downstream advisory agents.

Every financial decision (risk limits, asset allocation, instrument choices)
is calculated based on the fields defined in this profile.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserProfile:
    """
    Data model representing a retail investor's financial situation and preferences.
    """

    # --------------------------------------------------------------------------
    # Core User Preferences (Directly gathered from questions)
    # --------------------------------------------------------------------------
    
    # User's comfort with investment fluctuations:
    # "Conservative" (low risk, capital preservation), "Moderate", or "Aggressive" (wealth maximization)
    risk_tolerance: str = ""

    # Expected investment timeframe:
    # "Short-term" (< 3 years), "Medium-term" (3-7 years), or "Long-term" (> 7 years)
    investment_horizon: str = ""

    # Primary financial goal (e.g., "Retirement", "Buying a Home", "Tax Saving", "Wealth Growth")
    goal_type: str = ""

    # Amount of money the user saves and can potentially invest each month (in INR ₹)
    monthly_savings: float = 0.0

    # Total monthly debt obligations (Home Loan EMI, Car Loan EMI, Personal Loans in INR ₹)
    existing_emi: float = 0.0

    # Exposure to "Buy Now Pay Later" or revolving credit debts ("None", "Low", "Moderate", "High")
    bnpl_exposure: str = ""

    # How important tax savings (under 80C / ELSS / NPS) are to the user (scale of 1 to 5)
    tax_saving_priority: int = 0

    # User's self-assessed financial knowledge: "Beginner", "Intermediate", or "Advanced"
    financial_literacy: str = ""

    # --------------------------------------------------------------------------
    # Audit & Confirmation Tracking
    # --------------------------------------------------------------------------
    
    # Flags whether the user has reviewed and approved this profile
    confirmed: bool = False

    # Records any fields that the user explicitly edited during the confirmation step
    confirmation_edits: dict = field(default_factory=dict)

    # --------------------------------------------------------------------------
    # Derived Financial Metrics (Computed automatically by the system)
    # --------------------------------------------------------------------------
    
    # Net disposable surplus available for new investments (monthly_savings minus debt EMIs)
    # Crucial for preventing predatory or unaffordable SIP recommendations
    effective_investable: float = 0.0

    # Normalized lowercase risk category string used by the deterministic rule engine
    risk_category: str = ""

    def compute_derived_fields(self) -> None:
        """
        Calculates safe investable surplus and normalizes risk labels.
        Guarantees that effective_investable is never negative.
        """
        # Safety formula: Surplus = Monthly Savings - Existing Loan EMIs
        self.effective_investable = max(0.0, self.monthly_savings - self.existing_emi)
        
        # Normalize risk string to lowercase for standard rule engine checks
        self.risk_category = self.risk_tolerance.lower() if self.risk_tolerance else "moderate"

    def to_dict(self) -> dict:
        """
        Converts the profile into a standard Python dictionary for JSON serialization,
        database logging, and API responses.
        """
        return {
            "risk_tolerance": self.risk_tolerance,
            "investment_horizon": self.investment_horizon,
            "goal_type": self.goal_type,
            "monthly_savings": self.monthly_savings,
            "existing_emi": self.existing_emi,
            "bnpl_exposure": self.bnpl_exposure,
            "tax_saving_priority": self.tax_saving_priority,
            "financial_literacy": self.financial_literacy,
            "confirmed": self.confirmed,
            "confirmation_edits": self.confirmation_edits,
            "effective_investable": self.effective_investable,
            "risk_category": self.risk_category,
        }

