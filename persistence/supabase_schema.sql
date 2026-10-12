-- Supabase schema for session & message persistence
-- Run this in the Supabase SQL Editor or via supabase CLI.

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    label TEXT NOT NULL DEFAULT 'New session',
    stage TEXT NOT NULL DEFAULT 'elicitation'  -- elicitation | confirm | recommendation
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,        -- 'user' | 'assistant'
    kind TEXT NOT NULL,        -- 'answer' | 'question' | 'profile_edit' | 'confirmation' | 'recommendation' | 'evidence'
    content JSONB NOT NULL,    -- flexible payload (text, profile snapshot, recommendation data)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for fast history lookups
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
