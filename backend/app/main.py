import logging

from fastapi import Depends, FastAPI

from app.auth import get_current_reviewer
from app.config import (
    settings,
    uses_development_jwt_secret_key,
)
from app.routers import (
    auth,
    cases,
    documents,
    extractions,
    fhir,
    rag,
    reviews,
    system,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description="Evidence-grounded clinical case review API",
    version="0.1.0",
)

if (
    settings.environment != "development"
    and uses_development_jwt_secret_key()
):
    logger.warning(
        "JWT_SECRET_KEY is still the built-in development value. "
        "Anyone can forge reviewer access tokens. Set a unique "
        "secret before exposing this API."
    )

# Health checks stay public so orchestrators can probe the API, and
# sign-in obviously cannot require a token. Everything that touches
# case data requires an authenticated reviewer.
requires_reviewer = [Depends(get_current_reviewer)]

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(cases.router, dependencies=requires_reviewer)
app.include_router(documents.router, dependencies=requires_reviewer)
app.include_router(fhir.router, dependencies=requires_reviewer)
app.include_router(extractions.router, dependencies=requires_reviewer)
app.include_router(rag.router, dependencies=requires_reviewer)
app.include_router(reviews.router, dependencies=requires_reviewer)
