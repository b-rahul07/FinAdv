"""
FastAPI Web Server & REST API Endpoints
=========================================
This file exposes the HTTP API that allows the frontend (React / Vite website)
to communicate seamlessly with the backend Python advisory pipeline and agents.

Core Responsibilities:
  1. Managing Chat Sessions (creating, listing, deleting conversations)
  2. Guiding Preference Elicitation (serving questions one by one and collecting answers)
  3. Handling Profile Confirmation (allowing users to edit risk tolerance, horizon, etc.)
  4. Executing the Multi-Agent Advisory Pipeline (retrieval + FinBERT + recommendation + audit)
  5. Returning Structured Evidence & Provenance for the UI evidence panel
"""

import json
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional
import config
from orchestrator.pipeline import run_pipeline, run_pipeline_for_eval
from persistence.history import (
    create_session,
    write_message,
    update_session_stage,
    update_session_label,
    get_history,
    list_sessions,
    delete_session,
)
from preference.questions import ELICITATION_QUESTIONS
from preference.agent import elicit_preferences, confirm_profile

# Configure logger
logger = logging.getLogger(__name__)

# Initialize FastAPI application instance
app = FastAPI(
    title="AI Financial Advisor",
    description="Multi-agent financial advisory system for Indian personal finance",
    version="0.2.0",
)

# ------------------------------------------------------------------------------
# Cross-Origin Resource Sharing (CORS) Middleware
# Allows the frontend (running on e.g. http://localhost:8080) to make HTTP requests
# to this backend server (running on http://127.0.0.1:8000).
# ------------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Allow any origin during local development
    allow_credentials=True,
    allow_methods=["*"],       # Allow GET, POST, DELETE, OPTIONS, etc.
    allow_headers=["*"],       # Allow all request headers
)


# ==============================================================================
# In-Memory Session Cache
# ==============================================================================
# Holds temporary in-progress elicitation answers while the user is actively
# going through the questionnaire. Permanent message logs are stored in the database.
_session_state: dict[str, dict] = {}


def _get_state(session_id: str) -> dict:
    """
    Retrieves or initializes the in-memory state dictionary for a given session.
    Tracks answers submitted so far, current question index, and calculated profiles.
    """
    if session_id not in _session_state:
        _session_state[session_id] = {
            "answers": {},            # Dict mapping question_id -> user answer string
            "question_index": 0,      # Index of the question currently being answered
            "profile": None,          # UserProfile inferred from answers
            "confirmed_profile": None,# UserProfile after user confirms/edits it
        }
    return _session_state[session_id]


# ==============================================================================
# Request and Response Data Models (Pydantic)
# ==============================================================================

class MessageRequest(BaseModel):
    """Payload sent by the frontend when user answers a questionnaire question."""
    answer: str = ""


class ConfirmRequest(BaseModel):
    """Payload sent by frontend when user reviews and edits their risk profile."""
    profile: dict[str, Any]


class AdviseRequest(BaseModel):
    """Legacy request body for the direct /advise single-call endpoint."""
    user_query: str
    user_responses: dict[str, str]
    profile_edits: Optional[dict[str, str]] = None
    model: Optional[str] = None


class AdviseResponse(BaseModel):
    """Legacy response body containing advice, instruments, and provenance."""
    advice_text: str
    recommended_instruments: list[str]
    confidence: float
    provenance: dict
    profile: dict
    sentiment_summary: dict
    num_chunks_used: int
    pipeline_metadata: dict


class ConfigResponse(BaseModel):
    """Payload returning the active system configuration and model settings."""
    enable_preference_confirmation: bool
    enable_audit_evidence: bool
    ollama_model: str
    top_k_chunks: int
    max_headlines: int


class AblationConfig(BaseModel):
    """Payload for reading/writing experimental ablation toggles dynamically."""
    enable_preference_confirmation: bool
    enable_audit_evidence: bool


# ==============================================================================
# Session & Chat API Endpoints
# ==============================================================================

@app.post("/api/session")
def api_create_session():
    """
    Creates a new conversation session.
    Generates a unique UUID and inserts a new session record into the database.
    """
    try:
        session_id = create_session()
        return {"session_id": session_id}
    except Exception as e:
        logger.error("Failed to create session: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/session/{session_id}/message")
