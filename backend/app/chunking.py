from dataclasses import dataclass


DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200


@dataclass(frozen=True, slots=True)
class TextChunk:
    chunk_index: int
    content: str
    start_char: int
    end_char: int


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if overlap < 0:
        raise ValueError("overlap cannot be negative")

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    if not text:
        return []

    step_size = chunk_size - overlap
    chunks: list[TextChunk] = []

    for start_char in range(0, len(text), step_size):
        end_char = min(start_char + chunk_size, len(text))
        content = text[start_char:end_char]

        if content.strip():
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    content=content,
                    start_char=start_char,
                    end_char=end_char,
                )
            )

        if end_char == len(text):
            break

    return chunks