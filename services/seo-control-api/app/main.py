from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, SessionLocal, engine
from .routers import activity, articles, automations, dashboard, keywords, publishing, search_console, settings as settings_router
from .seed import ensure_seed_data

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_seed_data(db)
    finally:
        db.close()


app.include_router(dashboard.router)
app.include_router(keywords.router)
app.include_router(articles.router)
app.include_router(publishing.router)
app.include_router(search_console.router)
app.include_router(automations.router)
app.include_router(settings_router.router)
app.include_router(activity.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}

