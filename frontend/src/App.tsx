import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import {
  deleteClinicalCase,
  getCurrentReviewer,
  getReadiness,
  getSession,
  listCases,
  onSessionExpired,
  signOut,
} from "./api";
import type { ReviewerSession } from "./api";
import { CaseWorkspace } from "./CaseWorkspace";
import { CaseIntake } from "./CaseIntake";
import { SignIn } from "./SignIn";
import { DeleteCaseDialog } from "./components/DeleteCaseDialog";
import { Icon } from "./components/Icon";
import { getErrorMessage } from "./lib/errors";
import { formatDate, formatRelativeDate } from "./lib/format";

import type {
  CaseStatus,
  ClinicalCase,
  ReadinessResponse,
  ReviewerRole,
} from "./types";

import "./App.css";


type StatusFilter = "all" | CaseStatus;
type Theme = "light" | "dark";

const POLL_INTERVAL_MS = 5000;

const ROLE_LABELS: Record<ReviewerRole, string> = {
  reviewer: "Reviewer",
  administrator: "Administrator",
};

const STATUS_LABELS: Record<CaseStatus, string> = {
  received: "Received",
  processing: "Processing",
  awaiting_review: "Awaiting review",
  completed: "Completed",
  failed: "Failed",
};

interface LoadOptions {
  silent?: boolean;
  signal?: AbortSignal;
}

const SKELETON_ROWS = [0, 1, 2, 3, 4];

function SkeletonRow() {
  return (
    <tr className="skeleton-row" aria-hidden="true">
      <td>
        <div className="patient-cell">
          <span className="skeleton skeleton-avatar" />
          <div className="skeleton-lines">
            <span className="skeleton" style={{ width: "72%" }} />
            <span className="skeleton" style={{ width: "48%" }} />
          </div>
        </div>
      </td>
      <td>
        <span className="skeleton" style={{ width: "62%" }} />
      </td>
      <td className="col-priority">
        <span className="skeleton skeleton-pill" />
      </td>
      <td>
        <span className="skeleton skeleton-pill" style={{ width: 96 }} />
      </td>
      <td className="col-created">
        <span className="skeleton" style={{ width: "56%" }} />
      </td>
      <td>
        <span className="skeleton" style={{ width: 42 }} />
      </td>
    </tr>
  );
}

function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);

  if (parts.length === 0) {
    return "?";
  }

  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";

  return `${first}${last}`.toUpperCase();
}

