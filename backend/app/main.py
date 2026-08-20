from fastapi import FastAPI

from app.config import settings
from app.routers import (
    cases,
    documents,
    extractions,
    fhir,
    system,
)

from app.routers import (
    cases,
    documents,
    extractions,
    fhir,
    rag,
    system,
)
from app.routers import (
    cases,
    documents,
    extractions,
    fhir,
    rag,
    reviews,
    system,
)
app = FastAPI(
    title=settings.app_name,
    description="Evidence-grounded clinical case review API",
    version="0.1.0",
)

app.include_router(system.router)
app.include_router(cases.router)
app.include_router(documents.router)
app.include_router(fhir.router)
app.include_router(extractions.router)
app.include_router(rag.router)
app.include_router(reviews.router)