def api_send_message(session_id: str, req: MessageRequest):
    """
    Interactive questionnaire handler:
      1. If the request answer is blank (initial greeting/start), returns Question 1.
      2. If an answer is provided, stores it in state and persistence.
      3. If more questions remain, returns the next question.
      4. If all questions are answered, runs the Preference Agent to build the
         UserProfile and returns the profile summary for user confirmation.
    """
    try:
        state = _get_state(session_id)
        questions = ELICITATION_QUESTIONS
        idx = state["question_index"]

        # Case 1: First call (empty answer) -> Send the very first onboarding question
        if not req.answer.strip():
            q = questions[0]
            options = [str(o) for o in q["options"]] if q.get("options") else None
            # Log question to database
            write_message(session_id, "assistant", "question", {
                "question": q["text"],
                "options": options,
                "index": 1,
                "total": len(questions),
            })
            return {
                "type": "question",
                "question": q["text"],
                "options": options,
                "index": 1,
                "total": len(questions),
            }

        # Case 2: Save the user's answer to the current question
        q_id = questions[idx]["id"]
        state["answers"][q_id] = req.answer
        state["question_index"] = idx + 1

        # Write user's answer into the database
        write_message(session_id, "user", "answer", {
            "text": req.answer,
            "question_key": q_id,
            "question_index": idx + 1,
        })

        # Case 3: Check if user has completed all onboarding questions
        if state["question_index"] >= len(questions):
            # Run Preference Agent to analyze answers and synthesize a structured UserProfile
            profile = elicit_preferences(state["answers"])
            state["profile"] = profile
            profile_dict = profile.to_dict()

            # Advance session stage to 'confirm'
            update_session_stage(session_id, "confirm")

            # Write profile summary message into database
            write_message(session_id, "assistant", "confirmation", {
                "profile": profile_dict,
            })

            # Update the chat session display title in the sidebar
            label = (
                state["answers"].get("financial_question")
                or (list(state["answers"].values())[0] if state["answers"] else "Session")
            )
            update_session_label(session_id, label[:60])

            return {
                "type": "profile_summary",
                "profile": profile_dict,
            }

        # Case 4: More questions remain -> Return the next question
        next_q = questions[state["question_index"]]
        next_idx = state["question_index"] + 1
        next_options = [str(o) for o in next_q["options"]] if next_q.get("options") else None

        # Write next question into database
        write_message(session_id, "assistant", "question", {
            "question": next_q["text"],
            "options": next_options,
            "index": next_idx,
            "total": len(questions),
        })

        return {
            "type": "question",
            "question": next_q["text"],
            "options": next_options,
            "index": next_idx,
            "total": len(questions),
        }
    except Exception as e:
        logger.error("Error in /message for session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/session/{session_id}/confirm")
