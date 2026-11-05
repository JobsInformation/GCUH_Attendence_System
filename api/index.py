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
    
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        return {"status": "error", "message": "DATABASE_URL environment variable is missing"}
        
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "healthy", "database": "connected successfully"}
