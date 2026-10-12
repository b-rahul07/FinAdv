"""
Preference Elicitation Questions
==================================
This module defines the list of structured profiling questions presented to the
user at the beginning of their advisory session.

Why these questions matter:
  1. Financial Goal & Query -> Ensures advice is tailored to what the user actually wants.
  2. Risk Tolerance & Time Horizon -> Core pillars of modern portfolio theory (SEBI guidelines).
  3. Monthly Savings & Existing Debts (EMI/BNPL) -> Protects the user from overcommitting
     capital they do not safely have (Budget Guard rule).
  4. Tax Saving Priority -> Influences whether instruments like ELSS, PPF, or NPS are suggested.
  5. Financial Literacy -> Calibrates the technical depth and explanation style of the response.
"""

# The ELICITATION_QUESTIONS list contains the schema for every onboarding prompt.
# Each item has:
#   - id: Unique field name matching UserProfile properties
#   - text: User-friendly question prompt rendered in the chat UI
#   - type: Input format ("text", "choice", "number", or "scale")
#   - options: Predefined selectable options (or None for freeform entry)
#   - required: Flag indicating whether user input is mandatory
ELICITATION_QUESTIONS: list[dict] = [
    {
        # Question 1: The user's specific problem or request
        "id": "financial_question",
        "text": "What specific financial question or topic would you like advice on today?",
        "type": "text",
        "options": None,
        "required": True,
    },
    {
        # Question 2: Psychological tolerance for market volatility
        "id": "risk_tolerance",
        "text": "How would you describe your risk tolerance?",
        "type": "choice",
        "options": ["Conservative", "Moderate", "Aggressive"],
        "required": True,
    },
    {
        # Question 3: Duration for which funds can remain invested
        "id": "investment_horizon",
        "text": "What is your investment time horizon?",
        "type": "choice",
        "options": ["Short-term (< 1 year)", "Medium-term (1–5 years)", "Long-term (> 5 years)"],
        "required": True,
    },
    {
        # Question 4: Primary purpose of the investment
        "id": "goal_type",
        "text": "What is the primary goal for this investment?",
        "type": "choice",
        "options": ["Emergency fund", "Tax saving", "Wealth growth", "Retirement", "Child education", "Home purchase"],
        "required": True,
    },
    {
        # Question 5: Total monthly disposable income available before loans
        "id": "monthly_savings",
        "text": "What is your approximate monthly savings capacity (in ₹)?",
        "type": "number",
        "options": None,
        "required": True,
    },
    {
        # Question 6: Fixed loan repayment obligations
        "id": "existing_emi",
        "text": "What is your total existing EMI burden per month (in ₹)?",
        "type": "number",
        "options": None,
        "required": True,
    },
    {
        # Question 7: Short-term revolving credit debt exposure
        "id": "bnpl_exposure",
        "text": "Do you have any active Buy Now Pay Later (BNPL) commitments?",
        "type": "choice",
        "options": ["None", "Minor (< ₹10,000)", "Significant (₹10,000–50,000)", "Heavy (> ₹50,000)"],
        "required": True,
    },
    {
        # Question 8: Urgency of tax reduction under Sec 80C/80CCD
        "id": "tax_saving_priority",
        "text": "How important is tax saving (Section 80C, 80D, etc.) in your investment decision?",
        "type": "scale",
        "options": [1, 2, 3, 4, 5],  # 1 = not important, 5 = top priority
        "required": True,
    },
    {
        # Question 9: Familiarity with capital markets
        "id": "financial_literacy",
        "text": "How would you rate your financial knowledge?",
        "type": "choice",
        "options": ["Beginner", "Intermediate", "Advanced"],
        "required": True,
    },
]

