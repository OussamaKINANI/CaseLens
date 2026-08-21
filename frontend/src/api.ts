import type {
  AuditEvent,
  CaseAnswerResponse,
  CaseReviewRun,
  CaseSearchResponse,
  ClinicalCase,
  ClinicalDocument,
  ClinicalExtraction,
  ReadinessResponse,
  ReviewCommandResponse,
} from "./types";


const REQUEST_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface RequestOptions {
  signal?: AbortSignal;
}

function jsonOptions(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

async function performRequest(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  const headers = new Headers(options?.headers);
  headers.set("Accept", "application/json");

  const timeoutSignal = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  const signal = options?.signal
    ? AbortSignal.any([options.signal, timeoutSignal])
    : timeoutSignal;

  let response: Response;

  try {
    response = await fetch(path, { ...options, headers, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError(
        "The request timed out. The service may be busy — try again.",
        0,
      );
    }

    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }

    throw new ApiError(
      "Could not reach the CaseLens API. Check that the stack is running.",
      0,
    );
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;

    try {
      const body = (await response.json()) as {
        detail?: string | Array<{ msg?: string }>;
      };

      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item) => item.msg)
          .filter(Boolean)
          .join(", ");
      }
    } catch {
      // Keep the generic HTTP error message.
    }

    throw new ApiError(message, response.status);
  }

  return response;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await performRequest(path, options);
  const contentType = response.headers.get("content-type") ?? "";

  if (response.status === 204 || !contentType.includes("application/json")) {
    throw new ApiError(
      `The API returned an unexpected ${response.status} response.`,
      response.status,
    );
  }

  return (await response.json()) as T;
}

async function requestVoid(
  path: string,
  options?: RequestInit,
): Promise<void> {
  await performRequest(path, options);
}

export function getReadiness(
  options?: RequestOptions,
): Promise<ReadinessResponse> {
  return request<ReadinessResponse>("/ready", options);
}

export function listCases(
  options?: RequestOptions,
): Promise<ClinicalCase[]> {
  return request<ClinicalCase[]>("/v1/cases", options);
}

export function listCaseDocuments(
  caseId: string,
  options?: RequestOptions,
): Promise<ClinicalDocument[]> {
  return request<ClinicalDocument[]>(
    `/v1/cases/${caseId}/documents`,
    options,
  );
}

export function listCaseExtractions(
  caseId: string,
  options?: RequestOptions,
): Promise<ClinicalExtraction[]> {
  return request<ClinicalExtraction[]>(
    `/v1/cases/${caseId}/extractions`,
    options,
  );
}

export function listCaseAuditEvents(
  caseId: string,
  options?: RequestOptions,
): Promise<AuditEvent[]> {
  return request<AuditEvent[]>(`/v1/cases/${caseId}/audit`, options);
}

export function listCaseReviewRuns(
  caseId: string,
  options?: RequestOptions,
): Promise<CaseReviewRun[]> {
  return request<CaseReviewRun[]>(
    `/v1/cases/${caseId}/review-runs`,
    options,
  );
}

export function searchCase(
  caseId: string,
  query: string,
  topK = 3,
): Promise<CaseSearchResponse> {
  return request<CaseSearchResponse>(
    `/v1/cases/${caseId}/search`,
    jsonOptions("POST", { query, top_k: topK }),
  );
}

export function answerCaseQuestion(
  caseId: string,
  query: string,
  topK = 3,
): Promise<CaseAnswerResponse> {
  return request<CaseAnswerResponse>(
    `/v1/cases/${caseId}/answer`,
    jsonOptions("POST", { query, top_k: topK }),
  );
}

export function createCaseReviewRun(
  caseId: string,
  documentIds: string[],
): Promise<CaseReviewRun> {
  return request<CaseReviewRun>(
    `/v1/cases/${caseId}/review-runs`,
    jsonOptions("POST", { document_ids: documentIds }),
  );
}

export function startCaseReviewRun(
  caseId: string,
  reviewRunId: string,
): Promise<ReviewCommandResponse> {
  return request<ReviewCommandResponse>(
    `/v1/cases/${caseId}/review-runs/${reviewRunId}/start`,
    jsonOptions("POST"),
  );
}

export function submitHumanReview(
  caseId: string,
  reviewRunId: string,
  decision: "approve" | "reject",
  notes: string | null,
): Promise<ReviewCommandResponse> {
  return request<ReviewCommandResponse>(
    `/v1/cases/${caseId}/review-runs/${reviewRunId}/human-review`,
    jsonOptions("POST", { decision, notes }),
  );
}

export function createClinicalCase(
  patientExternalId: string,
  requestedService: string,
  priority: "routine" | "urgent",
): Promise<ClinicalCase> {
  return request<ClinicalCase>(
    "/v1/cases",
    jsonOptions("POST", {
      patient_external_id: patientExternalId,
      requested_service: requestedService,
      priority,
    }),
  );
}

export function deleteClinicalCase(caseId: string): Promise<void> {
  return requestVoid(`/v1/cases/${caseId}`, { method: "DELETE" });
}

export function uploadClinicalDocument(
  caseId: string,
  file: File,
): Promise<ClinicalDocument> {
  const formData = new FormData();
  formData.append("file", file);

  return request<ClinicalDocument>(`/v1/cases/${caseId}/documents`, {
    method: "POST",
    body: formData,
  });
}
