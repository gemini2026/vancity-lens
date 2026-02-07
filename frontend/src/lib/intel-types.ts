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
}

export interface IntelStats {
  total_signals: number;
  by_type: Record<SignalType, number>;
  by_neighborhood: Record<string, number>;
  by_severity: Record<Severity, number>;
  recent_7d: number;
  recent_30d: number;
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
