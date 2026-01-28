BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'policy_status') THEN
        CREATE TYPE policy_status AS ENUM ('crawl_allowed', 'partner_required', 'manual_only', 'unknown');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_type') THEN
        CREATE TYPE task_type AS ENUM ('SearchTask', 'MapTask', 'CrawlTask', 'ScrapeTask', 'ImportTask');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'evidence_kind') THEN
        CREATE TYPE evidence_kind AS ENUM ('text_span', 'image_region');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'listing_status') THEN
        CREATE TYPE listing_status AS ENUM ('active', 'pending', 'off_market', 'removed', 'unknown');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_channel') THEN
        CREATE TYPE alert_channel AS ENUM ('local', 'smtp');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS sources (
    source_id uuid PRIMARY KEY,
    name text,
    kind text,
    base_domains text[],
    created_at timestamp
);

CREATE TABLE IF NOT EXISTS document_snapshots (
    snapshot_id uuid PRIMARY KEY,
    source_id uuid REFERENCES sources(source_id),
    url text,
    fetched_at timestamp,
    http_status int,
    content_hash text NOT NULL,
    formats jsonb,
    storage_refs jsonb,
    change_tracking jsonb,
    raw_metadata jsonb,
    immutable boolean NOT NULL DEFAULT true,
    CONSTRAINT document_snapshots_immutable CHECK (immutable = true)
);

CREATE TABLE IF NOT EXISTS source_policies (
    policy_id uuid PRIMARY KEY,
    source_id uuid REFERENCES sources(source_id),
    policy_status policy_status NOT NULL,
    allowed_operations text[],
    robots_snapshot_id uuid REFERENCES document_snapshots(snapshot_id),
    tos_url text,
    compliance_summary text,
    reviewer text,
    reviewed_at timestamp,
    version int
);

CREATE TABLE IF NOT EXISTS source_observations (
    observation_id uuid PRIMARY KEY,
    snapshot_id uuid REFERENCES document_snapshots(snapshot_id),
    source_id uuid REFERENCES sources(source_id),
    extracted_json jsonb,
    extractor_version text,
    validation_report jsonb,
    created_at timestamp
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id uuid PRIMARY KEY,
    observation_id uuid REFERENCES source_observations(observation_id),
    entity_type text,
    entity_id uuid,
    field_path text,
    value_json jsonb,
    confidence numeric,
    extractor text,
    extracted_at timestamp,
    is_canonical boolean DEFAULT false,
    CONSTRAINT facts_confidence_required CHECK (value_json IS NULL OR confidence IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id uuid PRIMARY KEY,
    snapshot_id uuid REFERENCES document_snapshots(snapshot_id),
    kind evidence_kind NOT NULL,
    locator jsonb,
    excerpt text,
    created_at timestamp
);

CREATE TABLE IF NOT EXISTS fact_evidence (
    fact_id uuid REFERENCES facts(fact_id),
    evidence_id uuid REFERENCES evidence(evidence_id),
    rank int,
    PRIMARY KEY (fact_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id uuid PRIMARY KEY,
    task_type task_type NOT NULL,
    source_id uuid REFERENCES sources(source_id),
    policy_id uuid REFERENCES source_policies(policy_id),
    domain text,
    payload jsonb,
    status text,
    attempt int,
    max_attempts int,
    scheduled_at timestamp,
    created_at timestamp
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id uuid PRIMARY KEY,
    task_id uuid REFERENCES tasks(task_id),
    policy_id uuid REFERENCES source_policies(policy_id),
    outcome text,
    params jsonb,
    error_class text,
    created_at timestamp
);

CREATE INDEX IF NOT EXISTS idx_document_snapshots_url_hash ON document_snapshots (url, content_hash);
CREATE INDEX IF NOT EXISTS idx_source_observations_snapshot_source ON source_observations (snapshot_id, source_id);
CREATE INDEX IF NOT EXISTS idx_facts_field_path ON facts (field_path);
CREATE INDEX IF NOT EXISTS idx_fact_evidence_fact_evidence ON fact_evidence (fact_id, evidence_id);

CREATE OR REPLACE FUNCTION enforce_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'immutable table';
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_document_snapshots_immutable') THEN
        CREATE TRIGGER trg_document_snapshots_immutable
            BEFORE UPDATE OR DELETE ON document_snapshots
            FOR EACH ROW EXECUTE FUNCTION enforce_immutable();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_evidence_immutable') THEN
        CREATE TRIGGER trg_evidence_immutable
            BEFORE UPDATE OR DELETE ON evidence
            FOR EACH ROW EXECUTE FUNCTION enforce_immutable();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_facts_append_only') THEN
        CREATE TRIGGER trg_facts_append_only
            BEFORE UPDATE OR DELETE ON facts
            FOR EACH ROW EXECUTE FUNCTION enforce_immutable();
    END IF;
END $$;

COMMIT;
