export interface PersonSummary {
  person_id: string;
  full_name: string;
  branch: string;
  chamber: string | null;
  state: string | null;
  party: string | null;
  office: string | null;
  agency: string | null;
  court: string | null;
  service_start: string;
  service_end: string | null;
}

export interface PersonDetail extends PersonSummary {
  district: string | null;
  created_at: string | null;
}

export interface PersonListResponse {
  items: PersonSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface PublicOfficialRoleItem {
  role_id: string;
  person_id: string;
  external_role_id: string;
  external_person_id: string;
  full_name: string;
  branch: string;
  presidential_term: string;
  administration: string;
  role_category: string;
  role_title: string;
  office: string | null;
  agency: string | null;
  court: string | null;
  service_start: string | null;
  service_end: string | null;
  appointing_president: string | null;
  source_id: string;
  source_name: string;
  source_url: string;
  source_tier: string;
  source_retrieved_at: string | null;
  source_metadata: Record<string, unknown>;
}

export interface PublicOfficialRoleListResponse {
  items: PublicOfficialRoleItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface ScorecardResponse {
  transaction_level_reporting: string;
  typical_reporting_lag_days: number | null;
  disclosure_type: string;
  completeness_rating: number;
  grade: string;
  notes: string[];
  metrics: {
    trade_count: number;
    filing_count: number;
    median_lag_days: number | null;
    negative_lag_count: number;
    low_parser_confidence_count: number;
  };
  deductions: {
    rule_id: string;
    points: number;
    explanation: string;
    evidence_count: number;
  }[];
}

export interface TimelineBucket {
  start: string;
  end: string;
  trade_count: number;
  buy_count: number;
  sell_count: number;
  median_lag_days: number | null;
}

export interface TimelineGap {
  start: string;
  end: string;
  gap_type: string;
  display_label: string;
}

export interface TimelineResponse {
  bucket: "month" | "week" | "day";
  start: string | null;
  end: string | null;
  buckets: TimelineBucket[];
  gaps: TimelineGap[];
}

export interface TradeRow {
  id: string;
  person_id: string;
  filing_id: string;
  trade_date: string;
  reported_date: string;
  action: string;
  raw_asset_text: string;
  asset_display_name: string;
  ticker: string | null;
  asset_class: string;
  value_range_label: string;
  value_range_min: number | null;
  value_range_max: number | null;
  disclosure_lag_days: number;
  parsing_confidence: number | null;
  asset_match_confidence: number | null;
}

export interface TradeListResponse {
  items: TradeRow[];
  page: number;
  page_size: number;
  total: number;
}

export interface ProvenanceInfo {
  source_url?: string | null;
  retrieved_at?: string | null;
  file_hash?: string | null;
  provenance_complete?: boolean | null;
}

export interface TradeDetail extends TradeRow {
  provenance?: ProvenanceInfo | null;
}

export interface FilingDetail {
  id: string;
  person_id: string;
  filing_type: string;
  filed_date: string;
  source_url: string;
  retrieved_at: string;
  file_hash: string;
  retrieval_source: string;
  raw_document_id: string | null;
  superseded_by_filing_id: string | null;
  provenance_complete: boolean;
  created_at: string | null;
}

export interface RawDocumentDetail {
  id: string;
  ingestion_run_id: string;
  source_url: string;
  retrieved_at: string;
  retrieval_source: string;
  content_type: string;
  file_hash: string;
  storage_uri: string | null;
  rights_status: string;
  parser_version: string;
  provenance_complete: boolean;
  source_metadata: Record<string, unknown>;
  created_at: string | null;
}

export interface MarketPoint {
  date: string;
  value: number;
}

export interface MarketSeriesItem {
  symbol: string;
  freq: string;
  start: string;
  end: string;
  points: MarketPoint[];
}

export interface EventItem {
  event_id: string;
  date: string;
  label: string;
  event_type: string;
  source_links: string[];
  description: string | null;
}

export interface ShareCardCreateResponse {
  sharecard_id: string;
  render_url: string | null;
  permalink_url: string | null;
  sources: string[];
  disclaimer_text: string;
  dataset_version: string;
  methodology_version: string;
  generated_at: string;
}

export interface MetaStatus {
  last_ingestion_run_at: string | null;
  dataset_version: string;
  parser_version: string;
  methodology_version: string;
}

export interface MethodologyBlock {
  title: string;
  content: string;
}

export interface MethodologyResponse {
  blocks: MethodologyBlock[];
  key_rules: string[];
}

export interface OfficialSourceInfo {
  id: string;
  name: string;
  branch: string;
  chamber: string | null;
  source_url: string;
  search_url: string | null;
  download_url: string | null;
  access_mode: string | null;
  public_sample_url: string | null;
  ingestion_status: string;
  records_scope: string;
  rights_note: string;
  provenance_requirements: string[];
}

export interface OfficialSourcesResponse {
  dataset_version: string;
  methodology_version: string;
  sources: OfficialSourceInfo[];
}

export interface SourceCompletenessItem {
  source_id: string;
  branch: string;
  ingestion_status: string;
  has_completed_ingestion: boolean;
  raw_document_count: number;
  filing_count: number;
  provenance_requirements_count: number;
  missing_capabilities: string[];
}

export interface SourceCompletenessResponse {
  dataset_version: string;
  sources: SourceCompletenessItem[];
}

export interface ParserArtifactItem {
  id: string;
  source_id: string;
  raw_document_id: string;
  filing_id: string | null;
  trade_id: string | null;
  artifact_type: string;
  page_number: number | null;
  row_number: number | null;
  text_span: Record<string, unknown>;
  parser_output: Record<string, unknown>;
  confidence: number | null;
  created_at: string | null;
}

export interface ParserArtifactListResponse {
  items: ParserArtifactItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface IngestionRunItem {
  id: string;
  source_name: string;
  source_url: string | null;
  started_at: string;
  completed_at: string | null;
  status: string;
  dataset_version: string;
  parser_version: string;
  notes: string | null;
  created_at: string | null;
}

export interface IngestionRunListResponse {
  items: IngestionRunItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface EvidenceSearchResponse {
  items: ParserArtifactItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface DuplicateTradeGroup {
  duplicate_key: string;
  trade_ids: string[];
  person_id: string;
  trade_date: string;
  action: string;
  asset_display_name: string;
  value_range_label: string;
  count: number;
}

export interface DuplicateFilingGroup {
  duplicate_key: string;
  filing_ids: string[];
  person_id: string;
  filed_date: string;
  filing_type: string;
  file_hash: string;
  count: number;
}

export interface DuplicateReportResponse {
  trade_groups: DuplicateTradeGroup[];
  filing_groups: DuplicateFilingGroup[];
}

export interface BatchStatsItem {
  trades_count: number;
  last_filing_processed_at: string | null;
  median_lag_days: number | null;
}
