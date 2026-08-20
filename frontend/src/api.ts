import type {
  ClinicalCase,
  ReadinessResponse,
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

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    ...options,

    headers: {
      Accept: "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;

    try {
      const body = (await response.json()) as {
        detail?: string;
      };

      if (body.detail) {
        message = body.detail;
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
  return request<ReadinessResponse>("/ready");
}

export function listCases(): Promise<ClinicalCase[]> {
  return request<ClinicalCase[]>("/v1/cases");
}