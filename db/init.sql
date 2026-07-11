CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE people (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT 'Legislative',
    chamber TEXT CHECK (chamber IN ('House', 'Senate')),
    state TEXT,
    party TEXT,
    district TEXT,
    office TEXT,
    agency TEXT,
    court TEXT,
    service_start DATE NOT NULL,
    service_end DATE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE public_official_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES people(id),
    external_role_id TEXT NOT NULL UNIQUE,
    external_person_id TEXT NOT NULL,
    branch TEXT NOT NULL CHECK (branch IN ('Executive','Judicial','Legislative')),
    presidential_term TEXT NOT NULL,
    administration TEXT NOT NULL,
    role_category TEXT NOT NULL,
    role_title TEXT NOT NULL,
    office TEXT,
    agency TEXT,
    court TEXT,
    service_start DATE,
    service_end DATE,
    appointing_president TEXT,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_tier TEXT NOT NULL DEFAULT 'official',
    source_retrieved_at DATE,
    source_metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_public_official_roles_person ON public_official_roles(person_id);
CREATE INDEX idx_public_official_roles_branch_term ON public_official_roles(branch, presidential_term);
CREATE INDEX idx_public_official_roles_category ON public_official_roles(role_category);

CREATE TABLE congressional_service_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES people(id),
    bioguide_id TEXT NOT NULL,
    congress_number INT NOT NULL,
    chamber TEXT NOT NULL CHECK (chamber IN ('House','Senate')),
    state TEXT,
    district TEXT,
    party TEXT,
    service_start DATE,
    service_end DATE,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_retrieved_at DATE,
    source_metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (bioguide_id, congress_number, chamber, state, district)
);

CREATE INDEX idx_congressional_service_terms_person ON congressional_service_terms(person_id);
CREATE INDEX idx_congressional_service_terms_bioguide ON congressional_service_terms(bioguide_id);
CREATE INDEX idx_congressional_service_terms_congress ON congressional_service_terms(congress_number, chamber);
CREATE INDEX idx_congressional_service_terms_state_party ON congressional_service_terms(state, party);

CREATE TABLE service_periods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES people(id),
    public_official_role_id UUID REFERENCES public_official_roles(id),
    branch TEXT NOT NULL,
    role_title TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    source_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_service_periods_identity UNIQUE (person_id, role_title, start_date, source_id)
);

CREATE INDEX idx_service_periods_person_dates ON service_periods(person_id, start_date, end_date);
CREATE INDEX idx_service_periods_branch_dates ON service_periods(branch, start_date, end_date);

CREATE TABLE ingestion_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,
    source_url TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running','completed','failed')),
    dataset_version TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE raw_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_run_id UUID NOT NULL REFERENCES ingestion_runs(id),
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    retrieval_source TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    storage_uri TEXT,
    rights_status TEXT NOT NULL DEFAULT 'public_record',
    parser_version TEXT NOT NULL,
    provenance_complete BOOLEAN NOT NULL DEFAULT true,
    source_metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE filings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES people(id),
    filing_type TEXT NOT NULL DEFAULT 'PTR',
    filed_date DATE NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    file_hash TEXT NOT NULL,
    retrieval_source TEXT NOT NULL DEFAULT 'fixture',
    raw_document_id UUID REFERENCES raw_documents(id),
    superseded_by_filing_id UUID REFERENCES filings(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE issuers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT NOT NULL,
    cik TEXT,
    lei TEXT,
    source_url TEXT,
    source_metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_issuers_name_cik UNIQUE (canonical_name, cik)
);

CREATE INDEX idx_issuers_cik ON issuers(cik);

CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer_id UUID REFERENCES issuers(id),
    canonical_name TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    primary_symbol TEXT,
    source_metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_assets_identity UNIQUE (canonical_name, asset_class, primary_symbol)
);

CREATE INDEX idx_assets_symbol ON assets(primary_symbol);
CREATE INDEX idx_assets_issuer ON assets(issuer_id);

CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES people(id),
    filing_id UUID NOT NULL REFERENCES filings(id),
    asset_id UUID REFERENCES assets(id),
    trade_date DATE NOT NULL,
    reported_date DATE NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL', 'EXCHANGE', 'OTHER')),
    raw_asset_text TEXT NOT NULL,
    asset_display_name TEXT NOT NULL,
    ticker TEXT,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('equity','etf','mutual_fund','bond','fixed_income','crypto','option','commodity','real_estate','private_equity','other','unknown')),
    value_range_label TEXT NOT NULL,
    value_range_min NUMERIC,
    value_range_max NUMERIC,
    disclosure_lag_days INT NOT NULL,
    parsing_confidence NUMERIC,
    asset_match_confidence NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_trades_person_trade_date ON trades(person_id, trade_date);
