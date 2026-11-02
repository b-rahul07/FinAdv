"""LLM clients. The website may only use self-hosted models (brief §2.6)."""

from finadvisor.llm.base import LLM, Generation, ModelIdentity, PrivacyError, get_llm, require_self_hosted

__all__ = ["LLM", "Generation", "ModelIdentity", "PrivacyError", "get_llm", "require_self_hosted"]
