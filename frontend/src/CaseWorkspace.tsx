import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AnimationEvent, KeyboardEvent, MouseEvent } from "react";

import {
  answerCaseQuestion,
  createCaseReviewRun,
  listCaseAuditEvents,
  listCaseDocuments,
  listCaseExtractions,
  listCaseReviewRuns,
  startCaseReviewRun,
  submitHumanReview,
  uploadClinicalDocument,
} from "./api";
import { DocumentDropzone } from "./components/DocumentDropzone";
import { Icon } from "./components/Icon";
import { validateClinicalDocument } from "./lib/documents";
import { getErrorMessage, isAbortError } from "./lib/errors";
import { formatBytes, formatDate, humanize } from "./lib/format";

import type {
  AuditEvent,
  CaseAnswerResponse,
  CaseReviewRun,
  CaseStatus,
  ClinicalCase,
  ClinicalDocument,
  ClinicalExtraction,
} from "./types";


type WorkspaceTab = "findings" | "documents" | "audit";
type BusyAction = "start" | "approve" | "reject" | null;

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

const TAB_ORDER: WorkspaceTab[] = ["findings", "documents", "audit"];

const POLL_INTERVAL_MS = 3000;
const DECISION_POLL_INTERVAL_MS = 500;
const DECISION_POLL_ATTEMPTS = 10;

const REVIEW_STATUS_LABELS: Record<CaseReviewRun["status"], string> = {
  queued: "Queued",
  running: "AI processing",
  awaiting_human_review: "Awaiting human review",
  completed: "Approved",
  rejected: "Rejected",
  failed: "Failed",
};

const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  received: "Received",
  processing: "Processing",
  awaiting_review: "Awaiting review",
  completed: "Completed",
  failed: "Failed",
};

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function newestRun(runs: CaseReviewRun[]): CaseReviewRun | null {
  return (
    [...runs].sort(
      (left, right) =>
        new Date(right.created_at).getTime() -
        new Date(left.created_at).getTime(),
    )[0] ?? null
  );
}

async function fetchWorkspaceData(
  caseId: string,
  signal?: AbortSignal,
): Promise<WorkspaceData> {
  const [documents, extractions, auditEvents, reviewRuns] = await Promise.all([
    listCaseDocuments(caseId, { signal }),
    listCaseExtractions(caseId, { signal }),
    listCaseAuditEvents(caseId, { signal }),
    listCaseReviewRuns(caseId, { signal }),
  ]);

  return { documents, extractions, auditEvents, reviewRuns };
}

function WorkspaceSkeleton() {
  return (
    <div className="workspace-skeleton" aria-hidden="true">
      {[0, 1, 2].map((index) => (
        <div className="workspace-skeleton-card" key={index}>
          <span className="skeleton" style={{ width: "34%" }} />
          <span className="skeleton" style={{ width: "88%" }} />
          <span className="skeleton" style={{ width: "72%" }} />
        </div>
      ))}
    </div>
  );
}

