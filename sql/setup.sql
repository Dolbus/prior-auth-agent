-- ===========================================
-- Prior Auth Agent — Supabase Table Setup
-- ===========================================
-- Run this in the Supabase SQL Editor to create
-- the required tables for Phase 3 persistence.
-- ===========================================

-- ============================================
-- TABLE: case_results
-- One row per PA workflow run
-- ============================================
CREATE TABLE IF NOT EXISTS case_results (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    patient_id TEXT NOT NULL,
    patient_name TEXT NOT NULL,
    treatment TEXT,
    diagnosis TEXT,
    insurance_provider TEXT,
    pa_decision TEXT NOT NULL,
    expected_outcome TEXT,
    factual_accuracy FLOAT,
    duration_sec FLOAT,
    total_prompt_tokens INTEGER,
    total_completion_tokens INTEGER,
    total_tokens INTEGER,
    cost_usd FLOAT,
    guardrail_violation_rate FLOAT,
    guardrail_checks_total INTEGER,
    guardrail_violations_total INTEGER,
    handoff_success_rate FLOAT,
    handoff_attempts INTEGER,
    handoff_successes INTEGER,
    prompt_token_efficiency FLOAT,
    writer_output TEXT,
    supervisor_notes TEXT[],
    guardrail_violations TEXT[],
    pa_required BOOLEAN DEFAULT true,
    escalated BOOLEAN DEFAULT false,
    payer_feedback TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- TABLE: audit_log
-- One row per agent step within a case run
-- ============================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    case_id UUID REFERENCES case_results(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    step_type TEXT NOT NULL,
    duration_sec FLOAT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    guardrail_checks INTEGER DEFAULT 0,
    guardrail_violations INTEGER DEFAULT 0,
    handoff_attempted BOOLEAN DEFAULT false,
    handoff_succeeded BOOLEAN DEFAULT false,
    notes TEXT,
    escalated_from TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================
-- ROW LEVEL SECURITY — permissive for demo
-- ============================================
ALTER TABLE case_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on case_results"
    ON case_results FOR ALL
    USING (true) WITH CHECK (true);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on audit_log"
    ON audit_log FOR ALL
    USING (true) WITH CHECK (true);

-- ============================================
-- INDEXES for dashboard query performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_case_results_patient_id ON case_results(patient_id);
CREATE INDEX IF NOT EXISTS idx_case_results_created_at ON case_results(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_case_id ON audit_log(case_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_agent_name ON audit_log(agent_name);

-- ============================================
-- MIGRATION CHECKS (Safe to run if upgrading)
-- ============================================
ALTER TABLE case_results ADD COLUMN IF NOT EXISTS pa_required BOOLEAN DEFAULT true;
ALTER TABLE case_results ADD COLUMN IF NOT EXISTS escalated BOOLEAN DEFAULT false;
ALTER TABLE case_results ADD COLUMN IF NOT EXISTS payer_feedback TEXT;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS escalated_from TEXT;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
