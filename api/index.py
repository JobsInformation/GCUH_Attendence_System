import os
import traceback
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import bcrypt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_n1QztYNasx5I@ep-crimson-bread-b5d68uh1-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

if DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": tb.split("\n")}
    )

@app.get("/api/health")
@app.get("/health")
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected successfully"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.get("/login")
@app.get("/api/login")
def login_get_info():
    return {"message": "Login endpoint is active. Please send a POST request with username and password."}

@app.post("/login")
@app.post("/api/login")
async def login_post(request: Request, db: Session = Depends(get_db)):
    username = None
    password = None

    # 1. Try parsing JSON body
    try:
        body = await request.json()
        if isinstance(body, dict):
            username = body.get("username")
            password = body.get("password")
    except Exception:
        pass

    # 2. Fallback to Form Data if JSON failed or was empty
    if not username or not password:
        try:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")
        except Exception:
            pass

    if not username or not password:
        return JSONResponse(status_code=400, content={"detail": "Missing username or password in payload"})

    try:
        # Lazily ensure users table exists and seed admin user
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL
                );
            """))
            res = conn.execute(text("SELECT id FROM users WHERE username = 'admin'")).fetchone()
            if not res:
                hashed = bcrypt.hashpw("securepassword123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                conn.execute(
                    text("INSERT INTO users (username, hashed_password) VALUES (:uname, :pwd)"),
                    {"uname": "admin", "pwd": hashed}
                )

        user = db.execute(
            text("SELECT id, username, hashed_password FROM users WHERE username = :uname"),
            {"uname": username}
        ).fetchone()

        if not user or not bcrypt.checkpw(password.encode("utf-8"), user.hashed_password.encode("utf-8")):
            return JSONResponse(status_code=401, content={"detail": "Invalid username or password"})

        return {"access_token": user.username, "token_type": "bearer"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
