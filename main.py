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

@app.get("/")
def read_root():
    return {"status": "online", "system": "GCUH Attendance Backend with Neon DB"}

@app.post("/auth/register")
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

@app.post("/login")
def login(form_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    return {"access_token": user.username, "token_type": "bearer", "role": user.role}

@app.post("/students/register")
def register_student():
    return {"status": "success", "message": "Student registration endpoint active"}

@app.post("/lecture/start")
def start_lecture():
    return {"status": "success", "lecture_id": 1, "token": "sample-qr-token"}

@app.get("/lecture/{lecture_id}/token")
def get_lecture_token(lecture_id: int):
    return {"lecture_id": lecture_id, "token": "sample-qr-token"}

@app.post("/attendance/check-in")
def check_in():
    return {"status": "success", "message": "Attendance recorded"}

@app.get("/teacher/reports/{lecture_id}")
def get_report(lecture_id: int):
    return {"lecture_id": lecture_id, "attendance": []}

@app.get("/teacher/reports/{lecture_id}/csv")
def get_report_csv(lecture_id: int):
    return {"status": "csv generated"}
