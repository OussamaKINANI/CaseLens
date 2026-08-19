import pytest

from app.chunking import TextChunk, chunk_text


def test_short_text_creates_one_chunk() -> None:
    text = "Synthetic clinical note."

    chunks = chunk_text(
        text,
        chunk_size=100,
        overlap=20,
    )

    assert chunks == [
        TextChunk(
            chunk_index=0,
            content=text,
            start_char=0,
            end_char=len(text),
        )
    ]


def test_chunks_overlap_deterministically() -> None:
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    chunks = chunk_text(
        text,
        chunk_size=10,
        overlap=3,
    )

    assert [
        (chunk.start_char, chunk.end_char)
        for chunk in chunks
    ] == [
        (0, 10),
        (7, 17),
        (14, 24),
        (21, 26),
    ]

    for chunk in chunks:
        assert chunk.content == text[
            chunk.start_char:chunk.end_char
        ]


def test_blank_text_creates_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text(
        "     ",
        chunk_size=2,
        overlap=0,
    ) == []


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [
        (0, 0),
        (-1, 0),
        (10, -1),
        (10, 10),
        (10, 11),
    ],
)
def test_invalid_chunk_configuration_is_rejected(
    chunk_size: int,
    overlap: int,
) -> None:
    with pytest.raises(ValueError):
        chunk_text(
            "Synthetic note",
            chunk_size=chunk_size,
            overlap=overlap,
        )