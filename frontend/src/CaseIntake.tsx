import {
  useState,
} from "react";

import type {
  FormEvent,
} from "react";

import {
  createClinicalCase,
  uploadClinicalDocument,
} from "./api";

import type {
  ClinicalCase,
} from "./types";


interface CaseIntakeProps {
  onClose: () => void;

  onCreated: (
    clinicalCase: ClinicalCase,
  ) => void;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred.";
}

export function CaseIntake({
  onClose,
  onCreated,
}: CaseIntakeProps) {
  const [patientExternalId, setPatientExternalId] =
    useState("SYNTH-");
  const [requestedService, setRequestedService] =
    useState("");
  const [priority, setPriority] =
    useState<"routine" | "urgent">("routine");
  const [documentFile, setDocumentFile] =
    useState<File | null>(null);
  const [submitting, setSubmitting] =
    useState(false);
  const [error, setError] =
    useState<string | null>(null);

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    setError(null);

    const normalizedPatientId =
      patientExternalId.trim();

    const normalizedService =
      requestedService.trim();

    if (
      !normalizedPatientId ||
      normalizedPatientId === "SYNTH-"
    ) {
      setError(
        "Enter a synthetic patient reference.",
      );
      return;
    }

    if (!normalizedService) {
      setError(
        "Enter the requested clinical service.",
      );
      return;
    }

    if (!documentFile) {
      setError(
        "Select a synthetic UTF-8 text document.",
      );
      return;
    }

    if (
      documentFile.size >
      1_000_000
    ) {
      setError(
        "The document must be no larger than 1 MB.",
      );
      return;
    }

    if (
      !documentFile.name
        .toLowerCase()
        .endsWith(".txt")
    ) {
      setError(
        "Only .txt clinical documents are supported.",
      );
      return;
    }

    setSubmitting(true);

    let createdCase: ClinicalCase | null =
      null;

    try {
      createdCase =
        await createClinicalCase(
          normalizedPatientId,
          normalizedService,
          priority,
        );

      await uploadClinicalDocument(
        createdCase.id,
        documentFile,
      );

      onCreated(createdCase);
    } catch (submissionError) {
      const message =
        getErrorMessage(
          submissionError,
        );

      if (createdCase) {
        setError(
          "The case was created, but its document " +
            `could not be uploaded: ${message}`,
        );
      } else {
        setError(message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="intake-backdrop"
      role="presentation"
      onMouseDown={() => {
        if (!submitting) {
          onClose();
        }
      }}
    >
      <section
        className="intake-modal"
        aria-labelledby="intake-title"
        onMouseDown={(event) => {
          event.stopPropagation();
        }}
      >
        <header className="intake-header">
          <div>
            <p className="eyebrow">
              Clinical intake
            </p>

            <h2 id="intake-title">
              Create a review case
            </h2>

            <p>
              Register a synthetic case and upload
              its source clinical note.
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close case intake"
          >
            ×
          </button>
        </header>

        <div className="synthetic-notice">
          <span>Safety</span>

          <div>
            <strong>
              Synthetic data only
            </strong>

            <p>
              Do not enter real names, medical
              record numbers, or protected health
              information.
            </p>
          </div>
        </div>

        {error && (
          <div className="intake-error">
            <strong>
              Unable to complete intake
            </strong>

            <p>{error}</p>
          </div>
        )}

        <form
          className="intake-form"
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
        >
          <label>
            <span>
              Synthetic patient reference
            </span>

            <input
              type="text"
              value={patientExternalId}
              onChange={(event) => {
                setPatientExternalId(
                  event.target.value,
                );
              }}
              minLength={2}
              maxLength={100}
              required
              placeholder="SYNTH-CASE-001"
              autoFocus
            />

            <small>
              Use a non-identifying synthetic ID.
            </small>
          </label>

          <label>
            <span>Requested service</span>

            <input
              type="text"
              value={requestedService}
              onChange={(event) => {
                setRequestedService(
                  event.target.value,
                );
              }}
              list="requested-service-options"
              minLength={1}
              maxLength={200}
              required
              placeholder="Lumbar spine MRI"
            />

            <datalist id="requested-service-options">
              <option value="Lumbar spine MRI" />
              <option value="Cardiac MRI" />
              <option value="Chest CT" />
              <option value="Knee MRI" />
              <option value="Neurology consultation" />
            </datalist>
          </label>

          <fieldset>
            <legend>Priority</legend>

            <div className="priority-options">
              <label>
                <input
                  type="radio"
                  name="priority"
                  value="routine"
                  checked={
                    priority === "routine"
                  }
                  onChange={() => {
                    setPriority("routine");
                  }}
                />

                <span>
                  <strong>Routine</strong>
                  <small>
                    Standard review queue
                  </small>
                </span>
              </label>

              <label>
                <input
                  type="radio"
                  name="priority"
                  value="urgent"
                  checked={
                    priority === "urgent"
                  }
                  onChange={() => {
                    setPriority("urgent");
                  }}
                />

                <span>
                  <strong>Urgent</strong>
                  <small>
                    Prioritized reviewer attention
                  </small>
                </span>
              </label>
            </div>
          </fieldset>

          <label className="file-field">
            <span>
              Synthetic clinical document
            </span>

            <input
              type="file"
              accept=".txt,text/plain"
              required
              onChange={(event) => {
                setDocumentFile(
                  event.target.files?.[0] ??
                    null,
                );
              }}
            />

            <div className="file-dropzone">
              <strong>
                {documentFile
                  ? documentFile.name
                  : "Choose a UTF-8 text document"}
              </strong>

              <small>
                Maximum size: 1 MB
              </small>
            </div>
          </label>

          <footer className="intake-actions">
            <button
              className="intake-cancel"
              type="button"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>

            <button
              className="intake-submit"
              type="submit"
              disabled={submitting}
            >
              {submitting
                ? "Creating case…"
                : "Create case"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}