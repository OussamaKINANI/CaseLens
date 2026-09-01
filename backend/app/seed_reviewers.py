"""Create the bootstrap reviewer account.

Run after migrations:

    python -m app.seed_reviewers

The command is idempotent. An existing account with the configured
email is left untouched, so re-running never resets a password.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_models import ReviewerRecord
from app.config import settings
from app.database import SessionLocal
from app.security import hash_password


logger = logging.getLogger(__name__)

MINIMUM_RECOMMENDED_PASSWORD_LENGTH = 12


def seed_reviewer(database: Session) -> ReviewerRecord | None:
    email = (settings.seed_reviewer_email or "").strip().lower()
    password = settings.seed_reviewer_password

    if not email or not password:
        logger.info(
            "SEED_REVIEWER_EMAIL and SEED_REVIEWER_PASSWORD are not "
            "both set; skipping reviewer seeding."
        )

        return None

    if len(password) < MINIMUM_RECOMMENDED_PASSWORD_LENGTH:
        logger.warning(
            "SEED_REVIEWER_PASSWORD is shorter than %d characters.",
            MINIMUM_RECOMMENDED_PASSWORD_LENGTH,
        )

    statement = select(ReviewerRecord).where(
        ReviewerRecord.email == email,
    )

    existing_reviewer = database.scalar(statement)

    if existing_reviewer is not None:
        logger.info(
            "Reviewer %s already exists; leaving it unchanged.",
            email,
        )

        return existing_reviewer

    reviewer = ReviewerRecord(
        email=email,
        full_name=settings.seed_reviewer_full_name,
        password_hash=hash_password(password),
        role=settings.seed_reviewer_role.value,
        is_active=True,
    )

    database.add(reviewer)
    database.commit()
    database.refresh(reviewer)

    logger.info(
        "Created reviewer %s with role %s.",
        reviewer.email,
        reviewer.role,
    )

    return reviewer


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s %(message)s"
        ),
    )

    with SessionLocal() as database:
        seed_reviewer(database)


if __name__ == "__main__":
    main()
