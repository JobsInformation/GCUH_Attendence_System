import datetime
import os

import bcrypt
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# The database URL must come from the environment (Vercel -> Settings -> Environment Variables).
# Never hardcode it in source code.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


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
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"DB Init Error: {e}")

# Docs live under /api so the vercel.json rewrite (/api/(.*)) reaches them.
app = FastAPI(
    title="GCUH Attendance Backend",
    version="1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
router = APIRouter(prefix="/api")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- password helpers (bcrypt directly; no passlib) ----------
# Hashes created earlier with passlib's bcrypt scheme are standard $2b$ hashes,
# so existing users keep working.

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "teacher"


@router.get("/health")
def health():
    return {"status": "online", "system": "GCUH Attendance Backend with Neon DB"}


@router.post("/auth/register")
def register_teacher(user: UserCreate, db: Session = Depends(get_db)):
    if len(user.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password must be 72 bytes or fewer")
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    db_user = User(
        username=user.username,
        hashed_password=hash_password(user.password),
        role=user.role,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"status": "success", "message": f"{user.role.capitalize()} registered successfully"}


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    # The teacher page sends application/x-www-form-urlencoded; JSON is also accepted.
    username = None
    password = None
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            data = await request.json()
            username = data.get("username")
            password = data.get("password")
        except Exception:
            pass
    else:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    # TODO: this token is just the username, so anyone can forge it.
    # Replace with a signed JWT before relying on it to protect endpoints.
    return {"access_token": user.username, "token_type": "bearer", "role": user.role}


# ---------- placeholder endpoints (unchanged logic, now under /api) ----------

@router.post("/students/register")
def register_student():
    return {"status": "success", "message": "Student registration endpoint active"}


@router.post("/lecture/start")
def start_lecture():
    return {"status": "success", "lecture_id": 1, "token": "sample-qr-token"}


@router.get("/lecture/{lecture_id}/token")
def get_lecture_token(lecture_id: int):
    return {"lecture_id": lecture_id, "token": "sample-qr-token"}


@router.post("/attendance/check-in")
def check_in():
    return {"status": "success", "message": "Attendance recorded"}


@router.get("/teacher/reports/{lecture_id}")
def get_report(lecture_id: int):
    return {"lecture_id": lecture_id, "attendance": []}


@router.get("/teacher/reports/{lecture_id}/csv")
def get_report_csv(lecture_id: int):
    return {"status": "csv generated"}


app.include_router(router)
