export const MAX_DOCUMENT_BYTES = 1_000_000;

export function validateClinicalDocument(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".txt")) {
    return "Only .txt clinical documents are supported.";
  }

  if (file.size > MAX_DOCUMENT_BYTES) {
    return "The document must be no larger than 1 MB.";
  }

  return null;
}
