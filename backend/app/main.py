from fastapi import FastAPI

app = FastAPI(
    title="langgraphseoblog backend",
    description="LangGraph-powered SEO blog generator API",
    version="0.1.0",
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
