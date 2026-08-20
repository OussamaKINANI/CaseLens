import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = (
    Path(__file__).resolve().parents[1]
)


def test_worker_import_loads_foreign_key_tables(
) -> None:
    script = """
from app.temporal_worker import CaseReviewWorkflow
from app.database import Base

required_tables = {
    "cases",
    "audit_events",
    "clinical_documents",
    "case_review_runs",
}

missing_tables = (
    required_tables
    - set(Base.metadata.tables)
)

assert not missing_tables, (
    f"Worker is missing ORM tables: "
    f"{sorted(missing_tables)}"
)
"""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        result.stdout + result.stderr
    )
    