function App() {
  const [session, setActiveSession] = useState<ReviewerSession | null>(() =>
    getSession(),
  );
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  const [cases, setCases] = useState<ClinicalCase[]>([]);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [selectedSnapshot, setSelectedSnapshot] =
    useState<ClinicalCase | null>(null);
  const [showCaseIntake, setShowCaseIntake] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [urgentOnly, setUrgentOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedCaseId, setCopiedCaseId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ClinicalCase | null>(
    null,
  );
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  const copyResetRef = useRef<number | undefined>(undefined);

  const loadDashboard = useCallback(async (options?: LoadOptions) => {
    // Case data is unreadable without a token, so a signed-out app
    // waits at the sign-in screen instead of polling for 401s.
    if (!session) {
      return;
    }

    const [casesResult, readinessResult] = await Promise.allSettled([
      listCases({ signal: options?.signal }),
      getReadiness({ signal: options?.signal }),
    ]);

    if (options?.signal?.aborted) {
      return;
    }

    if (casesResult.status === "fulfilled") {
      setCases(casesResult.value);
      setError(null);
    } else if (!options?.silent) {
      setError(getErrorMessage(casesResult.reason));
    }

    setReadiness(
      readinessResult.status === "fulfilled" ? readinessResult.value : null,
    );
    setInitialLoading(false);
  }, [session]);

  // Any request the API rejects returns the reviewer to sign-in.
  useEffect(() => {
    onSessionExpired(() => {
      setActiveSession(null);
      setSelectedSnapshot(null);
      setCases([]);
      setInitialLoading(true);
      setSessionNotice("Your session ended. Sign in again to continue.");
    });

    return () => {
      onSessionExpired(null);
    };
  }, []);

  // A token restored from a previous visit may already have expired.
  // One identity call settles it before the worklist renders.
  useEffect(() => {
    if (!session) {
      return;
    }

    const controller = new AbortController();

    void getCurrentReviewer({ signal: controller.signal }).catch(() => {
      // A rejected token is cleared by the expiry handler above.
    });

    return () => {
      controller.abort();
    };
  }, [session]);

  const handleManualRefresh = useCallback(() => {
    setRefreshing(true);

    void loadDashboard().finally(() => {
      setRefreshing(false);
    });
  }, [loadDashboard]);

  useEffect(() => {
    const controller = new AbortController();
    // False positive: every setState inside loadDashboard runs after the
    // fetch resolves, never synchronously within this effect.
    // eslint-disable-next-line react/set-state-in-effect
    void loadDashboard({ signal: controller.signal });

    return () => {
      controller.abort();
    };
  }, [loadDashboard]);

  // Silent background polling keeps case statuses and the readiness
  // indicator live while Temporal advances work server-side.
  useEffect(() => {
    let cancelled = false;
    let running = false;
    let timeoutId: number | undefined;

    function schedule() {
      if (!cancelled) {
        timeoutId = window.setTimeout(() => {
          void tick();
        }, POLL_INTERVAL_MS);
      }
    }

    async function tick() {
      if (cancelled || running) {
        return;
      }

      running = true;

      if (document.visibilityState === "visible") {
        await loadDashboard({ silent: true });
      }

      running = false;
      schedule();
    }

    function handleVisibility() {
      if (document.visibilityState === "visible") {
        window.clearTimeout(timeoutId);
        void tick();
      }
    }

    schedule();
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [loadDashboard]);

  const handleCaseChanged = useCallback(() => {
    void loadDashboard({ silent: true });
  }, [loadDashboard]);

  // The workspace always renders the freshest version of the selected
  // case; the snapshot is only a fallback while the list refreshes.
  const selectedCase = useMemo(() => {
    if (!selectedSnapshot) {
      return null;
    }

    return (
      cases.find((clinicalCase) => clinicalCase.id === selectedSnapshot.id) ??
      selectedSnapshot
    );
  }, [cases, selectedSnapshot]);

  const filteredCases = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    return cases.filter((clinicalCase) => {
      const matchesStatus =
        statusFilter === "all" || clinicalCase.status === statusFilter;

      const matchesPriority =
        !urgentOnly || clinicalCase.priority === "urgent";

      const matchesSearch =
        !query ||
        clinicalCase.patient_external_id.toLowerCase().includes(query) ||
        clinicalCase.requested_service.toLowerCase().includes(query) ||
        clinicalCase.id.toLowerCase().includes(query);

      return matchesStatus && matchesPriority && matchesSearch;
    });
  }, [cases, searchQuery, statusFilter, urgentOnly]);

  const metrics = useMemo(() => {
    return {
      total: cases.length,

      awaiting: cases.filter(
        (clinicalCase) => clinicalCase.status === "awaiting_review",
      ).length,

      urgent: cases.filter(
        (clinicalCase) =>
          clinicalCase.priority === "urgent" &&
          clinicalCase.status !== "completed",
      ).length,

      completed: cases.filter(
        (clinicalCase) => clinicalCase.status === "completed",
      ).length,
    };
  }, [cases]);

  const filtersActive =
    statusFilter !== "all" || urgentOnly || searchQuery.trim() !== "";

  function clearFilters() {
    setStatusFilter("all");
    setUrgentOnly(false);
    setSearchQuery("");
  }

  function toggleStatusFilter(status: CaseStatus) {
    setStatusFilter((current) => (current === status ? "all" : status));
  }

  function handleSignOut() {
    signOut();
    setActiveSession(null);
    setSelectedSnapshot(null);
    setCases([]);
    setInitialLoading(true);
    setSessionNotice(null);
  }

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;

    try {
      window.localStorage.setItem("caselens-theme", next);
    } catch {
      // Persisting the preference is best-effort.
    }
  }

  function copyCaseId(caseId: string) {
    void navigator.clipboard
      .writeText(caseId)
      .then(() => {
        setCopiedCaseId(caseId);
        window.clearTimeout(copyResetRef.current);
        copyResetRef.current = window.setTimeout(() => {
          setCopiedCaseId((current) => (current === caseId ? null : current));
        }, 1600);
      })
      .catch(() => {
        // Clipboard access can be denied; ignore silently.
      });
  }

  function handleDeleteConfirmed() {
    if (!pendingDelete) {
      return;
    }

    const caseId = pendingDelete.id;

    setDeleting(true);
    setDeleteError(null);

    deleteClinicalCase(caseId)
      .then(() => {
        setDeleting(false);
        setPendingDelete(null);
        setSelectedSnapshot((current) =>
          current?.id === caseId ? null : current,
        );
        void loadDashboard({ silent: true });
      })
      .catch((error: unknown) => {
        setDeleting(false);
        setDeleteError(getErrorMessage(error));
      });
  }

  function handleRowKeyDown(
    event: KeyboardEvent<HTMLTableRowElement>,
    clinicalCase: ClinicalCase,
  ) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setSelectedSnapshot(clinicalCase);
    }
  }

  const showEmptyState = !initialLoading && filteredCases.length === 0;
  const showErrorState = error !== null && cases.length === 0 && !initialLoading;

  if (!session) {
    return (
      <SignIn
        notice={sessionNotice}
        onSignedIn={(nextSession) => {
          setSessionNotice(null);
          setInitialLoading(true);
          setActiveSession(nextSession);
        }}
      />
    );
  }

  // The API enforces this too; hiding the control keeps reviewers from
  // reaching for an action that would come back as 403.
  const canDeleteCases = session.reviewer.role === "administrator";

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

        <nav className="primary-navigation" aria-label="Primary navigation">
          <p className="navigation-label">Workspace</p>

          <button className="navigation-item active" type="button">
            <span className="navigation-index">01</span>
            Case worklist
          </button>

          <button className="navigation-item" type="button" disabled>
            <span className="navigation-index">02</span>
            AI review
            <span className="coming-soon">Soon</span>
          </button>

          <button className="navigation-item" type="button" disabled>
            <span className="navigation-index">03</span>
            Audit trail
            <span className="coming-soon">Soon</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="account-card">
            <span className="account-avatar" aria-hidden="true">
              {initials(session.reviewer.full_name)}
            </span>

            <div className="account-identity">
              <strong>{session.reviewer.full_name}</strong>
              <small>{ROLE_LABELS[session.reviewer.role]}</small>
            </div>

            <button
              className="account-signout"
              type="button"
              onClick={handleSignOut}
              aria-label="Sign out"
              title="Sign out"
            >
              <Icon name="sign-out" size={14} />
            </button>
          </div>

          <div className="environment-card">
            <span
              className={
                readiness ? "status-indicator online" : "status-indicator"
              }
            />

            <div>
              <strong>
                {readiness ? "System operational" : "System unavailable"}
              </strong>

              <small>Development environment</small>
            </div>
          </div>

          <p>Synthetic clinical data only</p>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Review operations</p>

            <h1>Case worklist</h1>

            <p className="page-description">
              Prioritize, inspect, and advance evidence-grounded clinical
              reviews.
            </p>
          </div>

          <div className="topbar-actions">
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => {
                setShowCaseIntake(true);
              }}
            >
              <Icon name="plus" size={15} />
              New case
            </button>

            <div className={readiness ? "api-status healthy" : "api-status"}>
              <span />
              {readiness ? "API and database ready" : "Service unavailable"}
            </div>

            <button
              className="btn btn-secondary"
              type="button"
              onClick={handleManualRefresh}
              disabled={refreshing}
            >
              <Icon
                name="refresh"
                size={14}
                className={refreshing ? "spin" : undefined}
              />
              {refreshing ? "Refreshing" : "Refresh"}
            </button>

            <button
              className="btn btn-secondary btn-icon"
              type="button"
              onClick={toggleTheme}
              aria-label={
                theme === "dark"
                  ? "Switch to light theme"
                  : "Switch to dark theme"
              }
              title={
                theme === "dark"
                  ? "Switch to light theme"
                  : "Switch to dark theme"
              }
            >
              <Icon name={theme === "dark" ? "sun" : "moon"} size={15} />
            </button>
          </div>
        </header>

        <section className="metrics-grid" aria-label="Case metrics">
          <button
            className="metric-card"
            type="button"
            onClick={clearFilters}
            title="Show all cases"
          >
            <div className="metric-heading">
              <span>Total cases</span>
              <span className="metric-code">ALL</span>
            </div>

            <strong>{metrics.total}</strong>
            <p>Cases currently in CaseLens</p>
          </button>

          <button
            className={`metric-card review${
              statusFilter === "awaiting_review" ? " selected" : ""
            }`}
            type="button"
            aria-pressed={statusFilter === "awaiting_review"}
            onClick={() => {
              toggleStatusFilter("awaiting_review");
            }}
            title="Filter cases awaiting review"
          >
            <div className="metric-heading">
              <span>Awaiting review</span>
              <span className="metric-code">HITL</span>
            </div>

            <strong>{metrics.awaiting}</strong>
            <p>Ready for reviewer action</p>
          </button>

          <button
            className={`metric-card urgent${urgentOnly ? " selected" : ""}`}
            type="button"
            aria-pressed={urgentOnly}
            onClick={() => {
              setUrgentOnly((current) => !current);
            }}
            title="Filter urgent-priority cases"
          >
            <div className="metric-heading">
              <span>Urgent queue</span>
              <span className="metric-code">P1</span>
            </div>

            <strong>{metrics.urgent}</strong>
            <p>Open urgent-priority cases</p>
          </button>

          <button
            className={`metric-card completed${
              statusFilter === "completed" ? " selected" : ""
            }`}
            type="button"
            aria-pressed={statusFilter === "completed"}
            onClick={() => {
              toggleStatusFilter("completed");
            }}
            title="Filter completed cases"
          >
            <div className="metric-heading">
              <span>Completed</span>
              <span className="metric-code">DONE</span>
            </div>

            <strong>{metrics.completed}</strong>
            <p>Reviews completed to date</p>
          </button>
        </section>

        {error && cases.length > 0 && (
          <div className="inline-banner error" role="alert">
            <Icon name="alert" size={15} />

            <p>{error}</p>

            <button
              type="button"
              onClick={() => {
                setError(null);
              }}
            >
              Dismiss
            </button>
          </div>
        )}

        <section className="worklist-card">
          <div className="worklist-header">
            <div>
              <h2>Clinical cases</h2>
              <p>
                {filteredCases.length} of {cases.length} cases shown
              </p>
            </div>

            <div className="worklist-controls">
              <label className="search-control">
                <Icon name="search" size={14} />

                <input
                  type="search"
                  value={searchQuery}
                  onChange={(event) => {
                    setSearchQuery(event.target.value);
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
                    setStatusFilter(event.target.value as StatusFilter);
                  }}
                >
                  <option value="all">All statuses</option>
                  <option value="received">Received</option>
                  <option value="processing">Processing</option>
                  <option value="awaiting_review">Awaiting review</option>
                  <option value="completed">Completed</option>
                  <option value="failed">Failed</option>
                </select>
              </label>
            </div>
          </div>

          {showErrorState ? (
            <div className="error-state">
              <div>
                <strong>Unable to load cases</strong>
                <p>{error}</p>
              </div>

              <button type="button" onClick={handleManualRefresh}>
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
                    <th className="col-priority">Priority</th>
                    <th>Status</th>
                    <th className="col-created">Created</th>
                    <th>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {initialLoading
                    ? SKELETON_ROWS.map((index) => <SkeletonRow key={index} />)
                    : filteredCases.map((clinicalCase) => (
                        <tr
                          key={clinicalCase.id}
                          tabIndex={0}
                          onClick={() => {
                            setSelectedSnapshot(clinicalCase);
                          }}
                          onKeyDown={(event) => {
                            handleRowKeyDown(event, clinicalCase);
                          }}
                        >
                          <td>
                            <div className="patient-cell">
                              <span className="patient-avatar">
                                {clinicalCase.patient_external_id[0]?.toUpperCase() ??
                                  "C"}
                              </span>

                              <div>
                                <strong>
                                  {clinicalCase.patient_external_id}
                                </strong>

                                <button
                                  className="case-id-copy"
                                  type="button"
                                  title={`Copy case ID ${clinicalCase.id}`}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    copyCaseId(clinicalCase.id);
                                  }}
                                >
                                  {copiedCaseId === clinicalCase.id
                                    ? "Copied"
                                    : clinicalCase.id.slice(0, 8)}
                                  <Icon name="copy" size={11} />
                                </button>
                              </div>
                            </div>
                          </td>

                          <td>{clinicalCase.requested_service}</td>

                          <td className="col-priority">
                            <span
                              className={`priority-badge ${clinicalCase.priority}`}
                            >
                              {clinicalCase.priority}
                            </span>
                          </td>

                          <td>
                            <span
                              className={`status-badge ${clinicalCase.status}`}
                            >
                              {STATUS_LABELS[clinicalCase.status]}
                            </span>
                          </td>

                          <td
                            className="date-cell col-created"
                            title={formatDate(clinicalCase.created_at)}
                          >
                            {formatRelativeDate(clinicalCase.created_at)}
                          </td>

                          <td>
                            <div className="row-actions">
                              <button
                                className="row-action"
                                type="button"
                                tabIndex={-1}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedSnapshot(clinicalCase);
                                }}
                              >
                                View
                              </button>

                              {canDeleteCases && (
                                <button
                                  className="row-action danger"
                                  type="button"
                                  aria-label={`Delete case ${clinicalCase.patient_external_id}`}
                                  title="Delete case"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    setDeleteError(null);
                                    setPendingDelete(clinicalCase);
                                  }}
                                >
                                  <Icon name="trash" size={13} />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                </tbody>
              </table>

              {showEmptyState &&
                (cases.length === 0 ? (
                  <div className="empty-state">
                    <span>
                      <Icon name="inbox" size={20} />
                    </span>
                    <strong>No cases yet</strong>
                    <p>
                      Create your first synthetic case to start an
                      evidence-grounded review.
                    </p>

                    <button
                      className="btn btn-primary"
                      type="button"
                      onClick={() => {
                        setShowCaseIntake(true);
                      }}
                    >
                      <Icon name="plus" size={15} />
                      Create your first case
                    </button>
                  </div>
                ) : (
                  <div className="empty-state">
                    <span>
                      <Icon name="search" size={20} />
                    </span>
                    <strong>No matching cases</strong>
                    <p>Try changing the search or status filter.</p>

                    {filtersActive && (
                      <button
                        className="btn btn-secondary"
                        type="button"
                        onClick={clearFilters}
                      >
                        Clear filters
                      </button>
                    )}
                  </div>
                ))}
            </div>
          )}
        </section>

        <footer className="credits-mark" aria-label="Credits">
          <span className="credits-mark-symbol">CL</span>
          <span>CaseLens by Oussama Kinani</span>
        </footer>
      </main>

      {selectedCase && (
        <CaseWorkspace
          key={selectedCase.id}
          clinicalCase={selectedCase}
          onClose={() => {
            setSelectedSnapshot(null);
          }}
          onCaseChanged={handleCaseChanged}
        />
      )}

      {pendingDelete && (
        <DeleteCaseDialog
          clinicalCase={pendingDelete}
          deleting={deleting}
          error={deleteError}
          onConfirm={handleDeleteConfirmed}
          onClose={() => {
            setPendingDelete(null);
            setDeleteError(null);
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
            setSelectedSnapshot(clinicalCase);
            void loadDashboard({ silent: true });
          }}
        />
      )}
    </div>
  );
}

export default App;
