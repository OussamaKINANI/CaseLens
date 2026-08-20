import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  answerCaseQuestion,
  createCaseReviewRun,
  listCaseAuditEvents,
  listCaseDocuments,
  listCaseExtractions,
  listCaseReviewRuns,
  startCaseReviewRun,
  submitHumanReview,
} from "./api";

import type {
  AuditEvent,
  CaseAnswerResponse,
  CaseReviewRun,
  ClinicalCase,
  ClinicalDocument,
  ClinicalExtraction,
} from "./types";


type WorkspaceTab =
  | "findings"
  | "documents"
  | "audit";

interface CaseWorkspaceProps {
  clinicalCase: ClinicalCase;
  onClose: () => void;
  onCaseChanged: () => void;
}

interface WorkspaceData {
  documents: ClinicalDocument[];
  extractions: ClinicalExtraction[];
  auditEvents: AuditEvent[];
  reviewRuns: CaseReviewRun[];
}

const REVIEW_STATUS_LABELS: Record<
  CaseReviewRun["status"],
  string
> = {
  queued: "Queued",
  running: "AI processing",
  awaiting_human_review: "Awaiting human review",
  completed: "Approved",
  rejected: "Rejected",
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

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }

  return `${(value / 1024).toFixed(1)} KB`;
}

function humanize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) =>
      character.toUpperCase(),
    );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred.";
}

async function fetchWorkspaceData(
  caseId: string,
): Promise<WorkspaceData> {
  const [
    documents,
    extractions,
    auditEvents,
    reviewRuns,
  ] = await Promise.all([
    listCaseDocuments(caseId),
    listCaseExtractions(caseId),
    listCaseAuditEvents(caseId),
    listCaseReviewRuns(caseId),
  ]);

  return {
    documents,
    extractions,
    auditEvents,
    reviewRuns,
  };
}

