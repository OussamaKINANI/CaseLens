export type CasePriority = "routine" | "urgent";

export type CaseStatus =
  | "received"
  | "processing"
  | "awaiting_review"
  | "completed"
  | "failed";

export interface ClinicalCase {
  id: string;
  patient_external_id: string;
  requested_service: string;
  priority: CasePriority;
  status: CaseStatus;
  created_at: string;
}

export interface ReadinessResponse {
  status: "ready";
  database: "reachable";
}