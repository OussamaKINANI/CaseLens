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


export class ApiError extends Error {
  readonly status: number;

  constructor(
    message: string,
    status: number,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function jsonOptions(
  method: string,
  body?: unknown,
): RequestInit {
  return {
    method,

    headers: {
      "Content-Type": "application/json",
    },

    body:
      body === undefined
        ? undefined
        : JSON.stringify(body),
  };
}

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const headers = new Headers(
    options?.headers,
  );

  headers.set(
    "Accept",
    "application/json",
  );

  const response = await fetch(path, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message =
      `Request failed with status ${response.status}`;

    try {
      const body = (await response.json()) as {
        detail?:
          | string
          | Array<{
              msg?: string;
            }>;
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

    throw new ApiError(
      message,
      response.status,
    );
  }

  return (await response.json()) as T;
}

export function getReadiness(): Promise<ReadinessResponse> {
  return request<ReadinessResponse>(
    "/ready",
  );
}

export function listCases(): Promise<ClinicalCase[]> {
  return request<ClinicalCase[]>(
    "/v1/cases",
  );
}

export function listCaseDocuments(
  caseId: string,
): Promise<ClinicalDocument[]> {
  return request<ClinicalDocument[]>(
    `/v1/cases/${caseId}/documents`,
  );
}

export function listCaseExtractions(
  caseId: string,
): Promise<ClinicalExtraction[]> {
  return request<ClinicalExtraction[]>(
    `/v1/cases/${caseId}/extractions`,
  );
}

export function listCaseAuditEvents(
  caseId: string,
): Promise<AuditEvent[]> {
  return request<AuditEvent[]>(
    `/v1/cases/${caseId}/audit`,
  );
}

export function listCaseReviewRuns(
  caseId: string,
): Promise<CaseReviewRun[]> {
  return request<CaseReviewRun[]>(
    `/v1/cases/${caseId}/review-runs`,
  );
}

export function searchCase(
  caseId: string,
  query: string,
  topK = 3,
): Promise<CaseSearchResponse> {
  return request<CaseSearchResponse>(
    `/v1/cases/${caseId}/search`,
    jsonOptions(
      "POST",
      {
        query,
        top_k: topK,
      },
    ),
  );
}

export function answerCaseQuestion(
  caseId: string,
  query: string,
  topK = 3,
): Promise<CaseAnswerResponse> {
  return request<CaseAnswerResponse>(
    `/v1/cases/${caseId}/answer`,
    jsonOptions(
      "POST",
      {
        query,
        top_k: topK,
      },
    ),
  );
}

export function createCaseReviewRun(
  caseId: string,
  documentIds: string[],
): Promise<CaseReviewRun> {
  return request<CaseReviewRun>(
    `/v1/cases/${caseId}/review-runs`,
    jsonOptions(
      "POST",
      {
        document_ids: documentIds,
      },
    ),
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
    jsonOptions(
      "POST",
      {
        decision,
        notes,
      },
    ),
  );
}