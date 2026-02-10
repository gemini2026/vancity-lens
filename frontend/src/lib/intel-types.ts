/** Intelligence layer types */

export type SignalType =
  | "rezoning_decision"
  | "permit_approval"
  | "policy_change"
  | "community_opposition"
  | "density_change"
  | "development_proposal"
  | "infrastructure_investment";

export type Severity = "critical" | "high" | "medium" | "low";
export type SourceType = "council_minutes" | "permit_records" | "news_article" | "community_notice" | "government_policy";

export interface IntelSignal {
  id: string;
  document_id: string;
  signal_type: SignalType;
  summary: string;
  headline: string;
  addresses: string[];
  neighborhood: string;
  decision?: string;
  vote_for?: number;
  vote_against?: number;
  sentiment: "positive" | "neutral" | "negative";
  severity: Severity;
  confidence: number;
  event_date: string;
  source_title: string;
  source_url: string;
  source_type: SourceType;
  source_date: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: SourceCitation[];
  related_signals?: string[];
}

export interface SourceCitation {
  document_title: string;
  document_url: string;
  source_type: SourceType;
  published_date: string;
  relevance_score: number;
  excerpt: string;
  // RAG-005: Provenance chain fields
  document_id?: number;
  chunk_id?: number;
  url_status?: string;
  archive_url?: string;
}

export interface SignalFeedResponse {
  signals: IntelSignal[];
  total_count: number;
  has_more: boolean;
}

export interface ChatResponse {
  answer: string;
  citations: SourceCitation[];
  related_signals: IntelSignal[];
  session_id: string;
  mode?: "full" | "partial" | "demo";
}

export interface IntelStats {
  total_signals: number;
  by_type: Record<SignalType, number>;
  by_neighborhood: Record<string, number>;
  by_severity: Record<Severity, number>;
  recent_7d: number;
  recent_30d: number;
}

/** Neighborhood scorecard types */

export type MetricCategory =
  | "safety"
  | "schools"
  | "transit"
  | "parks"
  | "development"
  | "air_quality"
  | "affordability"
  | "walkability";

export type TrendDirection = "improving" | "stable" | "declining";

export interface CategoryScore {
  category: MetricCategory;
  score: number;
  trend: TrendDirection;
  trend_delta: number;
}

export interface NeighborhoodSummary {
  name: string;
  slug: string;
  overall_score: number;
  rank: number;
  top_category: string;
  bottom_category: string;
}

export interface NeighborhoodScorecard {
  neighborhood: { name: string; slug: string };
  overall_score: number;
  rank: number;
  category_scores: CategoryScore[];
  active_rezonings: number;
  recent_permits: number;
}

export interface NeighborhoodComparison {
  neighborhoods: NeighborhoodScorecard[];
  categories: MetricCategory[];
}

/** Signal document response */
export interface SignalDocument {
  signal: {
    id: number;
    signal_type: string;
    headline: string;
    summary: string;
    addresses: string[];
    neighborhood: string;
    decision?: string;
    vote_for?: number;
    vote_against?: number;
    sentiment: string;
    severity: string;
    confidence: number;
    event_date?: string;
    zoning_from?: string;
    zoning_to?: string;
    unit_count?: number;
  };
  document: {
    id: number;
    title: string;
    source_type: string;
    source_url: string;
    published_date?: string;
    raw_text: string;
    url_status?: string | null;
    archive_url?: string | null;
  };
}

/** RAG-001: Archived document viewer */
export interface DocumentView {
  id: number;
  title: string | null;
  source_url: string;
  source_type: string;
  published_date: string | null;
  raw_text: string;
  text_length: number;
  page_count: number;
  url_status: string | null;
  archive_url: string | null;
}

/** URL ingestion result */
export interface IngestResult {
  document_id: number;
  title: string | null;
  text_length: number;
  page_count: number;
  status: "new" | "exists";
  processing: boolean;
}

/** RAG-011: Document processing status */
export interface DocumentStatus {
  document_id: number;
  title: string | null;
  status: "pending" | "processing" | "completed" | "failed";
  has_raw_text: boolean;
  chunk_count: number;
  signal_count: number;
  scraped_at: string | null;
  processed_at: string | null;
}

/** GeoJSON types for map overlay */
export namespace GeoJSON {
  export interface Point {
    type: "Point";
    coordinates: [number, number];
  }
  export interface Feature {
    type: "Feature";
    geometry: Point;
    properties: {
      id: number;
      signal_type: string;
      headline: string;
      summary: string;
      neighborhood: string;
      severity: Severity;
      decision?: string;
      confidence: number;
      event_date?: string;
      addresses: string[];
      source_title: string;
      source_url: string;
      source_type: string;
    };
  }
  export interface FeatureCollection {
    type: "FeatureCollection";
    features: Feature[];
  }
}
