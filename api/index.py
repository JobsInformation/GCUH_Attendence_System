import os
import traceback
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "traceback": tb.split("\n")
        }
    )

@app.get("/api/health")
@app.get("/health")
def health_check():
    import bcrypt
    import psycopg2
    from sqlalchemy import create_engine, text
    
    RAW_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_n1QztYNasx5I@ep-crimson-bread-b5d68uh1-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
    
    # Ensure SQLAlchemy explicitly uses psycopg2 instead of trying to load psycopg v3
    if RAW_URL.startswith("postgresql://") and "+psycopg2" not in RAW_URL:
        DATABASE_URL = RAW_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    else:
        DATABASE_URL = RAW_URL

    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "healthy", "database": "connected successfully"}