CREATE INDEX idx_trades_person_reported_date ON trades(person_id, reported_date);
CREATE INDEX idx_trades_ticker ON trades(ticker);
CREATE INDEX idx_trades_asset ON trades(asset_id);

CREATE TABLE parser_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id TEXT NOT NULL,
    raw_document_id UUID NOT NULL REFERENCES raw_documents(id),
    filing_id UUID REFERENCES filings(id),
    trade_id UUID REFERENCES trades(id),
    artifact_type TEXT NOT NULL CHECK (artifact_type IN ('document','filing','trade','row','warning','preview')),
    page_number INT,
    row_number INT,
    text_span JSONB NOT NULL DEFAULT '{}',
    parser_output JSONB NOT NULL DEFAULT '{}',
    confidence NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_parser_artifacts_source ON parser_artifacts(source_id);
CREATE INDEX idx_parser_artifacts_raw_document ON parser_artifacts(raw_document_id);

CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    label TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('legislation','bill_action','vote','funding','executive_order','presidential_document','agency_rule','court_decision','macro_release','role_change','macro','crypto_policy','other')),
    description TEXT,
    announcement_date DATE,
    effective_date DATE,
    publication_date DATE,
    source_tier TEXT NOT NULL DEFAULT 'official',
    editor_status TEXT NOT NULL DEFAULT 'curated',
    methodology_version TEXT NOT NULL DEFAULT 'event-relevance-v1',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE event_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id),
    url TEXT NOT NULL
);

CREATE TABLE event_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id),
    person_id UUID REFERENCES people(id),
    asset_id UUID REFERENCES assets(id),
    organization_name TEXT,
    relationship_type TEXT NOT NULL,
    evidence_tier TEXT NOT NULL,
    rationale TEXT NOT NULL,
    source_url TEXT NOT NULL,
    methodology_version TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'candidate',
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT ck_event_relationships_target CHECK (
        person_id IS NOT NULL OR asset_id IS NOT NULL OR organization_name IS NOT NULL
    )
);

CREATE INDEX idx_event_relationships_event ON event_relationships(event_id);
CREATE INDEX idx_event_relationships_person ON event_relationships(person_id);
CREATE INDEX idx_event_relationships_asset ON event_relationships(asset_id);
CREATE INDEX idx_event_relationships_tier ON event_relationships(evidence_tier, review_status);

CREATE TABLE trade_event_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id UUID NOT NULL REFERENCES trades(id),
    event_id UUID NOT NULL REFERENCES events(id),
    days_from_event INT NOT NULL,
    evidence_tier TEXT NOT NULL,
    relationship_reasons JSONB NOT NULL DEFAULT '[]',
    internal_rank NUMERIC,
    methodology_version TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'candidate',
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_trade_event_candidates_version UNIQUE (trade_id, event_id, methodology_version)
);

CREATE INDEX idx_trade_event_candidates_trade ON trade_event_candidates(trade_id);
CREATE INDEX idx_trade_event_candidates_event ON trade_event_candidates(event_id);
CREATE INDEX idx_trade_event_candidates_tier ON trade_event_candidates(evidence_tier, review_status);

CREATE TABLE relationship_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES trade_event_candidates(id),
    decision TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reason TEXT NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_relationship_reviews_candidate ON relationship_reviews(candidate_id);

CREATE TABLE data_quality_issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_data_quality_issues_entity ON data_quality_issues(entity_type, entity_id);
CREATE INDEX idx_data_quality_issues_status ON data_quality_issues(status, severity);

CREATE TABLE market_series (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    freq TEXT NOT NULL DEFAULT 'd',
    date DATE NOT NULL,
    value NUMERIC NOT NULL,
    UNIQUE(symbol, freq, date)
);

CREATE TABLE sharecards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope TEXT NOT NULL CHECK (scope IN ('trade','range')),
    person_id UUID NOT NULL REFERENCES people(id),
    trade_id UUID REFERENCES trades(id),
    range_start DATE,
    range_end DATE,
    overlays JSONB NOT NULL DEFAULT '["SPY","DIA"]',
    include_events BOOLEAN NOT NULL DEFAULT true,
    sources JSONB NOT NULL DEFAULT '[]',
    disclaimer_text TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    methodology_version TEXT NOT NULL,
    render_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
