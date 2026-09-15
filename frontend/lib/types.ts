export type Sentiment = 'Positive' | 'Neutral' | 'Negative' | 'Mixed';
export type Severity = 'Low' | 'Medium' | 'High';
export type Risk = Severity | 'Critical';
export type ValidationStatus = 'approved' | 'approved_with_changes' | 'needs_review' | 'rejected';
export type Approval = 'pending' | 'approved' | 'rejected';
export type CaseStatus =
  'open' | 'under_review' | 'approved_for_contact' | 'resolved' | 'dismissed';
export interface Feedback {
  id: number;
  feedback_id: string;
  source: string;
  submitted_at: string | null;
  rating: number | null;
  customer_name: string | null;
  customer_email: string | null;
  feedback_text: string;
  processing_status: string;
  created_at: string;
}
export interface Aspect {
  id: number;
  category: string;
  sentiment: Sentiment;
  severity: Severity;
  evidence_text: string;
}
export interface Analysis {
  id: number;
  feedback_db_id: number;
  feedback_id: string;
  primary_category: string;
  sentiment: Sentiment;
  severity: Severity;
  summary: string;
  is_mixed: boolean;
  confidence: number;
  requires_review: boolean;
  analysis_status: string;
  model_used: string;
  created_at: string;
  updated_at: string;
  aspects: Aspect[];
}
export interface Validation {
  id: number;
  analysis_id: number;
  feedback_db_id: number;
  feedback_id: string;
  validation_status: ValidationStatus;
  overall_confidence: number;
  requires_human_review: boolean;
  validated_sentiment: Sentiment;
  validated_severity: Severity;
  validated_categories: string[];
  validation_summary: string;
  model_used: string;
  created_at: string;
  updated_at: string;
  issues: { id: number; field: string; issue_type: string; message: string }[];
}
export interface FeedbackRow {
  feedback: Feedback;
  analysis?: Analysis;
  validation?: Validation;
}
export interface SentimentCounts {
  positive: number;
  neutral: number;
  negative: number;
  mixed: number;
}
export interface SeverityCounts {
  low: number;
  medium: number;
  high: number;
}
export interface SentimentMetrics extends SentimentCounts {
  total: number;
  positive_percentage: number;
  neutral_percentage: number;
  negative_percentage: number;
  mixed_percentage: number;
}
export interface Overview {
  total_feedback_count: number;
  trusted_validated_feedback_count: number;
  records_requiring_human_review: number;
  rated_feedback_count: number;
  average_rating: number | null;
  total_aspect_count: number;
  source_counts: { source: string; count: number; percentage: number }[];
  recurring_negative_trend_count: number;
  recurring_positive_pattern_count: number;
}
export interface CategoryMetric {
  category: string;
  feedback_count: number;
  aspect_count: number;
  percentage: number;
  aspect_percentage: number;
  sentiment_counts: SentimentCounts;
  severity_counts: SeverityCounts;
}
export interface Categories {
  trusted_feedback_count: number;
  total_aspect_count: number;
  categories: CategoryMetric[];
}
export interface SeverityMetrics extends SeverityCounts {
  total: number;
  high_severity_negative: number;
  high_severity_by_category: { category: string; count: number }[];
}
export interface Pattern {
  category: string;
  sentiment: Sentiment;
  feedback_count: number;
  recurring: boolean;
  supporting_feedback_ids: string[];
}
export interface Trends {
  threshold: number;
  positive_patterns: Pattern[];
  negative_patterns: Pattern[];
}
export interface Timeline {
  period: 'daily' | 'weekly';
  points: (SentimentCounts & {
    period_start: string;
    total: number;
    category_counts: { category: string; count: number }[];
  })[];
}
export interface Emerging {
  period: string;
  current_period_start: string | null;
  previous_period_start: string | null;
  minimum_current_count: number;
  percentage_increase_threshold: number;
  issues: {
    category: string;
    status: string;
    previous_count: number;
    current_count: number;
    percentage_change: number | null;
    supporting_feedback_ids: string[];
  }[];
}
export interface Recommendation {
  id: number;
  category: string;
  priority: Risk;
  problem_summary: string;
  recommendation: string;
  business_rationale: string;
  evidence_count: number;
  supporting_feedback_ids: string[];
  requires_management_approval: boolean;
  approval_status: Approval;
  confidence: number;
  model_used: string;
  created_at: string;
  updated_at: string;
  approval_history: { id: number; decision: Approval; decided_at: string }[];
}
export interface RecoveryCase {
  id: number;
  feedback_db_id: number;
  feedback_id: string;
  risk_level: Risk;
  risk_score: number;
  recovery_required: boolean;
  status: CaseStatus;
  reasons: { id: number; reason: string }[];
  suggested_action: string | null;
  response_draft: string | null;
  assigned_to: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}
export interface ImportSummary {
  total_rows: number;
  imported_rows: number;
  skipped_rows: number;
  failed_rows: number;
  errors: { row: number; feedback_id: string | null; code: string; message: string }[];
}
export interface DashboardData {
  overview: Overview;
  sentiment: SentimentMetrics;
  categories: Categories;
  severity: SeverityMetrics;
  trends: Trends;
  timeline: Timeline;
  emerging: Emerging;
  cases: RecoveryCase[];
}

export interface AnalysisState {
  total: number;
  pending: number;
  requires_review: number;
  is_running: boolean;
}
export interface PipelineResult {
  feedback_db_id: number;
  feedback_id: string;
  status: 'completed' | 'requires_review' | 'failed';
  classification_status: 'pending' | 'completed';
  validation_status: ValidationStatus | null;
  requires_human_review: boolean;
  reused: boolean;
  analysis: Analysis | null;
  validation: Validation | null;
  recovery: RecoveryCase | null;
  error: {
    stage: 'classification' | 'validation' | 'recovery';
    code: string;
    message: string;
  } | null;
}
export interface PipelineBatchSummary {
  total_pending: number;
  completed: number;
  requires_review: number;
  failed: number;
  classification_failures: number;
  validation_failures: number;
  recovery_failures: number;
  results: PipelineResult[];
}
