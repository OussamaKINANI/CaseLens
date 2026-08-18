from fastapi import FastAPI

app = FastAPI(
    title="CaseLens API",
    description="Evidence-grounded clinical case review API",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "caselens-api",
    }