"""
Recommendation + Audit Agent module.

Rule engine + local Ollama LLM producing final advice, with every output
attaching a provenance record: {chunk_ids, sentiment_score, rule_id, model_used}.

This is core novel piece #2 — the audit/evidence layer is the subject
of Experiment B in the paper.

Components:
    agent.py       — main callable: profile + chunks + sentiment → advice + provenance
    rules.py       — Indian finance rule engine (80C, lock-in, etc.)
    provenance.py  — provenance record schema
"""
