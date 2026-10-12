"""
Orchestrator module.

Sequential/conditional pipeline that wires the four agents together:
    Preference → Retrieval → Sentiment → Recommendation+Audit

Exposed via FastAPI endpoints. Not an autonomous multi-agent framework —
plain function calls with clear module boundaries for ablation support.

Components:
    pipeline.py — the sequential orchestration logic
    api.py      — FastAPI endpoints
"""
