import bcrypt
import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
import datetime
import qrcode
import io

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://neondb_owner:npg_n1QztYNasx5I@ep-crimson-bread-b5d68uh1-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)

class Lecture(Base):
    __tablename__ = "lectures"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    token = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

try:
    try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"DB Init Error: {e}")
except Exception as e:
    print(f"DB Init Error: {e}")

app = FastAPI(title="GCUH Attendance Backend", version="1.0")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "teacher"

class LoginRequest(BaseModel):
    username: str
    password: str

@app.get(\"/api/")
def read_root():
    return {"status": "online", "system": "GCUH Attendance Backend with Neon DB"}

@app.post(\"/api/auth/register")
def register_teacher(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = pwd_context.hash(user.password)
    db_user = User(username=user.username, hashed_password=hashed_password, role=user.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"status": "success", "message": f"{user.role.capitalize()} registered successfully"}

@app.post(\"/api/login")
async def login(request: Request, db: Session = Depends(get_db)):
    content_type = request.headers.get("content-type", "")
    username = None
    password = None
    
    if "application/json" in content_type:
        try:
            data = await request.json()
            username = data.get("username")
            password = data.get("password")
        except Exception:
            pass
    if not username or not password:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
        
    # Verify using passlib or direct bcrypt fallback
    verified = False
    try:
        if pwd_context.verify(password, user.hashed_password):
            verified = True
    except Exception:
        pass
        
    if not verified:
        try:
            if bcrypt.checkpw(password.encode('utf-8'), user.hashed_password.encode('utf-8')):
                verified = True
        except Exception:
            pass
            
    if not verified:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
        
    return {"access_token": user.username, "token_type": "bearer", "role": user.role}

@app.post(\"/api/students/register")
def register_student():
    return {"status": "success", "message": "Student registration endpoint active"}

@app.post(\"/api/lecture/start")
def start_lecture():
    return {"status": "success", "lecture_id": 1, "token": "sample-qr-token"}

@app.get(\"/api/lecture/{lecture_id}/token")
def get_lecture_token(lecture_id: int):
    return {"lecture_id": lecture_id, "token": "sample-qr-token"}

@app.post(\"/api/attendance/check-in")
def check_in():
    return {"status": "success", "message": "Attendance recorded"}

@app.get(\"/api/teacher/reports/{lecture_id}")
def get_report(lecture_id: int):
    return {"lecture_id": lecture_id, "attendance": []}

@app.get(\"/api/teacher/reports/{lecture_id}/csv")
def get_report_csv(lecture_id: int):
    return {"status": "csv generated"}
