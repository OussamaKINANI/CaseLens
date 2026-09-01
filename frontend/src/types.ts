export type ReviewerRole = "reviewer" | "administrator";

export interface Reviewer {
  id: string;
  email: string;
  full_name: string;
  role: ReviewerRole;
  is_active: boolean;
  created_at: string;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in_seconds: number;
  reviewer: Reviewer;
}

export type CasePriority = "routine" | "urgent";

export type CaseStatus =
  | "received"
  | "processing"
  | "awaiting_review"
  | "completed"
  | "failed";

export type ReviewRunStatus =
  | "queued"
  | "running"
  | "awaiting_human_review"
  | "completed"
  | "rejected"
  | "failed";

export interface ClinicalCase {
  id: string;
  patient_external_id: string;
  requested_service: string;
  priority: CasePriority;
  status: CaseStatus;
  created_at: string;
}

export interface ClinicalDocument {
  id: string;
  case_id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  content_sha256: string;
  uploaded_at: string;
}

export interface EvidenceCitation {
  document_id: string;
  exact_quote: string;
  start_char: number;
  end_char: number;
}

export interface ClinicalFact {
  fact_type:
    | "condition"
    | "symptom"
    | "medication"
    | "procedure"
    | "lab_result"
    | "allergy"
    | "demographic"
    | "other";
  name: string;
  value: string | null;
  assertion:
    | "present"
    | "absent"
    | "possible"
    | "historical";
  evidence: EvidenceCitation[];
}

export interface ClinicalExtractionResult {
  schema_version: "1.0";
  facts: ClinicalFact[];
  missing_information: string[];
  warnings: string[];
}

export interface ClinicalExtraction {
  id: string;
  case_id: string;
  document_id: string;
  provider_name: string;
  model_name: string;
  schema_version: string;
  source_sha256: string;
  result: ClinicalExtractionResult;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  case_id: string;
  event_type: string;
  actor_type: "system" | "reviewer";
  details: Record<string, unknown>;
  created_at: string;
}

export interface CaseReviewRun {
  id: string;
  case_id: string;
  status: ReviewRunStatus;
  document_ids: string[];
  temporal_workflow_id: string;
  failure_code: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ReviewCommandResponse {
  review_run_id: string;
  temporal_workflow_id: string;
  command_status: string;
}

export interface RetrievedChunk {
  id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  start_char: number;
  end_char: number;
  content_sha256: string;
  embedding_model: string;
  similarity: number;
}

export interface CaseSearchResponse {
  query: string;
  top_k: number;
  min_similarity: number;
  embedding_model: string;
  result_count: number;
  results: RetrievedChunk[];
}

export interface AnswerCitation {
  chunk_id: string;
  document_id: string;
  exact_quote: string;
  start_char: number;
  end_char: number;
}

export interface GroundedAnswer {
  schema_version: "1.0";
  supported: boolean;
  answer: string;
  citations: AnswerCitation[];
}

export interface CaseAnswerResponse {
  query: string;
  top_k: number;
  min_similarity: number;
  embedding_model: string;
  answer_provider: string;
  answer_model: string;
  retrieved_chunk_count: number;
  answer: GroundedAnswer;
}

export interface ReadinessResponse {
  status: "ready";
  database: "reachable";
}