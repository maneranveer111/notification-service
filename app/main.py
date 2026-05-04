from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug
    )

@app.get("/health")
def health():
    return {"status" : "ok", "service" : settings.app_name}

@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    version = db.execute(text("SELECT version();")).scalar()
    return {"status": "ok", "db" : "connected", "version" : version}