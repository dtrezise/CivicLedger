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

CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES people(id),
    filing_id UUID NOT NULL REFERENCES filings(id),
    trade_date DATE NOT NULL,
    reported_date DATE NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL', 'EXCHANGE', 'OTHER')),
    raw_asset_text TEXT NOT NULL,
    asset_display_name TEXT NOT NULL,
    ticker TEXT,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('equity','etf','mutual_fund','bond','crypto','other','unknown')),
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

CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL,
    label TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('legislation','role_change','macro','other')),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE event_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id),
    url TEXT NOT NULL
);

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
