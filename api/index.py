import os
import traceback
import uuid
from fastapi import FastAPI, Request, Depends
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
    err_msg = str(exc)
    return JSONResponse(
        status_code=500,
        content={"error": err_msg, "message": err_msg, "detail": err_msg, "traceback": tb.split("\n")}
    )

@app.api_route("/api/login", methods=["GET", "POST"])
@app.api_route("/login", methods=["GET", "POST"])
async def login_route(request: Request, db: Session = Depends(get_db)):
    if request.method == "GET":
        return {"message": "Login endpoint is active."}
    
    username, password = None, None
    try:
        body = await request.json()
        if isinstance(body, dict):
            username = body.get("username")
            password = body.get("password")
    except Exception:
        pass

    if not username or not password:
        return JSONResponse(status_code=400, content={"error": "Missing username or password", "message": "Missing username or password"})

    try:
        # Ensure users table exists and admin account is present
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    hashed_password VARCHAR(255) NOT NULL
                );
            """))
            
            # Check if admin exists
            res = conn.execute(text("SELECT count(*) FROM users WHERE username = 'admin'")).fetchone()
            if not res or res[0] == 0:
                hashed = bcrypt.hashpw("securepassword123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                conn.execute(text("""
                    INSERT INTO users (username, hashed_password) VALUES ('admin', :pwd)
                    ON CONFLICT (username) DO UPDATE SET hashed_password = :pwd;
                """), {"pwd": hashed})

        user = db.execute(
            text("SELECT id, username, hashed_password FROM users WHERE username = :uname"),
            {"uname": username.strip()}
        ).fetchone()

        if not user or not bcrypt.checkpw(password.encode("utf-8"), user[2].encode("utf-8")):
            return JSONResponse(status_code=401, content={"error": "Invalid username or password", "message": "Invalid username or password"})

        return {"access_token": user[1], "token_type": "bearer", "success": True}
    except Exception as e:
        err = str(e)
        return JSONResponse(status_code=500, content={"error": err, "message": err})

@app.api_route("/api/lecture/start", methods=["GET", "POST"])
async def start_lecture_route(request: Request, db: Session = Depends(get_db)):
    try:
        lecture_title = f"Lecture-{uuid.uuid4().hex[:6].upper()}"
        secure_token = str(uuid.uuid4())

        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS lectures (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(100) NOT NULL,
                    token VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(
                text("INSERT INTO lectures (title, token) VALUES (:title, :token)"),
                {"title": lecture_title, "token": secure_token}
            )

        return {
            "success": True,
            "lecture_id": lecture_title,
            "secure_token": secure_token,
            "token": secure_token,
            "message": "Lecture started successfully"
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.api_route("/api/lecture/{lecture_id}/token", methods=["GET", "POST"])
async def get_specific_lecture_token(lecture_id: str, db: Session = Depends(get_db)):
    try:
        row = db.execute(
            text("SELECT token FROM lectures WHERE title = :tid ORDER BY id DESC LIMIT 1"),
            {"tid": lecture_id}
        ).fetchone()

        if not row:
            new_token = str(uuid.uuid4())
            with engine.begin() as conn:
                conn.execute(
                    text("INSERT INTO lectures (title, token) VALUES (:title, :token)"),
                    {"title": lecture_id, "token": new_token}
                )
            return {"success": True, "token": new_token, "secure_token": new_token}

        return {"success": True, "token": row[0], "secure_token": row[0]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.api_route("/api/student/lookup/{roll_number}", methods=["GET"])
def lookup_student(roll_number: str, db: Session = Depends(get_db)):
    try:
        row = db.execute(
            text("SELECT roll_number, full_name, department, COALESCE(student_status, 'Active') FROM students WHERE roll_number = :rno"),
            {"rno": roll_number.strip().upper()}
        ).fetchone()

        if not row:
            return JSONResponse(status_code=404, content={"found": False, "message": "Roll number not found in official batch roster."})

        return {
            "found": True,
            "roll_number": row[0],
            "name": row[1],
            "department": row[2] or "Information Technology"
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.api_route("/api/attendance/check-in", methods=["GET", "POST"])
async def student_check_in(request: Request, db: Session = Depends(get_db)):
    if request.method == "GET":
        return {"message": "Check-in endpoint active."}
    
    roll_number, token = None, None
    try:
        body = await request.json()
        if isinstance(body, dict):
            roll_number = body.get("roll_number") or body.get("rollNumber")
            token = body.get("token") or body.get("secure_token")
    except Exception:
        pass

    if not roll_number or not token:
        return JSONResponse(status_code=400, content={"error": "Missing roll number or token"})

    try:
        student_row = db.execute(
            text("SELECT full_name, department FROM students WHERE roll_number = :rno"),
            {"rno": roll_number.strip().upper()}
        ).fetchone()

        if not student_row:
            return JSONResponse(status_code=401, content={"success": False, "message": "Roll number not registered in batch roster."})

        lecture_row = db.execute(
            text("SELECT title FROM lectures WHERE token = :tok ORDER BY id DESC LIMIT 1"),
            {"tok": token.strip()}
        ).fetchone()

        if not lecture_row:
            lecture_row = db.execute(
                text("SELECT title FROM lectures ORDER BY id DESC LIMIT 1")
            ).fetchone()

        lecture_id = lecture_row[0] if lecture_row else "Lecture-General"

        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    lecture_id VARCHAR(100),
                    roll_number VARCHAR(50),
                    name VARCHAR(100),
                    department VARCHAR(100),
                    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                ALTER TABLE attendance ADD COLUMN IF NOT EXISTS department VARCHAR(100);
            """))
            
            # Check duplicate
            existing = db.execute(
                text("SELECT id FROM attendance WHERE lecture_id = :lid AND roll_number = :rno"),
                {"lid": lecture_id, "rno": roll_number.strip().upper()}
            ).fetchone()

            if existing:
                return {"success": True, "message": "Attendance already marked!", "lecture_id": lecture_id}

            conn.execute(
                text("INSERT INTO attendance (lecture_id, roll_number, name, department) VALUES (:lid, :rno, :name, :dept)"),
                {"lid": lecture_id, "rno": roll_number.strip().upper(), "name": student_row[0], "dept": student_row[1] or "Information Technology"}
            )

        return {"success": True, "message": "Attendance marked successfully!", "lecture_id": lecture_id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.api_route("/api/teacher/reports/{lecture_id}", methods=["GET", "POST"])
async def teacher_reports(lecture_id: str, db: Session = Depends(get_db)):
    try:
        if lecture_id == "undefined" or not lecture_id:
            return {"attendance_list": [], "count": 0, "success": True}

        records = db.execute(
            text("SELECT roll_number, name, department, time FROM attendance WHERE lecture_id = :lid ORDER BY time DESC"),
            {"lid": lecture_id}
        ).fetchall()
        
        feed = [{"roll_number": r[0], "name": r[1], "department": r[2], "time": str(r[3])} for r in records]
        return {"attendance_list": feed, "attendance": feed, "count": len(feed), "success": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
