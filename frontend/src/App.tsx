import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getReadiness,
  listCases,
} from "./api";

import type {
  CaseStatus,
  ClinicalCase,
  ReadinessResponse,
} from "./types";

import "./App.css";


type StatusFilter = "all" | CaseStatus;

const STATUS_LABELS: Record<CaseStatus, string> = {
  received: "Received",
  processing: "Processing",
  awaiting_review: "Awaiting review",
  completed: "Completed",
  failed: "Failed",
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(
    "en-US",
    {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    },
  ).format(new Date(value));
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred.";
}

function App() {
  const [cases, setCases] = useState<ClinicalCase[]>([]);
  const [readiness, setReadiness] =
    useState<ReadinessResponse | null>(null);
  const [selectedCase, setSelectedCase] =
    useState<ClinicalCase | null>(null);
  const [statusFilter, setStatusFilter] =
    useState<StatusFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] =
    useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [
      casesResult,
      readinessResult,
    ] = await Promise.allSettled([
      listCases(),
      getReadiness(),
    ]);

    if (casesResult.status === "fulfilled") {
      setCases(casesResult.value);
    } else {
      setError(
        getErrorMessage(casesResult.reason),
      );
    }

    if (readinessResult.status === "fulfilled") {
      setReadiness(readinessResult.value);
    } else {
      setReadiness(null);
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const filteredCases = useMemo(() => {
    const query = searchQuery
      .trim()
      .toLowerCase();

    return cases.filter((clinicalCase) => {
      const matchesStatus =
        statusFilter === "all" ||
        clinicalCase.status === statusFilter;

      const matchesSearch =
        !query ||
        clinicalCase.patient_external_id
          .toLowerCase()
          .includes(query) ||
        clinicalCase.requested_service
          .toLowerCase()
          .includes(query) ||
        clinicalCase.id
          .toLowerCase()
          .includes(query);

      return matchesStatus && matchesSearch;
    });
  }, [
    cases,
    searchQuery,
    statusFilter,
  ]);

  const metrics = useMemo(() => {
    return {
      total: cases.length,

      awaiting: cases.filter(
        (clinicalCase) =>
          clinicalCase.status ===
          "awaiting_review",
      ).length,

      urgent: cases.filter(
        (clinicalCase) =>
          clinicalCase.priority === "urgent" &&
          clinicalCase.status !== "completed",
      ).length,

      completed: cases.filter(
        (clinicalCase) =>
          clinicalCase.status === "completed",
      ).length,
    };
  }, [cases]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <span>CL</span>
          </div>

          <div>
            <strong>CaseLens</strong>
            <small>Clinical review</small>
          </div>
        </div>

        <nav
          className="primary-navigation"
          aria-label="Primary navigation"
        >
          <p className="navigation-label">
            Workspace
          </p>

          <button
            className="navigation-item active"
            type="button"
          >
            <span className="navigation-index">
              01
            </span>
            Case worklist
          </button>

          <button
            className="navigation-item"
            type="button"
            disabled
          >
            <span className="navigation-index">
              02
            </span>
            AI review
            <span className="coming-soon">
              Soon
            </span>
          </button>

          <button
            className="navigation-item"
            type="button"
            disabled
          >
            <span className="navigation-index">
              03
            </span>
            Audit trail
            <span className="coming-soon">
              Soon
            </span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="environment-card">
            <span
              className={
                readiness
                  ? "status-indicator online"
                  : "status-indicator"
              }
            />

            <div>
              <strong>
                {readiness
                  ? "System operational"
                  : "System unavailable"}
              </strong>

              <small>
                Development environment
              </small>
            </div>
          </div>

          <p>
            Synthetic clinical data only
          </p>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">
              Review operations
            </p>

            <h1>Case worklist</h1>

            <p className="page-description">
              Prioritize, inspect, and advance
              evidence-grounded clinical reviews.
            </p>
          </div>

          <div className="topbar-actions">
            <div
              className={
                readiness
                  ? "api-status healthy"
                  : "api-status"
              }
            >
              <span />

              {readiness
                ? "API and database ready"
                : "Service unavailable"}
            </div>

            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                void loadDashboard();
              }}
              disabled={loading}
            >
              <span aria-hidden="true">
                ↻
              </span>

              {loading
                ? "Refreshing"
                : "Refresh"}
            </button>
          </div>
        </header>

        <section
          className="metrics-grid"
          aria-label="Case metrics"
        >
          <article className="metric-card">
            <div className="metric-heading">
              <span>Total cases</span>
              <span className="metric-code">
                ALL
              </span>
            </div>

            <strong>{metrics.total}</strong>
            <p>Cases currently in CaseLens</p>
          </article>

          <article className="metric-card review">
            <div className="metric-heading">
              <span>Awaiting review</span>
              <span className="metric-code">
                HITL
              </span>
            </div>

            <strong>{metrics.awaiting}</strong>
            <p>Ready for reviewer action</p>
          </article>

          <article className="metric-card urgent">
            <div className="metric-heading">
              <span>Urgent queue</span>
              <span className="metric-code">
                P1
              </span>
            </div>

            <strong>{metrics.urgent}</strong>
            <p>Open urgent-priority cases</p>
          </article>

          <article className="metric-card completed">
            <div className="metric-heading">
              <span>Completed</span>
              <span className="metric-code">
                DONE
              </span>
            </div>

            <strong>{metrics.completed}</strong>
            <p>Reviews completed to date</p>
          </article>
        </section>

        <section className="worklist-card">
          <div className="worklist-header">
            <div>
              <h2>Clinical cases</h2>
              <p>
                {filteredCases.length} of{" "}
                {cases.length} cases shown
              </p>
            </div>

            <div className="worklist-controls">
              <label className="search-control">
                <span aria-hidden="true">⌕</span>

                <input
                  type="search"
                  value={searchQuery}
                  onChange={(event) => {
                    setSearchQuery(
                      event.target.value,
                    );
                  }}
                  placeholder="Search cases"
                  aria-label="Search cases"
                />
              </label>

              <label className="filter-control">
                <span>Status</span>

                <select
                  value={statusFilter}
                  onChange={(event) => {
                    setStatusFilter(
                      event.target
                        .value as StatusFilter,
                    );
                  }}
                >
                  <option value="all">
                    All statuses
                  </option>
                  <option value="received">
                    Received
                  </option>
                  <option value="processing">
                    Processing
                  </option>
                  <option value="awaiting_review">
                    Awaiting review
                  </option>
                  <option value="completed">
                    Completed
                  </option>
                  <option value="failed">
                    Failed
                  </option>
                </select>
              </label>
            </div>
          </div>

          {error ? (
            <div className="error-state">
              <div>
                <strong>
                  Unable to load cases
                </strong>
                <p>{error}</p>
              </div>

              <button
                type="button"
                onClick={() => {
                  void loadDashboard();
                }}
              >
                Try again
              </button>
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Patient reference</th>
                    <th>Requested service</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>
                      <span className="sr-only">
                        Actions
                      </span>
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {loading
                    ? Array.from({
                        length: 5,
                      }).map((_, index) => (
                        <tr
                          className="skeleton-row"
                          key={index}
                        >
                          <td colSpan={6}>
                            <span />
                          </td>
                        </tr>
                      ))
                    : filteredCases.map(
                        (clinicalCase) => (
                          <tr
                            key={clinicalCase.id}
                            onClick={() => {
                              setSelectedCase(
                                clinicalCase,
                              );
                            }}
                          >
                            <td>
                              <div className="patient-cell">
                                <span className="patient-avatar">
                                  {clinicalCase
                                    .patient_external_id[0]
                                    ?.toUpperCase() ??
                                    "C"}
                                </span>

                                <div>
                                  <strong>
                                    {
                                      clinicalCase.patient_external_id
                                    }
                                  </strong>

                                  <small>
                                    {clinicalCase.id.slice(
                                      0,
                                      8,
                                    )}
                                  </small>
                                </div>
                              </div>
                            </td>

                            <td>
                              {
                                clinicalCase.requested_service
                              }
                            </td>

                            <td>
                              <span
                                className={`priority-badge ${clinicalCase.priority}`}
                              >
                                {
                                  clinicalCase.priority
                                }
                              </span>
                            </td>

                            <td>
                              <span
                                className={`status-badge ${clinicalCase.status}`}
                              >
                                {
                                  STATUS_LABELS[
                                    clinicalCase
                                      .status
                                  ]
                                }
                              </span>
                            </td>

                            <td className="date-cell">
                              {formatDate(
                                clinicalCase.created_at,
                              )}
                            </td>

                            <td>
                              <button
                                className="row-action"
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedCase(
                                    clinicalCase,
                                  );
                                }}
                              >
                                View
                              </button>
                            </td>
                          </tr>
                        ),
                      )}
                </tbody>
              </table>

              {!loading &&
                filteredCases.length === 0 && (
                  <div className="empty-state">
                    <span>0</span>
                    <strong>
                      No matching cases
                    </strong>
                    <p>
                      Try changing the search or
                      status filter.
                    </p>
                  </div>
                )}
            </div>
          )}
        </section>
      </main>

      {selectedCase && (
        <div
          className="drawer-backdrop"
          role="presentation"
          onMouseDown={() => {
            setSelectedCase(null);
          }}
        >
          <aside
            className="case-drawer"
            aria-label="Case details"
            onMouseDown={(event) => {
              event.stopPropagation();
            }}
          >
            <div className="drawer-header">
              <div>
                <p className="eyebrow">
                  Case overview
                </p>

                <h2>
                  {
                    selectedCase.patient_external_id
                  }
                </h2>
              </div>

              <button
                className="close-button"
                type="button"
                onClick={() => {
                  setSelectedCase(null);
                }}
                aria-label="Close case details"
              >
                ×
              </button>
            </div>

            <div className="drawer-status-row">
              <span
                className={`status-badge ${selectedCase.status}`}
              >
                {
                  STATUS_LABELS[
                    selectedCase.status
                  ]
                }
              </span>

              <span
                className={`priority-badge ${selectedCase.priority}`}
              >
                {selectedCase.priority}
              </span>
            </div>

            <dl className="case-details">
              <div>
                <dt>Requested service</dt>
                <dd>
                  {
                    selectedCase.requested_service
                  }
                </dd>
              </div>

              <div>
                <dt>Created</dt>
                <dd>
                  {formatDate(
                    selectedCase.created_at,
                  )}
                </dd>
              </div>

              <div>
                <dt>Case identifier</dt>
                <dd className="monospace">
                  {selectedCase.id}
                </dd>
              </div>
            </dl>

            <div className="drawer-callout">
              <span>Next</span>

              <div>
                <strong>
                  Reviewer workspace
                </strong>
                <p>
                  Documents, AI findings,
                  citations, and human decisions
                  will appear here next.
                </p>
              </div>
            </div>

            <button
              className="primary-button"
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(
                  selectedCase.id,
                );
              }}
            >
              Copy case ID
            </button>
          </aside>
        </div>
      )}
    </div>
  );
}

export default App;