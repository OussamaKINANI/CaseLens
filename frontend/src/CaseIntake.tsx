import { useEffect, useRef, useState } from "react";
import type { AnimationEvent, FormEvent, MouseEvent } from "react";

import { createClinicalCase, uploadClinicalDocument } from "./api";
import { DocumentDropzone } from "./components/DocumentDropzone";
import { Icon } from "./components/Icon";
import { validateClinicalDocument } from "./lib/documents";
import { getErrorMessage } from "./lib/errors";

import type { CasePriority, ClinicalCase } from "./types";


interface CaseIntakeProps {
  onClose: () => void;
  onCreated: (clinicalCase: ClinicalCase) => void;
}

export function CaseIntake({ onClose, onCreated }: CaseIntakeProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [patientExternalId, setPatientExternalId] = useState("SYNTH-");
  const [requestedService, setRequestedService] = useState("");
  const [priority, setPriority] = useState<CasePriority>("routine");
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [createdCase, setCreatedCase] = useState<ClinicalCase | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;

    if (dialog && !dialog.open) {
      dialog.showModal();
    }
  }, []);

  const isDirty =
    patientExternalId !== "SYNTH-" ||
    requestedService.trim() !== "" ||
    documentFile !== null ||
    createdCase !== null;

  function beginClose() {
    setClosing(true);
  }

  function requestClose() {
    if (submitting || closing) {
      return;
    }

    if (isDirty && !confirmingDiscard) {
      setConfirmingDiscard(true);
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
    if (closing && event.animationName === "modal-exit") {
      onClose();
    }
  }

  function handleFile(file: File) {
    const validationError = validateClinicalDocument(file);

    if (validationError) {
      setDocumentFile(null);
      setFileError(validationError);
      return;
    }

    setDocumentFile(file);
    setFileError(null);
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    setError(null);

    const normalizedPatientId = patientExternalId.trim();
    const normalizedService = requestedService.trim();

    if (!normalizedPatientId || normalizedPatientId === "SYNTH-") {
      setError("Enter a synthetic patient reference.");
      return;
    }

    if (!normalizedService) {
      setError("Enter the requested clinical service.");
      return;
    }

    if (!documentFile) {
      setFileError("Select a synthetic UTF-8 text document.");
      return;
    }

    setSubmitting(true);

    try {
      // If the case already exists from a previous attempt whose upload
      // failed, retry only the upload instead of creating a duplicate.
      const clinicalCase =
        createdCase ??
        (await createClinicalCase(
          normalizedPatientId,
          normalizedService,
          priority,
        ));

      setCreatedCase(clinicalCase);

      await uploadClinicalDocument(clinicalCase.id, documentFile);

      onCreated(clinicalCase);
    } catch (submissionError) {
      const message = getErrorMessage(submissionError);

      if (createdCase) {
        setError(`The document upload failed again: ${message}`);
      } else {
        setError(message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className={`intake-modal${closing ? " closing" : ""}`}
      aria-labelledby="intake-title"
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onMouseDown={handleBackdropMouseDown}
      onAnimationEnd={handleAnimationEnd}
    >
      <div className="intake-inner">
        <header className="intake-header">
          <div>
            <p className="eyebrow">Clinical intake</p>

            <h2 id="intake-title">Create a review case</h2>

            <p>
              Register a synthetic case and upload its source clinical note.
            </p>
          </div>

          <button
            className="dialog-close"
            type="button"
            onClick={requestClose}
            disabled={submitting}
            aria-label="Close case intake"
          >
            <Icon name="close" size={16} />
          </button>
        </header>

        <div className="synthetic-notice">
          <span>Safety</span>

          <div>
            <strong>Synthetic data only</strong>

            <p>
              Do not enter real names, medical record numbers, or protected
              health information.
            </p>
          </div>
        </div>

        {error && (
          <div className="intake-error" role="alert">
            <strong>Unable to complete intake</strong>

            <p>{error}</p>
          </div>
        )}

        {confirmingDiscard && (
          <div className="discard-confirm" role="alertdialog" aria-label="Discard case confirmation">
            <p>
              {createdCase
                ? "The case was already created. Close without its document?"
                : "Discard this case and the details you entered?"}
            </p>

            <div>
              <button
                className="btn btn-secondary btn-sm"
                type="button"
                onClick={() => {
                  setConfirmingDiscard(false);
                }}
              >
                Keep editing
              </button>

              <button
                className="btn btn-danger btn-sm"
                type="button"
                onClick={beginClose}
              >
                {createdCase ? "Close anyway" : "Discard case"}
              </button>
            </div>
          </div>
        )}

        <form
          className="intake-form"
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
        >
          <label>
            <span>Synthetic patient reference</span>

            <input
              type="text"
              value={patientExternalId}
              onChange={(event) => {
                setPatientExternalId(event.target.value);
              }}
              minLength={2}
              maxLength={100}
              required
              placeholder="SYNTH-CASE-001"
              disabled={submitting || createdCase !== null}
              autoFocus
            />

            <small>Use a non-identifying synthetic ID.</small>
          </label>

          <label>
            <span>Requested service</span>

            <input
              type="text"
              value={requestedService}
              onChange={(event) => {
                setRequestedService(event.target.value);
              }}
              list="requested-service-options"
              minLength={1}
              maxLength={200}
              required
              placeholder="Lumbar spine MRI"
              disabled={submitting || createdCase !== null}
            />

            <datalist id="requested-service-options">
              <option value="Lumbar spine MRI" />
              <option value="Cardiac MRI" />
              <option value="Chest CT" />
              <option value="Knee MRI" />
              <option value="Neurology consultation" />
            </datalist>
          </label>

          <fieldset disabled={submitting || createdCase !== null}>
            <legend>Priority</legend>

            <div className="priority-options">
              <label>
                <input
                  type="radio"
                  name="priority"
                  value="routine"
                  checked={priority === "routine"}
                  onChange={() => {
                    setPriority("routine");
                  }}
                />

                <span>
                  <strong>Routine</strong>
                  <small>Standard review queue</small>
                </span>
              </label>

              <label>
                <input
                  type="radio"
                  name="priority"
                  value="urgent"
                  checked={priority === "urgent"}
                  onChange={() => {
                    setPriority("urgent");
                  }}
                />

                <span>
                  <strong>Urgent</strong>
                  <small>Prioritized reviewer attention</small>
                </span>
              </label>
            </div>
          </fieldset>

          <div className="intake-file-field">
            <span>Synthetic clinical document</span>

            <DocumentDropzone
              file={documentFile}
              onFile={handleFile}
              disabled={submitting}
            />

            {fileError && <p className="field-error">{fileError}</p>}
          </div>

          <footer className="intake-actions">
            {createdCase && (
              <button
                className="btn btn-secondary"
                type="button"
                disabled={submitting}
                onClick={() => {
                  onCreated(createdCase);
                }}
              >
                Open case without document
              </button>
            )}

            <button
              className="btn btn-secondary"
              type="button"
              onClick={requestClose}
              disabled={submitting}
            >
              Cancel
            </button>

            <button
              className="btn btn-primary"
              type="submit"
              disabled={submitting}
            >
              {submitting
                ? createdCase
                  ? "Uploading document…"
                  : "Creating case…"
                : createdCase
                  ? "Retry document upload"
                  : "Create case"}
            </button>
          </footer>
        </form>
      </div>
    </dialog>
  );
}
