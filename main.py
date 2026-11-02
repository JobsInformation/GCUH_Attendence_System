cat << 'EOF' > main.py
import time
import io
import base64
import os
import qrcode
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# --- DATABASE SETUP (Neon PostgreSQL) ---
DATABASE_URL = "postgresql://neondb_owner:npg_n1QztYNasx5I@ep-crimson-bread-b5d68uh1-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AttendanceModel(Base):
    __tablename__ = "attendance_records"
    
    id = Column(String, primary_key=True, index=True)
    student_roll = Column(String, index=True)
    lecture_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Automatically create tables in Neon on startup
Base.metadata.create_all(bind=engine)

# --- FASTAPI APP ---
app = FastAPI(title="GCUH Attendance System with Neon DB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AttendanceCheckIn(BaseModel):
    student_roll: str
    token: str

@app.get("/")
def read_root():
    return {"status": "online", "system": "GCUH Attendance Backend with Neon DB"}

@app.post("/login")
def login(data: dict = None):
    return {
        "status": "success",
        "message": "Authenticated successfully",
        "access_token": "mock-jwt-token-gcuh",
        "token_type": "bearer",
        "role": "teacher"
    }

@app.post("/lecture/start")
def start_lecture(data: dict = None):
    lecture_id = f"LECTURE_{int(time.time())}"
    return {
        "status": "success",
        "lecture_id": lecture_id,
        "message": "Lecture started successfully"
    }

@app.get("/lecture/{lecture_id}/token")
def get_lecture_token(lecture_id: str):
    token_val = f"GCUH-{lecture_id}-{int(time.time() // 10)}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(token_val)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    img_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    
    return {
        "lecture_id": lecture_id,
        "token": token_val,
        "qr_image": f"data:image/png;base64,{img_base64}"
    }

@app.post("/attendance/check-in")
def check_in(data: AttendanceCheckIn):
    if not data.token.startswith("GCUH-"):
        raise HTTPException(status_code=400, detail="Invalid attendance token format")
    
    try:
        parts = data.token.split("-")
        token_time_str = parts[-1]
        lecture_id = "-".join(parts[1:-1])
        
        token_time_window = int(token_time_str)
        current_time_window = int(time.time() // 10)
        
        # Allow current window or immediate previous window (10s grace period)
        if current_time_window - token_time_window > 1:
            raise HTTPException(status_code=400, detail="QR Code has expired. Please scan the current code.")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Malformed token: {str(e)}")

    # Save to Neon Database
    db = SessionLocal()
    try:
        existing_record = db.query(AttendanceModel).filter(
            AttendanceModel.student_roll == data.student_roll,
            AttendanceModel.lecture_id == lecture_id
        ).first()

        if existing_record:
            return {"status": "success", "message": f"Welcome back, {data.student_roll}! Attendance already recorded."}

        record_id = f"{data.student_roll}_{lecture_id}"
        new_attendance = AttendanceModel(
            id=record_id,
            student_roll=data.student_roll,
            lecture_id=lecture_id
        )
        db.add(new_attendance)
        db.commit()
    except Exception as db_err:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(db_err)}")
    finally:
        db.close()

    return {
        "status": "success", 
        "message": f"Attendance successfully recorded and saved to Neon DB for {data.student_roll}!"
    }
EOF
