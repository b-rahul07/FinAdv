"""
Preference Agent module.

SAUR-style elicitation of user financial preferences via targeted
questions, producing a structured profile that is explicitly confirmed
(or edited) by the user before proceeding.

This is core novel piece #1 — the confirmation step is the subject
of Experiment A in the paper.

Components:
    agent.py      — main callable: run elicitation → produce confirmed profile
    questions.py  — the 5–8 targeted elicitation questions
    profile.py    — UserProfile dataclass/schema
"""
