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
import {
  CaseWorkspace,
} from "./CaseWorkspace";
import {
  CaseIntake,
} from "./CaseIntake";

import type {
  CaseStatus,
  ClinicalCase,
  ReadinessResponse,
} from "./types";

import "./App.css";


type StatusFilter = "all" | CaseStatus;
type PriorityFilter = "all" | "routine" | "urgent";

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
  const [
    showCaseIntake,
    setShowCaseIntake,
  ] = useState(false);
  const [statusFilter, setStatusFilter] =
    useState<StatusFilter>("all");
  const [priorityFilter, setPriorityFilter] =
    useState<PriorityFilter>("all");
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
    let cancelled = false;

    void Promise.allSettled([
      listCases(),
      getReadiness(),
    ]).then(
      ([
        casesResult,
        readinessResult,
      ]) => {
        if (cancelled) {
          return;
        }

        if (casesResult.status === "fulfilled") {
          setCases(casesResult.value);
        } else {
          setError(
            getErrorMessage(
              casesResult.reason,
            ),
          );
        }

        if (
          readinessResult.status ===
          "fulfilled"
        ) {
          setReadiness(
            readinessResult.value,
          );
        } else {
          setReadiness(null);
        }

        setLoading(false);
      },
    );

    return () => {
      cancelled = true;
    };
  }, []);

  const filteredCases = useMemo(() => {
    const query = searchQuery
      .trim()
      .toLowerCase();

    return cases.filter((clinicalCase) => {
      const matchesStatus =
        statusFilter === "all" ||
        clinicalCase.status === statusFilter;

      const matchesPriority =
        priorityFilter === "all" ||
        clinicalCase.priority === priorityFilter;

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

      return (
        matchesStatus &&
        matchesPriority &&
        matchesSearch
      );
    });
  }, [
    cases,
    priorityFilter,
    searchQuery,
    statusFilter,
  ]);

  const hasActiveFilters =
    statusFilter !== "all" ||
    priorityFilter !== "all" ||
    searchQuery.trim().length > 0;

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
          <img
            className="brand-mark"
            src="/caselens-mark.svg"
            alt=""
          />

          <div>
            <strong>CaseLens</strong>
            <small>Evidence review</small>
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
            className={
              statusFilter === "all" &&
              priorityFilter === "all"
                ? "navigation-item active"
                : "navigation-item"
            }
            type="button"
            onClick={() => {
              setStatusFilter("all");
              setPriorityFilter("all");
            }}
          >
            <span className="navigation-icon">WL</span>
            All cases
            <span className="navigation-count">
              {metrics.total}
            </span>
          </button>

          <button
            className={
              statusFilter === "awaiting_review"
                ? "navigation-item active"
                : "navigation-item"
            }
            type="button"
            onClick={() => {
              setStatusFilter("awaiting_review");
              setPriorityFilter("all");
            }}
          >
            <span className="navigation-icon">HR</span>
            Needs review
            <span className="navigation-count attention">
              {metrics.awaiting}
            </span>
          </button>

          <button
            className={
              priorityFilter === "urgent"
                ? "navigation-item active"
                : "navigation-item"
            }
            type="button"
            onClick={() => {
              setStatusFilter("all");
              setPriorityFilter("urgent");
            }}
          >
            <span className="navigation-icon">P1</span>
            Urgent queue
            <span className="navigation-count urgent">
              {metrics.urgent}
            </span>
          </button>
        </nav>

        <div className="guardrail-card">
          <span className="guardrail-kicker">
            Review guardrails
          </span>
          <strong>Evidence before inference.</strong>
          <p>
            Every AI claim remains source-linked and
            every final decision stays human-owned.
          </p>
          <div className="guardrail-points">
            <span>Exact citations</span>
            <span>Immutable audit</span>
          </div>
        </div>

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
            <p className="eyebrow">Review operations</p>

            <h1>
              Evidence review,
              <span> built for human judgment.</span>
            </h1>

            <p className="page-description">
              Triage incoming cases, inspect source-linked
              AI findings, and record a defensible decision.
            </p>
          </div>

          <div className="topbar-actions">
            <button
              className="new-case-button"
              type="button"
              onClick={() => {
                setShowCaseIntake(true);
              }}
            >
              <span aria-hidden="true">+</span>
              New case
            </button>
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
          <button
            className={
              statusFilter === "all" &&
              priorityFilter === "all"
                ? "metric-card active"
                : "metric-card"
            }
            type="button"
            onClick={() => {
              setStatusFilter("all");
              setPriorityFilter("all");
            }}
          >
            <div className="metric-heading">
              <span>Total cases</span>
              <span className="metric-code">
                ALL
              </span>
            </div>

            <strong>{metrics.total}</strong>
            <p>Cases currently in CaseLens</p>
            <span className="metric-action">View all</span>
          </button>

          <button
            className={
              statusFilter === "awaiting_review"
                ? "metric-card review active"
                : "metric-card review"
            }
            type="button"
            onClick={() => {
              setStatusFilter("awaiting_review");
              setPriorityFilter("all");
            }}
          >
            <div className="metric-heading">
              <span>Awaiting review</span>
              <span className="metric-code">
                HITL
              </span>
            </div>

            <strong>{metrics.awaiting}</strong>
            <p>Ready for reviewer action</p>
            <span className="metric-action">Open queue</span>
          </button>

          <button
            className={
              priorityFilter === "urgent"
                ? "metric-card urgent active"
                : "metric-card urgent"
            }
            type="button"
            onClick={() => {
              setStatusFilter("all");
              setPriorityFilter("urgent");
            }}
          >
            <div className="metric-heading">
              <span>Urgent queue</span>
              <span className="metric-code">
                P1
              </span>
            </div>

            <strong>{metrics.urgent}</strong>
            <p>Open urgent-priority cases</p>
            <span className="metric-action">Prioritize</span>
          </button>

          <button
            className={
              statusFilter === "completed"
                ? "metric-card completed active"
                : "metric-card completed"
            }
            type="button"
            onClick={() => {
              setStatusFilter("completed");
              setPriorityFilter("all");
            }}
          >
            <div className="metric-heading">
              <span>Completed</span>
              <span className="metric-code">
                DONE
              </span>
            </div>

            <strong>{metrics.completed}</strong>
            <p>Reviews completed to date</p>
            <span className="metric-action">Review history</span>
          </button>
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

              <label className="filter-control">
                <span>Priority</span>

                <select
                  value={priorityFilter}
                  onChange={(event) => {
                    setPriorityFilter(
                      event.target
                        .value as PriorityFilter,
                    );
                  }}
                >
                  <option value="all">
                    All priorities
                  </option>
                  <option value="urgent">Urgent</option>
                  <option value="routine">Routine</option>
                </select>
              </label>

              {hasActiveFilters && (
                <button
                  className="clear-filters"
                  type="button"
                  onClick={() => {
                    setSearchQuery("");
                    setStatusFilter("all");
                    setPriorityFilter("all");
                  }}
                >
                  Clear
                </button>
              )}
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
                            tabIndex={0}
                            onClick={() => {
                              setSelectedCase(
                                clinicalCase,
                              );
                            }}
                            onKeyDown={(event) => {
                              if (
                                event.key === "Enter" ||
                                event.key === " "
                              ) {
                                event.preventDefault();
                                setSelectedCase(
                                  clinicalCase,
                                );
                              }
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
                                Open
                                <span aria-hidden="true">
                                  {"\u2192"}
                                </span>
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
                    <span aria-hidden="true">0</span>
                    <strong>
                      {cases.length === 0
                        ? "Your worklist is clear"
                        : "No matching cases"}
                    </strong>
                    <p>
                      {cases.length === 0
                        ? "Create a synthetic case to begin an evidence-grounded review."
                        : "Try changing the search, status, or priority filter."}
                    </p>
                    {cases.length === 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          setShowCaseIntake(true);
                        }}
                      >
                        Create first case
                      </button>
                    )}
                  </div>
                )}
            </div>
          )}
        </section>
      </main>

      {selectedCase && (
        <CaseWorkspace
          clinicalCase={selectedCase}
          onClose={() => {
            setSelectedCase(null);
          }}
          onCaseChanged={() => {
            void loadDashboard();
          }}
        />
      )}
      {showCaseIntake && (
        <CaseIntake
          onClose={() => {
            setShowCaseIntake(false);
          }}
          onCreated={(clinicalCase) => {
            setShowCaseIntake(false);
            setSelectedCase(clinicalCase);
            void loadDashboard();
          }}
        />
      )}
    </div>
  );
}

export default App;
