import { useEffect, useRef, useState } from "react";
import type { AnimationEvent, MouseEvent } from "react";

import { Icon } from "./Icon";

import type { ClinicalCase } from "../types";


interface DeleteCaseDialogProps {
  clinicalCase: ClinicalCase;
  deleting: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}

export function DeleteCaseDialog({
  clinicalCase,
  deleting,
  error,
  onConfirm,
  onClose,
}: DeleteCaseDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;

    if (dialog && !dialog.open) {
      dialog.showModal();
    }
  }, []);

  function requestClose() {
    if (deleting || closing) {
      return;
    }

    setClosing(true);
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

  return (
    <dialog
      ref={dialogRef}
      className={`confirm-dialog${closing ? " closing" : ""}`}
      aria-labelledby="delete-case-title"
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onMouseDown={handleBackdropMouseDown}
      onAnimationEnd={handleAnimationEnd}
    >
      <div className="confirm-inner">
        <div className="confirm-icon danger">
          <Icon name="trash" size={18} />
        </div>

        <h2 id="delete-case-title">Delete this case?</h2>

        <p>
          <strong>{clinicalCase.patient_external_id}</strong>
          {" · "}
          {clinicalCase.requested_service}
        </p>

        <p>
          This permanently removes the case with its documents, AI findings,
          review history, and audit trail. This cannot be undone.
        </p>

        {error && (
          <div className="confirm-error" role="alert">
            {error}
          </div>
        )}

        <div className="confirm-actions">
          <button
            className="btn btn-secondary"
            type="button"
            onClick={requestClose}
            disabled={deleting}
            autoFocus
          >
            Keep case
          </button>

          <button
            className="btn btn-danger-solid"
            type="button"
            onClick={onConfirm}
            disabled={deleting}
          >
            {deleting ? "Deleting…" : "Delete case"}
          </button>
        </div>
      </div>
    </dialog>
  );
}
