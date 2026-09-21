-- MineralIQ schema v1 (PostgreSQL 15+)
-- Stage 1 foundation. Contracts: tables below are frozen; changes need a new migration + contract test.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('patent','rd','publication')),
  access_method TEXT NOT NULL,
  licence_note TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS taxonomy_versions (
  version TEXT PRIMARY KEY,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS records (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_id TEXT NOT NULL REFERENCES sources(id),
  source_url TEXT NOT NULL,
  fetched_at DATE NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('patent','rd','publication')),
  -- patent fields (nullable for rd)
  appl_no TEXT,
  title TEXT NOT NULL,
  abstract TEXT,
  applicants TEXT[] DEFAULT '{}',
  inventors TEXT[] DEFAULT '{}',
  ipc_codes TEXT[] DEFAULT '{}',
  filing_date DATE,
  legal_status TEXT,
  -- classification (populated Stage 3; nullable in Stage 1/2)
  mineral_ids TEXT[] DEFAULT '{}',
  stage_ids TEXT[] DEFAULT '{}',
  process_family_ids TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (source_id, source_url)
);

CREATE TABLE IF NOT EXISTS organisations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  canonical_name TEXT UNIQUE NOT NULL,
  aliases TEXT[] DEFAULT '{}',
  kind TEXT CHECK (kind IN ('csir','iit','nit','psu','startup','industry','gov','other'))
);

CREATE TABLE IF NOT EXISTS record_org_links (
  record_id UUID REFERENCES records(id) ON DELETE CASCADE,
  org_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
  role TEXT CHECK (role IN ('applicant','assignee',' performer','author_affil','funder')),
  PRIMARY KEY (record_id, org_id, role)
);

CREATE INDEX IF NOT EXISTS idx_records_mineral ON records USING GIN (mineral_ids);
CREATE INDEX IF NOT EXISTS idx_records_stage ON records USING GIN (stage_ids);
CREATE INDEX IF NOT EXISTS idx_records_title_trgm ON records USING GIN (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_records_appl ON records (appl_no);
