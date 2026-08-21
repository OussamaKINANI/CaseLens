import { useEffect, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";

import { Icon } from "./Icon";
import { formatBytes } from "../lib/format";

interface DocumentDropzoneProps {
  file: File | null;
  onFile: (file: File) => void;
  disabled?: boolean;
  busy?: boolean;
  prompt?: string;
}

export function DocumentDropzone({
  file,
  onFile,
  disabled = false,
  busy = false,
  prompt = "Choose a UTF-8 text document",
}: DocumentDropzoneProps) {
  const [dragging, setDragging] = useState(false);

  // Stop the browser from navigating away when a file is dropped
  // anywhere outside the dropzone while it is mounted.
  useEffect(() => {
    function preventWindowDrop(event: globalThis.DragEvent) {
      event.preventDefault();
    }

    window.addEventListener("dragover", preventWindowDrop);
    window.addEventListener("drop", preventWindowDrop);

    return () => {
      window.removeEventListener("dragover", preventWindowDrop);
      window.removeEventListener("drop", preventWindowDrop);
    };
  }, []);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0];

    if (selected) {
      onFile(selected);
    }

    // Allow re-selecting the same file after a failed upload.
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);

    if (disabled || busy) {
      return;
    }

    const dropped = event.dataTransfer.files?.[0];

    if (dropped) {
      onFile(dropped);
    }
  }

  return (
    <label
      className={`file-dropzone${dragging ? " dragging" : ""}${
        disabled || busy ? " disabled" : ""
      }`}
      onDragOver={(event) => {
        event.preventDefault();

        if (!disabled && !busy) {
          setDragging(true);
        }
      }}
      onDragLeave={() => {
        setDragging(false);
      }}
      onDrop={handleDrop}
    >
      <input
        type="file"
        accept=".txt,text/plain"
        disabled={disabled || busy}
        onChange={handleChange}
      />

      <Icon name={busy ? "refresh" : file ? "file" : "upload"} size={18} className={busy ? "spin" : undefined} />

      <strong>
        {busy
          ? "Uploading document…"
          : file
            ? `${file.name} · ${formatBytes(file.size)}`
            : prompt}
      </strong>

      <small>Drag and drop, or click to browse · .txt up to 1 MB</small>
    </label>
  );
}
