import os
import traceback
import uuid
from fastapi import FastAPI, Request, Depends, HTTPException
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

@app.api_route("/api/health", methods=["GET", "POST"])
@app.api_route("/health", methods=["GET", "POST"])
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected successfully"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.api_route("/login", methods=["GET", "POST"])
@app.api_route("/api/login", methods=["GET", "POST"])
async def login_route(request: Request, db: Session = Depends(get_db)):
    if request.method == "GET":
        return {"message": "Login endpoint is active. Please send a POST request with username and password."}
    
    username, password = None, None
    try:
        body = await request.json()
        if isinstance(body, dict):
            username = body.get("username")
            password = body.get("password")
    except Exception:
        pass

    if not username or not password:
        try:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")
        except Exception:
            pass

    if not username or not password:
        return JSONResponse(status_code=400, content={"detail": "Missing username or password"})

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lectures (
                    id SERIAL PRIMARY KEY,
                    lecture_id VARCHAR(100) UNIQUE NOT NULL,
                    teacher_id VARCHAR(100),
                    secure_token VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    lecture_id VARCHAR(100),
                    roll_number VARCHAR(50),
                    name VARCHAR(100),
                    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

@app.api_route("/start-lecture", methods=["GET", "POST"])
@app.api_route("/api/start-lecture", methods=["GET", "POST"])
async def start_lecture_route(request: Request, db: Session = Depends(get_db)):
    try:
        data = {}
        try:
            data = await request.json()
        except Exception:
            pass

        teacher_id = data.get("teacher_id", "IT-Instructor-01")
        lecture_id = f"LEC-{uuid.uuid4().hex[:8].upper()}"
        secure_token = str(uuid.uuid4())

        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS lectures (
                    id SERIAL PRIMARY KEY,
                    lecture_id VARCHAR(100) UNIQUE NOT NULL,
                    teacher_id VARCHAR(100),
                    secure_token VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(
                text("INSERT INTO lectures (lecture_id, teacher_id, secure_token) VALUES (:lid, :tid, :tok)"),
                {"lid": lecture_id, "tid": teacher_id, "tok": secure_token}
            )

        return {
            "success": True,
            "lecture_id": lecture_id,
            "secure_token": secure_token,
            "message": "Lecture started successfully"
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})

@app.api_route("/attendance-feed", methods=["GET", "POST"])
@app.api_route("/api/attendance-feed", methods=["GET", "POST"])
def attendance_feed_route(lecture_id: str = None, db: Session = Depends(get_db)):
    try:
        if lecture_id:
            records = db.execute(
                text("SELECT roll_number, name, time FROM attendance WHERE lecture_id = :lid ORDER BY time DESC"),
                {"lid": lecture_id}
            ).fetchall()
        else:
            records = db.execute(
                text("SELECT roll_number, name, time FROM attendance ORDER BY time DESC LIMIT 50")
            ).fetchall()
        
        feed = [{"roll_number": r[0], "name": r[1], "time": str(r[2])} for r in records]
        return {"attendance": feed, "count": len(feed)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
