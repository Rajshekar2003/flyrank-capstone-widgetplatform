"""Application wiring only: migrations, CORS, error handling and routers. No business logic lives here."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import run_migrations
from app.errors import AppError
from app.routers import auth, dashboard, public, submissions, widgets

run_migrations()

app = FastAPI(title="Embeddable Widget & Lead-Capture Platform")

# The widget script runs on other people's sites, so the public endpoints must allow any origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
    expose_headers=["Retry-After"],
)


@app.exception_handler(AppError)
async def handle_app_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers or None)


@app.get("/health")
def health():
    return {"status": "ok"}


for router in (auth.router, widgets.router, submissions.router, public.router, dashboard.router):
    app.include_router(router)
