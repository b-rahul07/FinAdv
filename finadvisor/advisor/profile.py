"""The financial profile: the facts and willingness inputs every engine reads.

Only a profile the user has confirmed reaches the capacity engine. Values extracted by the LLM
stay in a draft until the user confirms them on the profile card.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_serializer

DebtKind = Literal["home", "car", "personal", "education", "bnpl", "credit_card", "gold", "two_wheeler", "other"]
Experience = Literal["none", "beginner", "intermediate", "advanced"]

SECURED_KINDS = {"home", "car", "gold", "two_wheeler"}


class Debt(BaseModel):
    kind: DebtKind
    label: str = ""
    outstanding: float = Field(0, ge=0)
    rate_pa: Optional[float] = Field(None, ge=0, le=100)
    emi_monthly: float = Field(0, ge=0)

    @property
    def secured(self) -> bool:
        return self.kind in SECURED_KINDS


class Goal(BaseModel):
    id: str
    name: str
    kind: Literal["retirement", "home", "education", "marriage", "vehicle", "travel", "wealth", "other"] = "other"
    target_today: float = Field(..., gt=0)   # cost in today's rupees
    horizon_years: float = Field(..., gt=0)
    saved_so_far: float = Field(0, ge=0)


class TaxFacts(BaseModel):
    """Optional facts for income-tax estimates, asked one at a time when a tax question needs them. No engine reads
    them: they change no capacity score and no plan."""
    gross_salary_annual: Optional[float] = Field(None, ge=0)
    deductions_80c: Optional[float] = Field(None, ge=0)
    deductions_80d: Optional[float] = Field(None, ge=0)
    nps_80ccd1b: Optional[float] = Field(None, ge=0)
    hra_exemption_annual: Optional[float] = Field(None, ge=0)


class Profile(BaseModel):
    """Facts (x_f) and willingness inputs (x_w), report §3.1."""

    # facts
    age: Optional[int] = Field(None, ge=16, le=100)
    take_home_monthly: float = Field(0, ge=0)
    expenses_monthly: float = Field(0, ge=0)
    liquid_savings: float = Field(0, ge=0)            # emergency money: savings account, FD, liquid fund
    debts: list[Debt] = Field(default_factory=list)
    card_dues_paid_in_full: bool = True
    dependants: int = Field(0, ge=0)
    life_cover: float = Field(0, ge=0)
    health_cover: float = Field(0, ge=0)               # personal/family floater, excluding employer-only cover
    goals: list[Goal] = Field(default_factory=list)
    salaried: bool = True
    # willingness
    experience: Experience = "none"
    gl_answers: dict[int, str] = Field(default_factory=dict)   # item number -> option key
    wishes: list[str] = Field(default_factory=list)
    # tax facts (website conversation layer only)
    tax: Optional[TaxFacts] = None

    @model_serializer(mode="wrap")
    def _dump(self, handler):
        """A profile without tax facts dumps exactly as it did before the field existed, so stored records, prompts
        and experiment files built from dumps are unchanged."""
        d = handler(self)
        if d.get("tax") is None:
            d.pop("tax", None)
        return d

    @property
    def total_emi(self) -> float:
        return sum(d.emi_monthly for d in self.debts)

    @property
    def monthly_surplus(self) -> float:
        """Money left each month after expenses and EMIs (never negative)."""
        return max(0.0, self.take_home_monthly - self.expenses_monthly - self.total_emi)

    def fact_dict(self) -> dict:
        """Facts only, used when comparing whether a turn changed facts."""
        return self.model_dump(exclude={"gl_answers", "wishes", "experience"})


REQUIRED_FIELDS = ("take_home_monthly", "expenses_monthly")


def missing_fields(p: Profile) -> list[str]:
    missing = [f for f in REQUIRED_FIELDS if not getattr(p, f)]
    if len(p.gl_answers) < 13:
        missing.append("gl_answers")
    return missing