def api_confirm_profile(session_id: str, req: ConfirmRequest):
    """
    Confirms or applies manual edits to the user's financial profile.
    Allows the user to adjust risk tolerance, target investment horizon, or monthly savings.
    """
    try:
        state = _get_state(session_id)
        profile = state.get("profile")

        if profile is None:
            raise HTTPException(
                status_code=400,
                detail="No profile to confirm — please complete the questionnaire first.",
            )

        # Merge user's edits into the profile object and mark as confirmed
        confirmed = confirm_profile(profile, edits=req.profile)
        state["confirmed_profile"] = confirmed

        # Advance session stage to 'recommendation'
        update_session_stage(session_id, "recommendation")

        # Record confirmation event in persistence log
        write_message(session_id, "user", "profile_edit", {
            "edits": req.profile,
            "confirmed_profile": confirmed.to_dict(),
        })

        return {"confirmed_profile": confirmed.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in /confirm for session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/session/{session_id}/recommend")
def api_recommend(session_id: str):
    """
    Triggers the core multi-agent advisory pipeline:
      1. Uses the user's confirmed risk profile and financial question.
      2. Retrieves authoritative document chunks via vector & keyword search.
      3. Scrapes current headlines and scores sentiment with FinBERT.
      4. Synthesizes personalized advice with local Ollama LLM.
      5. Performs deterministic suitability rule checks (budget guard, risk mismatch).
      6. Formats evidence and audit provenance for display in the UI Evidence Panel.
    """
    try:
        state = _get_state(session_id)
        profile = state.get("confirmed_profile") or state.get("profile")

        if profile is None:
            raise HTTPException(
                status_code=400,
                detail="No profile available — complete elicitation first.",
            )

        # Get the specific financial query asked by the user, or construct a sensible default
        answers = state.get("answers", {})
        user_query = answers.get("financial_question")
        if not user_query:
            user_query = f"What investments are suitable for my {profile.goal_type} goal?"

        # Run pipeline using the confirmed UserProfile directly
        result = run_pipeline_for_eval(
            user_query=user_query,
            profile=profile,
        )

        # Structure document citations for UI display
        evidence = [
            {
                "chunk_id": c.chunk_id,
                "source_document": c.document_name,
                "excerpt": c.content[:300],
            }
            for c in result.chunks
        ]

        # Structure market sentiment analysis for UI display
        sentiment_summary = {
            "score": result.sentiment.overall_score,
            "label": result.sentiment.overall_sentiment,
            "headlines_used": [
                r.headline
                for r in (result.sentiment.individual_results or [])[:5]
            ],
        }

        # Structure rule audit findings
        rule_fired = None
        if result.recommendation.provenance.rule_ids:
            rule_fired = {
                "rule_id": result.recommendation.provenance.rule_ids[0],
                "description": f"Rule {result.recommendation.provenance.rule_ids[0]} was applied.",
            }

        # Structure provenance audit trail (model, timestamps, flags)
        provenance = {
            "model": result.pipeline_metadata.get("model", config.OLLAMA_MODEL),
            "retrieval_k": len(result.chunks),
            "generated_at": result.recommendation.provenance.timestamp,
            "audit_constrained": config.ENABLE_AUDIT_EVIDENCE,
            "preference_confirmation": config.ENABLE_PREFERENCE_CONFIRMATION,
        }

        # Build clean recommendation text
        rec = result.recommendation
        recommendation_text = rec.executive_summary
        if rec.technical_breakdown:
            recommendation_text += "\n\n" + rec.technical_breakdown

        response_data = {
            "recommendation_text": recommendation_text,
            "executive_summary": rec.executive_summary,
            "technical_breakdown": rec.technical_breakdown,
            "asset_allocation": rec.asset_allocation,
            "recommended_instruments": rec.recommended_instruments,
            "evidence": evidence,
            "sentiment_summary": sentiment_summary,
            "rule_fired": rule_fired,
            "provenance": provenance,
        }

        # Save recommendation output to database history
        write_message(session_id, "assistant", "recommendation", response_data)

        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in /recommend for session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/{session_id}/history")
def api_get_history(session_id: str):
    """
    Returns the complete chronological message history for a given chat session.
    """
    try:
        messages = get_history(session_id)
        return {"messages": messages}
    except Exception as e:
        logger.error("Error fetching history for session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions")
def api_list_sessions():
    """
    Returns a list of all existing chat sessions for the sidebar, sorted by recency.
    """
    try:
        sessions = list_sessions()
        return {"sessions": sessions}
    except Exception as e:
        logger.error("Error listing sessions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/session/{session_id}")
def api_delete_session(session_id: str):
    """
    Deletes a session and all its associated messages from the database.
    """
    try:
        delete_session(session_id)
        return {"deleted": session_id}
    except Exception as e:
        logger.error("Error deleting session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# Configuration & Ablation Endpoints
# ==============================================================================

@app.get("/api/config/ablation")
def api_get_ablation():
    """Returns the current state of experimental ablation switches."""
    return AblationConfig(
        enable_preference_confirmation=config.ENABLE_PREFERENCE_CONFIRMATION,
        enable_audit_evidence=config.ENABLE_AUDIT_EVIDENCE,
    )


@app.post("/api/config/ablation")
def api_set_ablation(cfg: AblationConfig):
    """Allows modifying ablation flags at runtime without restarting the server."""
    config.ENABLE_PREFERENCE_CONFIRMATION = cfg.enable_preference_confirmation
    config.ENABLE_AUDIT_EVIDENCE = cfg.enable_audit_evidence
    return cfg


# ==============================================================================
# General & Legacy Utility Endpoints
# ==============================================================================

@app.get("/health")
def health_check():
    """Basic health check to verify backend is up and running."""
    return {"status": "ok", "version": "0.2.0"}


@app.post("/advise", response_model=AdviseResponse)
def get_advice(request: AdviseRequest):
    """
    Single-call advisory endpoint for programmatic or script-based invocation.
    Accepts full questionnaire answers and runs the complete pipeline in one go.
    """
    try:
        result = run_pipeline(
            user_query=request.user_query,
            user_responses=request.user_responses,
            profile_edits=request.profile_edits,
            model=request.model,
        )

        rec = result.recommendation
        advice_text = rec.executive_summary
        if rec.technical_breakdown:
            advice_text += "\n\n" + rec.technical_breakdown

        return AdviseResponse(
            advice_text=advice_text,
            recommended_instruments=rec.recommended_instruments,
            confidence=rec.confidence,
            provenance=rec.provenance.to_dict(),
            profile=result.profile.to_dict(),
            sentiment_summary={
                "topic": result.sentiment.topic,
                "overall_sentiment": result.sentiment.overall_sentiment,
                "overall_score": result.sentiment.overall_score,
                "num_headlines": result.sentiment.num_headlines,
            },
            num_chunks_used=len(result.chunks),
            pipeline_metadata=result.pipeline_metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config", response_model=ConfigResponse)
def get_config():
    """Returns current system configuration and model parameters."""
    return ConfigResponse(
        enable_preference_confirmation=config.ENABLE_PREFERENCE_CONFIRMATION,
        enable_audit_evidence=config.ENABLE_AUDIT_EVIDENCE,
        ollama_model=config.OLLAMA_MODEL,
        top_k_chunks=config.TOP_K_CHUNKS,
        max_headlines=config.MAX_HEADLINES,
    )


@app.get("/questions")
def get_elicitation_questions():
    """Returns the list of onboarding preference questionnaire questions."""
    return {"questions": ELICITATION_QUESTIONS}