export function CaseWorkspace({
  clinicalCase,
  onClose,
  onCaseChanged,
}: CaseWorkspaceProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [closing, setClosing] = useState(false);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("findings");
  const [documents, setDocuments] = useState<ClinicalDocument[]>([]);
  const [extractions, setExtractions] = useState<ClinicalExtraction[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [reviewRuns, setReviewRuns] = useState<CaseReviewRun[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [question, setQuestion] = useState(
    "What clinically relevant treatment was attempted?",
  );
  const [questionError, setQuestionError] = useState<string | null>(null);
  const [answerResult, setAnswerResult] =
    useState<CaseAnswerResponse | null>(null);
  const [askingQuestion, setAskingQuestion] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;

    if (dialog && !dialog.open) {
      dialog.showModal();
    }
  }, []);

  const applyWorkspaceData = useCallback((data: WorkspaceData) => {
    setDocuments(data.documents);
    setExtractions(data.extractions);
    setAuditEvents(data.auditEvents);
    setReviewRuns(data.reviewRuns);
  }, []);

  const refreshWorkspace = useCallback(
    async (options?: { signal?: AbortSignal }) => {
      try {
        const data = await fetchWorkspaceData(
          clinicalCase.id,
          options?.signal,
        );

        applyWorkspaceData(data);
        setError(null);
      } catch (refreshError) {
        if (!isAbortError(refreshError)) {
          setError(getErrorMessage(refreshError));
        }
      } finally {
        setInitialLoading(false);
      }
    },
    [applyWorkspaceData, clinicalCase.id],
  );

  const handleManualRefresh = useCallback(() => {
    setRefreshing(true);

    void refreshWorkspace().finally(() => {
      setRefreshing(false);
    });
  }, [refreshWorkspace]);

  useEffect(() => {
    const controller = new AbortController();
    // False positive: every setState inside refreshWorkspace runs after
    // the fetch resolves, never synchronously within this effect.
    // eslint-disable-next-line react/set-state-in-effect
    void refreshWorkspace({ signal: controller.signal });

    return () => {
      controller.abort();
    };
  }, [refreshWorkspace]);

  // Success notices dismiss themselves.
  useEffect(() => {
    if (!notice) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setNotice(null);
    }, 5000);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [notice]);

  const latestReviewRun = useMemo(
    () => newestRun(reviewRuns),
    [reviewRuns],
  );

  const latestRunIsProcessing =
    latestReviewRun?.status === "queued" ||
    latestReviewRun?.status === "running";

  // Poll while Temporal is processing; pause in hidden tabs; notify the
  // dashboard as soon as the run leaves its processing states.
  useEffect(() => {
    if (!latestRunIsProcessing) {
      return;
    }

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

      if (document.visibilityState !== "visible") {
        schedule();
        return;
      }

      running = true;

      try {
        const runs = await listCaseReviewRuns(clinicalCase.id);

        if (cancelled) {
          return;
        }

        setReviewRuns(runs);

        const newest = newestRun(runs);

        if (
          newest &&
          newest.status !== "queued" &&
          newest.status !== "running"
        ) {
          await refreshWorkspace();
          onCaseChanged();
          return;
        }
      } catch {
        // Transient polling failures are ignored; manual refresh remains.
      } finally {
        running = false;
      }

      schedule();
    }

    void tick();

    function handleVisibility() {
      if (document.visibilityState === "visible") {
        window.clearTimeout(timeoutId);
        void tick();
      }
    }

    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [
    clinicalCase.id,
    latestRunIsProcessing,
    onCaseChanged,
    refreshWorkspace,
  ]);

  const facts = useMemo(() => {
    return extractions.flatMap((extraction) =>
      extraction.result.facts.map((fact) => ({
        ...fact,
        extractionId: extraction.id,
        documentId: extraction.document_id,
      })),
    );
  }, [extractions]);

  const missingInformation = useMemo(() => {
    return Array.from(
      new Set(
        extractions.flatMap(
          (extraction) => extraction.result.missing_information,
        ),
      ),
    );
  }, [extractions]);

  const warnings = useMemo(() => {
    return Array.from(
      new Set(extractions.flatMap((extraction) => extraction.result.warnings)),
    );
  }, [extractions]);

  const documentNames = useMemo(
    () => new Map(documents.map((doc) => [doc.id, doc.filename])),
    [documents],
  );

  const sortedAuditEvents = useMemo(() => {
    return [...auditEvents].sort(
      (left, right) =>
        new Date(right.created_at).getTime() -
        new Date(left.created_at).getTime(),
    );
  }, [auditEvents]);

  function documentName(documentId: string): string {
    return documentNames.get(documentId) ?? "Unknown document";
  }

  function beginClose() {
    setClosing(true);
  }

  function requestClose() {
    if (closing) {
      return;
    }

    beginClose();
  }

  function handleBackdropMouseDown(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === dialogRef.current) {
      requestClose();
    }
  }

  function handleAnimationEnd(event: AnimationEvent<HTMLDialogElement>) {
    if (closing && event.animationName === "workspace-exit") {
      onClose();
    }
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const index = TAB_ORDER.indexOf(activeTab);
    let next: WorkspaceTab | null = null;

    if (event.key === "ArrowRight") {
      next = TAB_ORDER[(index + 1) % TAB_ORDER.length];
    } else if (event.key === "ArrowLeft") {
      next = TAB_ORDER[(index + TAB_ORDER.length - 1) % TAB_ORDER.length];
    } else if (event.key === "Home") {
      next = TAB_ORDER[0];
    } else if (event.key === "End") {
      next = TAB_ORDER[TAB_ORDER.length - 1];
    }

    if (next) {
      event.preventDefault();
      setActiveTab(next);
      document.getElementById(`workspace-tab-${next}`)?.focus();
    }
  }

  async function startReview(): Promise<void> {
    if (documents.length === 0) {
      return;
    }

    setBusyAction("start");
    setError(null);
    setNotice(null);

    try {
      const reviewRun = await createCaseReviewRun(
        clinicalCase.id,
        documents.map((doc) => doc.id),
      );

      await startCaseReviewRun(clinicalCase.id, reviewRun.id);

      setNotice("Durable AI review started.");

      await refreshWorkspace();
      onCaseChanged();
    } catch (startError) {
      setError(getErrorMessage(startError));
    } finally {
      setBusyAction(null);
    }
  }

  async function submitDecision(
    decision: "approve" | "reject",
  ): Promise<void> {
    if (
      !latestReviewRun ||
      latestReviewRun.status !== "awaiting_human_review"
    ) {
      return;
    }

    const reviewRunId = latestReviewRun.id;

    setBusyAction(decision);
    setError(null);
    setNotice(null);

    try {
      await submitHumanReview(
        clinicalCase.id,
        reviewRunId,
        decision,
        reviewNotes.trim() || null,
      );

      // Wait for the durable state transition instead of guessing with a
      // fixed sleep; the workflow usually lands within a poll or two. The
      // decision itself already succeeded, so polling is best-effort.
      try {
        for (
          let attempt = 0;
          attempt < DECISION_POLL_ATTEMPTS;
          attempt += 1
        ) {
          const runs = await listCaseReviewRuns(clinicalCase.id);
          const updated = runs.find((run) => run.id === reviewRunId);

          if (updated && updated.status !== "awaiting_human_review") {
            break;
          }

          await delay(DECISION_POLL_INTERVAL_MS);
        }
      } catch {
        // The refresh below still shows the latest durable state.
      }

      await refreshWorkspace();
      onCaseChanged();

      setNotice(
        decision === "approve"
          ? "Review approved and recorded."
          : "Review rejected and recorded.",
      );

      setReviewNotes("");
    } catch (decisionError) {
      setError(getErrorMessage(decisionError));
    } finally {
      setBusyAction(null);
    }
  }

  async function askQuestion(): Promise<void> {
    const normalizedQuestion = question.trim();

    if (!normalizedQuestion) {
      setQuestionError("Enter a question before asking CaseLens.");
      return;
    }

    setAskingQuestion(true);
    setQuestionError(null);

    try {
      const result = await answerCaseQuestion(
        clinicalCase.id,
        normalizedQuestion,
        3,
      );

      setAnswerResult(result);
    } catch (askError) {
      setQuestionError(getErrorMessage(askError));
    } finally {
      setAskingQuestion(false);
    }
  }

  async function handleWorkspaceUpload(file: File): Promise<void> {
    const validationError = validateClinicalDocument(file);

    if (validationError) {
      setUploadError(validationError);
      return;
    }

    setUploading(true);
    setUploadError(null);

    try {
      await uploadClinicalDocument(clinicalCase.id, file);
      await refreshWorkspace();
      setNotice(`Uploaded ${file.name}.`);
    } catch (uploadFailure) {
      setUploadError(getErrorMessage(uploadFailure));
    } finally {
      setUploading(false);
    }
  }

  const runIsClosed =
    latestReviewRun !== null &&
    ["completed", "rejected", "failed"].includes(latestReviewRun.status);

  const canStartReview = !latestReviewRun || runIsClosed;

  const tabs: Array<{ id: WorkspaceTab; label: string; count: number }> = [
    { id: "findings", label: "AI findings", count: facts.length },
    { id: "documents", label: "Documents", count: documents.length },
    { id: "audit", label: "Audit trail", count: auditEvents.length },
  ];

  return (
    <dialog
      ref={dialogRef}
      className={`review-workspace${closing ? " closing" : ""}`}
      aria-label="Clinical case reviewer workspace"
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onMouseDown={handleBackdropMouseDown}
      onAnimationEnd={handleAnimationEnd}
    >
      <div className="workspace-scroll">
        <header className="workspace-header">
          <div className="workspace-title">
            <button
              className="workspace-close"
              type="button"
              onClick={requestClose}
              aria-label="Close reviewer workspace"
            >
              <Icon name="arrow-left" size={17} />
            </button>

            <div>
              <p className="eyebrow">Reviewer workspace</p>

              <h2>{clinicalCase.patient_external_id}</h2>

              <p>{clinicalCase.requested_service}</p>
            </div>
          </div>

          <div className="workspace-header-actions">
            <span className={`status-badge ${clinicalCase.status}`}>
              {CASE_STATUS_LABELS[clinicalCase.status]}
            </span>

            {latestReviewRun && (
              <span
                className={`review-run-status ${latestReviewRun.status}`}
              >
                {REVIEW_STATUS_LABELS[latestReviewRun.status]}
              </span>
            )}

            <button
              className="workspace-refresh"
              type="button"
              onClick={handleManualRefresh}
              disabled={refreshing}
            >
              <Icon
                name="refresh"
                size={13}
                className={refreshing ? "spin" : undefined}
              />
              Refresh
            </button>
          </div>
        </header>

        <div className="workspace-summary">
          <div>
            <span>Priority</span>
            <strong>{humanize(clinicalCase.priority)}</strong>
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

        <div
          className="workspace-tabs"
          role="tablist"
          aria-label="Case workspace sections"
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              id={`workspace-tab-${tab.id}`}
              role="tab"
              type="button"
              aria-selected={activeTab === tab.id}
              aria-controls={`workspace-panel-${tab.id}`}
              tabIndex={activeTab === tab.id ? 0 : -1}
              className={activeTab === tab.id ? "active" : ""}
              onClick={() => {
                setActiveTab(tab.id);
              }}
              onKeyDown={handleTabKeyDown}
            >
              {tab.label}
              <span>{tab.count}</span>
            </button>
          ))}
        </div>

        {error && (
          <div className="workspace-message error" role="alert">
            <strong>Action failed</strong>
            <p>{error}</p>

            <button
              className="message-dismiss"
              type="button"
              onClick={() => {
                setError(null);
              }}
              aria-label="Dismiss error"
            >
              <Icon name="close" size={13} />
            </button>
          </div>
        )}

        {notice && (
          <div className="workspace-message success" role="status">
            <strong>Success</strong>
            <p>{notice}</p>

            <button
              className="message-dismiss"
              type="button"
              onClick={() => {
                setNotice(null);
              }}
              aria-label="Dismiss notice"
            >
              <Icon name="close" size={13} />
            </button>
          </div>
        )}

        <div className="workspace-body">
          <main
            className="workspace-primary"
            id={`workspace-panel-${activeTab}`}
            role="tabpanel"
            aria-labelledby={`workspace-tab-${activeTab}`}
          >
            {initialLoading ? (
              <WorkspaceSkeleton />
            ) : (
              <div className="tab-panel" key={activeTab}>
                {activeTab === "findings" && (
                  <div className="findings-view">
                    <section className="workspace-section">
                      <div className="section-heading">
                        <div>
                          <p className="eyebrow">Structured extraction</p>
                          <h3>Evidence-grounded facts</h3>
                        </div>

                        <span className="section-count">
                          {facts.length} findings
                        </span>
                      </div>

                      {facts.length === 0 ? (
                        <div className="workspace-empty">
                          <strong>No AI findings yet</strong>
                          <p>
                            Start a durable review to index documents and
                            extract supported clinical facts.
                          </p>
                        </div>
                      ) : (
                        <div className="fact-list">
                          {facts.map((fact, factIndex) => (
                            <article
                              className="fact-card"
                              key={`${fact.extractionId}-${factIndex}`}
                            >
                              <div className="fact-card-heading">
                                <div>
                                  <span className="fact-type">
                                    {humanize(fact.fact_type)}
                                  </span>

                                  <h4>{fact.name}</h4>
                                </div>

                                <span
                                  className={`assertion ${fact.assertion}`}
                                >
                                  {humanize(fact.assertion)}
                                </span>
                              </div>

                              {fact.value && (
                                <p className="fact-value">{fact.value}</p>
                              )}

                              <div className="evidence-list">
                                {fact.evidence.map(
                                  (citation, citationIndex) => (
                                    <blockquote
                                      key={`${citation.document_id}-${citationIndex}`}
                                    >
                                      “{citation.exact_quote}”
                                      <footer>
                                        {documentName(citation.document_id)}
                                        {" · chars "}
                                        {citation.start_char}–
                                        {citation.end_char}
                                      </footer>
                                    </blockquote>
                                  ),
                                )}
                              </div>
                            </article>
                          ))}
                        </div>
                      )}
                    </section>

                    {(warnings.length > 0 ||
                      missingInformation.length > 0) && (
                      <section className="workspace-section">
                        <div className="section-heading">
                          <div>
                            <p className="eyebrow">Safety review</p>
                            <h3>Gaps and warnings</h3>
                          </div>
                        </div>

                        <div className="safety-grid">
                          <div>
                            <h4>Missing information</h4>

                            {missingInformation.length === 0 ? (
                              <p>No missing information reported.</p>
                            ) : (
                              <ul>
                                {missingInformation.map((item) => (
                                  <li key={item}>{item}</li>
                                ))}
                              </ul>
                            )}
                          </div>

                          <div>
                            <h4>Warnings</h4>

                            {warnings.length === 0 ? (
                              <p>No extraction warnings.</p>
                            ) : (
                              <ul>
                                {warnings.map((item) => (
                                  <li key={item}>{item}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                        </div>
                      </section>
                    )}

                    <section className="workspace-section">
                      <div className="section-heading">
                        <div>
                          <p className="eyebrow">Grounded assistant</p>
                          <h3>Ask the indexed case</h3>
                        </div>
                      </div>

                      <form
                        className="question-form"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void askQuestion();
                        }}
                      >
                        <label className="sr-only" htmlFor="case-question">
                          Question for the indexed case documents
                        </label>

                        <textarea
                          id="case-question"
                          value={question}
                          onChange={(event) => {
                            setQuestion(event.target.value);
                          }}
                          onKeyDown={(event) => {
                            if (
                              (event.ctrlKey || event.metaKey) &&
                              event.key === "Enter"
                            ) {
                              event.preventDefault();
                              void askQuestion();
                            }
                          }}
                          rows={3}
                          maxLength={2000}
                          placeholder="Ask about the indexed case documents"
                        />

                        {questionError && (
                          <p className="field-error" role="alert">
                            {questionError}
                          </p>
                        )}

                        <div className="question-actions">
                          <small>Ctrl+Enter to ask</small>

                          <button
                            className="btn btn-primary btn-sm"
                            type="submit"
                            disabled={askingQuestion}
                          >
                            {askingQuestion
                              ? "Generating grounded answer…"
                              : "Ask CaseLens"}
                          </button>
                        </div>
                      </form>

                      <div aria-live="polite">
                        {answerResult && (
                          <article
                            className={`answer-card ${
                              answerResult.answer.supported
                                ? "supported"
                                : "unsupported"
                            }${askingQuestion ? " stale" : ""}`}
                          >
                            <div className="answer-heading">
                              <span>
                                {answerResult.answer.supported
                                  ? "Supported answer"
                                  : "Insufficient evidence"}
                              </span>

                              <small>
                                Min similarity{" "}
                                {answerResult.min_similarity.toFixed(2)}
                              </small>
                            </div>

                            <p>{answerResult.answer.answer}</p>

                            {answerResult.answer.citations.length > 0 && (
                              <div className="answer-citations">
                                {answerResult.answer.citations.map(
                                  (citation, index) => (
                                    <blockquote
                                      key={`${citation.chunk_id}-${index}`}
                                    >
                                      “{citation.exact_quote}”
                                      <footer>
                                        {documentName(citation.document_id)}
                                        {" · chars "}
                                        {citation.start_char}–
                                        {citation.end_char}
                                      </footer>
                                    </blockquote>
                                  ),
                                )}
                              </div>
                            )}
                          </article>
                        )}
                      </div>
                    </section>
                  </div>
                )}

                {activeTab === "documents" && (
                  <section className="workspace-section">
                    <div className="section-heading">
                      <div>
                        <p className="eyebrow">Source records</p>
                        <h3>Clinical documents</h3>
                      </div>
                    </div>

                    {documents.length === 0 ? (
                      <div className="workspace-empty">
                        <strong>No documents uploaded</strong>
                        <p>
                          Upload a synthetic clinical note below to give this
                          case reviewable evidence.
                        </p>
                      </div>
                    ) : (
                      <div className="document-list">
                        {documents.map((doc) => (
                          <article key={doc.id}>
                            <div className="document-icon">
                              <Icon name="file" size={17} />
                            </div>

                            <div>
                              <strong>{doc.filename}</strong>

                              <p>
                                {formatBytes(doc.size_bytes)}
                                {" · "}
                                {formatDate(doc.uploaded_at)}
                              </p>

                              <small>
                                SHA-256 {doc.content_sha256.slice(0, 18)}…
                              </small>
                            </div>
                          </article>
                        ))}
                      </div>
                    )}

                    <div className="workspace-upload">
                      <DocumentDropzone
                        file={null}
                        onFile={(file) => {
                          void handleWorkspaceUpload(file);
                        }}
                        busy={uploading}
                        prompt="Add a synthetic clinical document"
                      />

                      {uploadError && (
                        <p className="field-error" role="alert">
                          {uploadError}
                        </p>
                      )}
                    </div>
                  </section>
                )}

                {activeTab === "audit" && (
                  <section className="workspace-section">
                    <div className="section-heading">
                      <div>
                        <p className="eyebrow">Immutable history</p>
                        <h3>Case audit trail</h3>
                      </div>
                    </div>

                    {sortedAuditEvents.length === 0 ? (
                      <div className="workspace-empty">
                        <strong>No audit events yet</strong>
                        <p>
                          Case and workflow actions are recorded here as they
                          happen.
                        </p>
                      </div>
                    ) : (
                      <div className="audit-timeline">
                        {sortedAuditEvents.map((event) => (
                          <article
                            key={event.id}
                            className={
                              event.actor_type === "reviewer"
                                ? "reviewer-event"
                                : undefined
                            }
                          >
                            <span className="audit-dot" />

                            <div>
                              <div className="audit-heading">
                                <strong>{humanize(event.event_type)}</strong>

                                <span>
                                  {event.actor_label ??
                                    humanize(event.actor_type)}
                                </span>
                              </div>

                              <time>{formatDate(event.created_at)}</time>

                              {Object.keys(event.details).length > 0 && (
                                <details className="audit-details">
                                  <summary>Details</summary>

                                  <pre>
                                    {JSON.stringify(event.details, null, 2)}
                                  </pre>
                                </details>
                              )}
                            </div>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>
                )}
              </div>
            )}
          </main>

          <aside className="workspace-review-panel">
            <p className="eyebrow">Human oversight</p>

            <h3>Review decision</h3>

            {latestReviewRun ? (
              <>
                <div className="run-summary">
                  <span>Latest run</span>
                  <strong>
                    {REVIEW_STATUS_LABELS[latestReviewRun.status]}
                  </strong>
                  <small>{formatDate(latestReviewRun.created_at)}</small>
                </div>

                {latestReviewRun.status === "awaiting_human_review" && (
                  <div className="decision-form">
                    <label>
                      Reviewer notes
                      <textarea
                        value={reviewNotes}
                        onChange={(event) => {
                          setReviewNotes(event.target.value);
                        }}
                        rows={5}
                        maxLength={2000}
                        placeholder="Document the clinical rationale for this decision."
                      />
                    </label>

                    <button
                      className="btn btn-primary btn-block"
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() => {
                        void submitDecision("approve");
                      }}
                    >
                      {busyAction === "approve"
                        ? "Approving…"
                        : "Approve review"}
                    </button>

                    <button
                      className="btn btn-danger btn-block"
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() => {
                        void submitDecision("reject");
                      }}
                    >
                      {busyAction === "reject"
                        ? "Rejecting…"
                        : "Reject review"}
                    </button>
                  </div>
                )}

                {latestRunIsProcessing && (
                  <div className="processing-state">
                    <span />
                    <strong>Durable processing active</strong>
                    <p>
                      Temporal is indexing and extracting evidence. This panel
                      updates automatically.
                    </p>
                  </div>
                )}

                {latestReviewRun.status === "failed" && (
                  <div className="run-failed" role="alert">
                    <div className="run-failed-heading">
                      <Icon name="alert" size={14} />
                      <strong>Review failed</strong>
                    </div>

                    <p>
                      {latestReviewRun.failure_code
                        ? humanize(latestReviewRun.failure_code)
                        : "The durable workflow reported a failure."}
                    </p>
                  </div>
                )}

                {["completed", "rejected"].includes(
                  latestReviewRun.status,
                ) && (
                  <div className="decision-complete">
                    <strong>Decision recorded</strong>
                    <p>
                      This workflow is closed and its history remains
                      available in the audit trail.
                    </p>
                  </div>
                )}
              </>
            ) : (
              <p className="no-run-message">
                No durable review has been started for this case.
              </p>
            )}

            {canStartReview && (
              <>
                <button
                  className="btn btn-primary btn-block start-review-button"
                  type="button"
                  disabled={busyAction !== null || documents.length === 0}
                  onClick={() => {
                    void startReview();
                  }}
                >
                  {busyAction === "start"
                    ? "Starting review…"
                    : latestReviewRun?.status === "failed"
                      ? "Retry durable review"
                      : "Start durable review"}
                </button>

                {documents.length === 0 && !initialLoading && (
                  <p className="start-review-hint">
                    Upload at least one document to enable review.
                  </p>
                )}
              </>
            )}

            <div className="oversight-note">
              <strong>Human decision required</strong>
              <p>
                CaseLens never approves or rejects a case autonomously. AI
                output remains evidence-linked and reviewer controlled.
              </p>
            </div>
          </aside>
        </div>
      </div>
    </dialog>
  );
}