export function CaseWorkspace({
  clinicalCase,
  onClose,
  onCaseChanged,
}: CaseWorkspaceProps) {
  const [activeTab, setActiveTab] =
    useState<WorkspaceTab>("findings");
  const [documents, setDocuments] =
    useState<ClinicalDocument[]>([]);
  const [extractions, setExtractions] =
    useState<ClinicalExtraction[]>([]);
  const [auditEvents, setAuditEvents] =
    useState<AuditEvent[]>([]);
  const [reviewRuns, setReviewRuns] =
    useState<CaseReviewRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] =
    useState(false);
  const [error, setError] =
    useState<string | null>(null);
  const [notice, setNotice] =
    useState<string | null>(null);
  const [reviewNotes, setReviewNotes] =
    useState("");
  const [question, setQuestion] =
    useState(
      "What clinically relevant treatment was attempted?",
    );
  const [answerResult, setAnswerResult] =
    useState<CaseAnswerResponse | null>(null);
  const [askingQuestion, setAskingQuestion] =
    useState(false);

  useEffect(() => {
    const previousOverflow =
      document.body.style.overflow;

    document.body.style.overflow = "hidden";

    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener(
        "keydown",
        handleKeyDown,
      );
    };
  }, [onClose]);

  const applyWorkspaceData = useCallback(
    (data: WorkspaceData) => {
      setDocuments(data.documents);
      setExtractions(data.extractions);
      setAuditEvents(data.auditEvents);
      setReviewRuns(data.reviewRuns);
    },
    [],
  );

  const refreshWorkspace = useCallback(
    async () => {
      setLoading(true);
      setError(null);

      try {
        const data = await fetchWorkspaceData(
          clinicalCase.id,
        );

        applyWorkspaceData(data);
      } catch (refreshError) {
        setError(
          getErrorMessage(refreshError),
        );
      } finally {
        setLoading(false);
      }
    },
    [
      applyWorkspaceData,
      clinicalCase.id,
    ],
  );

  useEffect(() => {
    let cancelled = false;

    void fetchWorkspaceData(
      clinicalCase.id,
    )
      .then((data) => {
        if (cancelled) {
          return;
        }

        applyWorkspaceData(data);
        setLoading(false);
      })
      .catch((loadError: unknown) => {
        if (cancelled) {
          return;
        }

        setError(
          getErrorMessage(loadError),
        );
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [
    applyWorkspaceData,
    clinicalCase.id,
  ]);

  const latestReviewRun = useMemo(() => {
    return [...reviewRuns].sort(
      (left, right) =>
        new Date(right.created_at).getTime() -
        new Date(left.created_at).getTime(),
    )[0] ?? null;
  }, [reviewRuns]);

  const latestRunIsProcessing =
    latestReviewRun?.status === "queued" ||
    latestReviewRun?.status === "running";

  useEffect(() => {
    if (!latestRunIsProcessing) {
      return;
    }

    let requestInProgress = false;

    async function checkReviewStatus(): Promise<void> {
      if (requestInProgress) {
        return;
      }

      requestInProgress = true;

      try {
        const runs =
          await listCaseReviewRuns(
            clinicalCase.id,
          );

        setReviewRuns(runs);

        const newestRun = [...runs].sort(
          (left, right) =>
            new Date(
              right.created_at,
            ).getTime() -
            new Date(
              left.created_at,
            ).getTime(),
        )[0];

        if (
          newestRun &&
          newestRun.status !== "queued" &&
          newestRun.status !== "running"
        ) {
          const data =
            await fetchWorkspaceData(
              clinicalCase.id,
            );

          applyWorkspaceData(data);
        }
      } catch {
        // Manual refresh remains available.
      } finally {
        requestInProgress = false;
      }
    }

    void checkReviewStatus();

    const intervalId =
      window.setInterval(
        () => {
          void checkReviewStatus();
        },
        3000,
      );

    return () => {
      window.clearInterval(intervalId);
    };
  }, [
    applyWorkspaceData,
    clinicalCase.id,
    latestRunIsProcessing,
  ]);

  const facts = useMemo(() => {
    return extractions.flatMap(
      (extraction) =>
        extraction.result.facts.map(
          (fact) => ({
            ...fact,
            extractionId: extraction.id,
            documentId: extraction.document_id,
          }),
        ),
    );
  }, [extractions]);

  const missingInformation = useMemo(() => {
    return Array.from(
      new Set(
        extractions.flatMap(
          (extraction) =>
            extraction.result
              .missing_information,
        ),
      ),
    );
  }, [extractions]);

  const warnings = useMemo(() => {
    return Array.from(
      new Set(
        extractions.flatMap(
          (extraction) =>
            extraction.result.warnings,
        ),
      ),
    );
  }, [extractions]);

  async function startReview(): Promise<void> {
    if (documents.length === 0) {
      setError(
        "Upload at least one document before starting a review.",
      );
      return;
    }

    setActionBusy(true);
    setError(null);
    setNotice(null);

    try {
      const reviewRun =
        await createCaseReviewRun(
          clinicalCase.id,
          documents.map(
            (document) => document.id,
          ),
        );

      await startCaseReviewRun(
        clinicalCase.id,
        reviewRun.id,
      );

      setNotice(
        "Durable AI review started.",
      );

      await refreshWorkspace();
      onCaseChanged();
    } catch (startError) {
      setError(
        getErrorMessage(startError),
      );
    } finally {
      setActionBusy(false);
    }
  }

  async function submitDecision(
    decision: "approve" | "reject",
  ): Promise<void> {
    if (
      !latestReviewRun ||
      latestReviewRun.status !==
        "awaiting_human_review"
    ) {
      return;
    }

    setActionBusy(true);
    setError(null);
    setNotice(null);

    try {
      await submitHumanReview(
        clinicalCase.id,
        latestReviewRun.id,
        decision,
        reviewNotes.trim() || null,
      );

      setNotice(
        decision === "approve"
          ? "Review approved successfully."
          : "Review rejected successfully.",
      );

      setReviewNotes("");

      await new Promise((resolve) => {
        window.setTimeout(resolve, 1200);
      });

      await refreshWorkspace();
      onCaseChanged();
    } catch (decisionError) {
      setError(
        getErrorMessage(decisionError),
      );
    } finally {
      setActionBusy(false);
    }
  }

  async function askQuestion(): Promise<void> {
    const normalizedQuestion =
      question.trim();

    if (!normalizedQuestion) {
      setError(
        "Enter a question before asking CaseLens.",
      );
      return;
    }

    setAskingQuestion(true);
    setError(null);
    setAnswerResult(null);

    try {
      const result =
        await answerCaseQuestion(
          clinicalCase.id,
          normalizedQuestion,
          3,
        );

      setAnswerResult(result);
    } catch (questionError) {
      setError(
        getErrorMessage(questionError),
      );
    } finally {
      setAskingQuestion(false);
    }
  }

  return (
    <div
      className="workspace-backdrop"
      role="presentation"
      onMouseDown={onClose}
    >
      <section
        className="review-workspace"
        role="dialog"
        aria-modal="true"
        aria-labelledby="workspace-title"
        onMouseDown={(event) => {
          event.stopPropagation();
        }}
      >
        <header className="workspace-header">
          <div className="workspace-title">
            <button
              className="workspace-close"
              type="button"
              onClick={onClose}
              aria-label="Close reviewer workspace"
            >
              ←
            </button>

            <div>
              <p className="eyebrow">
                Reviewer workspace
              </p>

              <h2 id="workspace-title">
                {
                  clinicalCase.patient_external_id
                }
              </h2>

              <p>
                {
                  clinicalCase.requested_service
                }
              </p>
            </div>
          </div>

          <div className="workspace-header-actions">
            {latestReviewRun && (
              <span
                className={`review-run-status ${latestReviewRun.status}`}
              >
                {
                  REVIEW_STATUS_LABELS[
                    latestReviewRun.status
                  ]
                }
              </span>
            )}

            <button
              className="workspace-refresh"
              type="button"
              onClick={() => {
                void refreshWorkspace();
              }}
              disabled={loading}
            >
              ↻ Refresh
            </button>
          </div>
        </header>

        <div className="workspace-summary">
          <div>
            <span>Priority</span>
            <strong>
              {humanize(
                clinicalCase.priority,
              )}
            </strong>
          </div>

          <div>
            <span>Documents</span>
            <strong>{documents.length}</strong>
          </div>

          <div>
            <span>AI findings</span>
            <strong>{facts.length}</strong>
          </div>

          <div>
            <span>Audit events</span>
            <strong>{auditEvents.length}</strong>
          </div>
        </div>

        <nav
          className="workspace-tabs"
          aria-label="Case workspace sections"
          role="tablist"
        >
          <button
            className={
              activeTab === "findings"
                ? "active"
                : ""
            }
            type="button"
            role="tab"
            onClick={() => {
              setActiveTab("findings");
            }}
            aria-selected={activeTab === "findings"}
          >
            AI findings
            <span>{facts.length}</span>
          </button>

          <button
            className={
              activeTab === "documents"
                ? "active"
                : ""
            }
            type="button"
            role="tab"
            onClick={() => {
              setActiveTab("documents");
            }}
            aria-selected={activeTab === "documents"}
          >
            Documents
            <span>{documents.length}</span>
          </button>

          <button
            className={
              activeTab === "audit"
                ? "active"
                : ""
            }
            type="button"
            role="tab"
            onClick={() => {
              setActiveTab("audit");
            }}
            aria-selected={activeTab === "audit"}
          >
            Audit trail
            <span>{auditEvents.length}</span>
          </button>
        </nav>

        {error && (
          <div className="workspace-message error" role="alert">
            <strong>Action failed</strong>
            <p>{error}</p>
          </div>
        )}

        {notice && (
          <div
            className="workspace-message success"
            role="status"
          >
            <strong>Success</strong>
            <p>{notice}</p>
          </div>
        )}

        <div className="workspace-body">
          <main className="workspace-primary">
            {loading ? (
              <div className="workspace-loading">
                <span />
                <strong>
                  Loading clinical evidence
                </strong>
              </div>
            ) : (
              <>
                {activeTab === "findings" && (
                  <div className="findings-view">
                    <section className="workspace-section">
                      <div className="section-heading">
                        <div>
                          <p className="eyebrow">
                            Structured extraction
                          </p>
                          <h3>
                            Evidence-grounded facts
                          </h3>
                        </div>

                        <span className="section-count">
                          {facts.length} findings
                        </span>
                      </div>

                      {facts.length === 0 ? (
                        <div className="workspace-empty">
                          <strong>
                            No AI findings yet
                          </strong>
                          <p>
                            Start a durable review to
                            index documents and extract
                            supported clinical facts.
                          </p>
                        </div>
                      ) : (
                        <div className="fact-list">
                          {facts.map(
                            (
                              fact,
                              factIndex,
                            ) => (
                              <article
                                className="fact-card"
                                key={`${fact.extractionId}-${factIndex}`}
                              >
                                <div className="fact-card-heading">
                                  <div>
                                    <span className="fact-type">
                                      {humanize(
                                        fact.fact_type,
                                      )}
                                    </span>

                                    <h4>
                                      {fact.name}
                                    </h4>
                                  </div>

                                  <span
                                    className={`assertion ${fact.assertion}`}
                                  >
                                    {humanize(
                                      fact.assertion,
                                    )}
                                  </span>
                                </div>

                                {fact.value && (
                                  <p className="fact-value">
                                    {fact.value}
                                  </p>
                                )}

                                <div className="evidence-list">
                                  {fact.evidence.map(
                                    (
                                      citation,
                                      citationIndex,
                                    ) => (
                                      <blockquote
                                        key={`${citation.document_id}-${citationIndex}`}
                                      >
                                        “
                                        {
                                          citation.exact_quote
                                        }
                                        ”
                                        <footer>
                                          Source characters{" "}
                                          {
                                            citation.start_char
                                          }
                                          –
                                          {
                                            citation.end_char
                                          }
                                        </footer>
                                      </blockquote>
                                    ),
                                  )}
                                </div>
                              </article>
                            ),
                          )}
                        </div>
                      )}
                    </section>

                    {(warnings.length > 0 ||
                      missingInformation.length >
                        0) && (
                      <section className="workspace-section">
                        <div className="section-heading">
                          <div>
                            <p className="eyebrow">
                              Safety review
                            </p>
                            <h3>
                              Gaps and warnings
                            </h3>
                          </div>
                        </div>

                        <div className="safety-grid">
                          <div>
                            <h4>
                              Missing information
                            </h4>

                            {missingInformation.length ===
                            0 ? (
                              <p>
                                No missing information
                                reported.
                              </p>
                            ) : (
                              <ul>
                                {missingInformation.map(
                                  (item) => (
                                    <li key={item}>
                                      {item}
                                    </li>
                                  ),
                                )}
                              </ul>
                            )}
                          </div>

                          <div>
                            <h4>Warnings</h4>

                            {warnings.length === 0 ? (
                              <p>
                                No extraction warnings.
                              </p>
                            ) : (
                              <ul>
                                {warnings.map(
                                  (item) => (
                                    <li key={item}>
                                      {item}
                                    </li>
                                  ),
                                )}
                              </ul>
                            )}
                          </div>
                        </div>
                      </section>
                    )}

                    <section className="workspace-section">
                      <div className="section-heading">
                        <div>
                          <p className="eyebrow">
                            Grounded assistant
                          </p>
                          <h3>
                            Ask the indexed case
                          </h3>
                        </div>
                      </div>

                      <div className="question-form">
                        <label
                          className="sr-only"
                          htmlFor="case-question"
                        >
                          Ask a question about this case
                        </label>
                        <textarea
                          id="case-question"
                          value={question}
                          onChange={(event) => {
                            setQuestion(
                              event.target.value,
                            );
                          }}
                          rows={3}
                          maxLength={2000}
                          onKeyDown={(event) => {
                            if (
                              (event.metaKey || event.ctrlKey) &&
                              event.key === "Enter"
                            ) {
                              event.preventDefault();
                              void askQuestion();
                            }
                          }}
                        />

                        <button
                          type="button"
                          onClick={() => {
                            void askQuestion();
                          }}
                          disabled={askingQuestion}
                        >
                          {askingQuestion
                            ? "Generating grounded answer…"
                            : "Ask CaseLens"}
                        </button>
                      </div>

                      {answerResult && (
                        <article
                          aria-live="polite"
                          className={
                            answerResult.answer
                              .supported
                              ? "answer-card supported"
                              : "answer-card unsupported"
                          }
                        >
                          <div className="answer-heading">
                            <span>
                              {answerResult.answer
                                .supported
                                ? "Supported answer"
                                : "Insufficient evidence"}
                            </span>

                            <small>
                              Similarity threshold{" "}
                              {
                                answerResult.min_similarity
                              }
                            </small>
                          </div>

                          <p>
                            {
                              answerResult.answer
                                .answer
                            }
                          </p>

                          {answerResult.answer
                            .citations.length > 0 && (
                            <div className="answer-citations">
                              {answerResult.answer.citations.map(
                                (
                                  citation,
                                  index,
                                ) => (
                                  <blockquote
                                    key={`${citation.chunk_id}-${index}`}
                                  >
                                    “
                                    {
                                      citation.exact_quote
                                    }
                                    ”
                                  </blockquote>
                                ),
                              )}
                            </div>
                          )}
                        </article>
                      )}
                    </section>
                  </div>
                )}

                {activeTab === "documents" && (
                  <section className="workspace-section">
                    <div className="section-heading">
                      <div>
                        <p className="eyebrow">
                          Source records
                        </p>
                        <h3>
                          Clinical documents
                        </h3>
                      </div>
                    </div>

                    {documents.length === 0 ? (
                      <div className="workspace-empty">
                        <strong>
                          No documents uploaded
                        </strong>
                        <p>
                          This case has no reviewable
                          clinical evidence.
                        </p>
                      </div>
                    ) : (
                      <div className="document-list">
                        {documents.map(
                          (document) => (
                            <article
                              key={document.id}
                            >
                              <div className="document-icon">
                                TXT
                              </div>

                              <div>
                                <strong>
                                  {
                                    document.filename
                                  }
                                </strong>

                                <p>
                                  {formatBytes(
                                    document.size_bytes,
                                  )}
                                  {" · "}
                                  {formatDate(
                                    document.uploaded_at,
                                  )}
                                </p>

                                <small>
                                  SHA-256{" "}
                                  {document.content_sha256.slice(
                                    0,
                                    18,
                                  )}
                                  …
                                </small>
                              </div>
                            </article>
                          ),
                        )}
                      </div>
                    )}
                  </section>
                )}

                {activeTab === "audit" && (
                  <section className="workspace-section">
                    <div className="section-heading">
                      <div>
                        <p className="eyebrow">
                          Immutable history
                        </p>
                        <h3>
                          Case audit trail
                        </h3>
                      </div>
                    </div>

                    {auditEvents.length === 0 ? (
                      <div className="workspace-empty">
                        <strong>No audit events yet</strong>
                        <p>
                          Case and review actions will appear
                          here as an immutable history.
                        </p>
                      </div>
                    ) : (
                      <div className="audit-timeline">
                        {[...auditEvents]
                          .reverse()
                          .map((event) => (
                          <article
                            key={event.id}
                          >
                            <span className="audit-dot" />

                            <div>
                              <div className="audit-heading">
                                <strong>
                                  {humanize(
                                    event.event_type,
                                  )}
                                </strong>

                                <span>
                                  {event.actor_type}
                                </span>
                              </div>

                              <time>
                                {formatDate(
                                  event.created_at,
                                )}
                              </time>

                              <pre>
                                {JSON.stringify(
                                  event.details,
                                  null,
                                  2,
                                )}
                              </pre>
                            </div>
                          </article>
                          ))}
                      </div>
                    )}
                  </section>
                )}
              </>
            )}
          </main>

          <aside className="workspace-review-panel">
            <p className="eyebrow">
              Human oversight
            </p>

            <h3>Review decision</h3>

            {latestReviewRun ? (
              <>
                <div className="run-summary">
                  <span>Latest run</span>
                  <strong>
                    {
                      REVIEW_STATUS_LABELS[
                        latestReviewRun.status
                      ]
                    }
                  </strong>
                  <small>
                    {formatDate(
                      latestReviewRun.created_at,
                    )}
                  </small>
                </div>

                {latestReviewRun.status ===
                  "awaiting_human_review" && (
                  <div className="decision-form">
                    <label>
                      Reviewer notes
                      <textarea
                        value={reviewNotes}
                        onChange={(event) => {
                          setReviewNotes(
                            event.target.value,
                          );
                        }}
                        rows={5}
                        maxLength={2000}
                        placeholder="Document the clinical rationale for this decision."
                      />
                    </label>

                    <button
                      className="approve-button"
                      type="button"
                      disabled={actionBusy}
                      onClick={() => {
                        void submitDecision(
                          "approve",
                        );
                      }}
                    >
                      Approve review
                    </button>

                    <button
                      className="reject-button"
                      type="button"
                      disabled={actionBusy}
                      onClick={() => {
                        void submitDecision(
                          "reject",
                        );
                      }}
                    >
                      Reject review
                    </button>
                  </div>
                )}

                {(latestReviewRun.status ===
                  "queued" ||
                  latestReviewRun.status ===
                    "running") && (
                  <div className="processing-state">
                    <span />
                    <strong>
                      Durable processing active
                    </strong>
                    <p>
                      Temporal is indexing and
                      extracting evidence. This panel
                      updates automatically.
                    </p>
                  </div>
                )}

                {[
                  "completed",
                  "rejected",
                ].includes(
                  latestReviewRun.status,
                ) && (
                  <div className="decision-complete">
                    <strong>
                      Decision recorded
                    </strong>
                    <p>
                      This workflow is closed and its
                      history remains available in the
                      audit trail.
                    </p>
                  </div>
                )}
              </>
            ) : (
              <p className="no-run-message">
                No durable review has been started for
                this case.
              </p>
            )}

            {(!latestReviewRun ||
              [
                "completed",
                "rejected",
                "failed",
              ].includes(
                latestReviewRun.status,
              )) && (
              <button
                className="start-review-button"
                type="button"
                disabled={
                  actionBusy ||
                  documents.length === 0
                }
                onClick={() => {
                  void startReview();
                }}
              >
                {actionBusy
                  ? "Starting review…"
                  : "Start durable review"}
              </button>
            )}

            <div className="oversight-note">
              <strong>
                Human decision required
              </strong>
              <p>
                CaseLens never approves or rejects a
                case autonomously. AI output remains
                evidence-linked and reviewer
                controlled.
              </p>
            </div>
          </aside>
        </div>
      </section>
    </div>
  );
}
