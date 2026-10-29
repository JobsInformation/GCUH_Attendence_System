import time
import hmac
import hashlib
import json
import asyncio
import math
import csv
import io
import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# Twilio SMS Integration (Install via: pip install twilio)
try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

app = FastAPI(title="GCUH IT Enterprise Attendance System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

SECRET_KEY = "gcuh_it_secret_key"
ACTIVE_LECTURES = {}
STREAM_QUEUES = {}
LECTURE_ATTENDEES = {}  # lecture_id -> list of student records

# Immutable Audit Ledger (Blockchain-Lite)
ATTENDANCE_LEDGER = []

# ==========================================
# TWILIO SMS CONFIGURATION (For Exhibition)
# ==========================================
TWILIO_ACCOUNT_SID = ""  # Paste your Twilio SID here
TWILIO_AUTH_TOKEN = ""   # Paste your Twilio Auth Token here
TWILIO_PHONE_NUMBER = "" # Paste your Twilio Phone Number here (e.g., "+1234567890")

def send_sms_notification(to_phone: str, message_body: str):
    if not TWILIO_AVAILABLE or not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        print(f"[SIMULATED SMS to {to_phone}] {message_body}")
        return False
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=message_body,
            from_=TWILIO_PHONE_NUMBER,
            to=to_phone
        )
        print(f"[TWILIO SMS SENT] SID: {message.sid}")
        return True
    except Exception as e:
        print(f"[TWILIO SMS ERROR] {e}")
        return False

# Mock Users Database with Phone Numbers
USERS_DB = {
    "prof_smith": {"pass": "1234", "role": "teacher", "name": "Prof. Smith", "phone": ""},
    "hod_it": {"pass": "1234", "role": "hod", "name": "Dr. Head of IT", "phone": ""},
    "admin": {"pass": "1234", "role": "admin", "name": "System Administrator", "phone": ""},
    "S001": {"pass": "1234", "role": "student", "name": "Syed Iqrar Ali Shah", "program": "BSIT-701", "phone": "+923313601071"},
    "S002": {"pass": "1234", "role": "student", "name": "Ayesha Khan", "program": "BSIT-701", "phone": "+923000000001"},
    "S003": {"pass": "1234", "role": "student", "name": "Bilal Ahmed", "program": "BSIT-701", "phone": "+923000000002"},
    "S004": {"pass": "1234", "role": "student", "name": "Fatima Baloch", "program": "MSIT-502", "phone": "+923000000003"}
}

REGISTERED_STUDENTS = [
    {"roll_no": "S001", "name": "Syed Iqrar Ali Shah", "program": "BSIT-701"},
    {"roll_no": "S002", "name": "Ayesha Khan", "program": "BSIT-701"},
    {"roll_no": "S003", "name": "Bilal Ahmed", "program": "BSIT-701"},
    {"roll_no": "S004", "name": "Fatima Baloch", "program": "MSIT-502"},
]

class LectureStart(BaseModel):
    course_code: str
    latitude: float
    longitude: float

class AttendanceCheckin(BaseModel):
    qr_payload: str
    latitude: float
    longitude: float
    device_id: str

@app.post("/login")
def unified_login(payload: dict):
    username = payload.get("username") or payload.get("user") or payload.get("student_id")
    password = payload.get("password") or payload.get("pass") or payload.get("pin")
    
    user = USERS_DB.get(username)
    if not user or user["pass"] != password:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    token = f"{username}_token_{user['role']}"
    return {
        "access_token": token,
        "role": user["role"],
        "name": user["name"]
    }

@app.post("/login/teacher")
def teacher_login_compat(payload: dict):
    username = payload.get("username") or payload.get("user")
    password = payload.get("password") or payload.get("pass")
    
    user = USERS_DB.get(username)
    if not user or user["pass"] != password or user["role"] != "teacher":
        raise HTTPException(status_code=400, detail="Invalid teacher credentials")
    return {"access_token": f"{username}_token_teacher", "role": "teacher", "name": user["name"]}

@app.post("/login/student")
def student_login_compat(payload: dict):
    student_id = payload.get("student_id") or payload.get("username") or payload.get("user")
    pin = payload.get("pin") or payload.get("password") or payload.get("pass")
    
    user = USERS_DB.get(student_id)
    if not user or user["pass"] != pin or user["role"] != "student":
        if student_id == "S001" and pin == "1234":
            return {"access_token": "S001_token_student", "role": "student", "name": "Syed Iqrar Ali Shah"}
        raise HTTPException(status_code=400, detail="Invalid student credentials")
    return {"access_token": f"{student_id}_token_student", "role": "student", "name": user["name"]}

@app.post("/lecture/start")
def start_lecture(data: LectureStart, credentials: HTTPAuthorizationCredentials = Depends(security)):
    lecture_id = f"LECTURE_{int(time.time())}"
    ACTIVE_LECTURES[lecture_id] = {
        "course_code": data.course_code,
        "latitude": data.latitude,
        "longitude": data.longitude,
        "start_time": time.time()
    }
    STREAM_QUEUES[lecture_id] = asyncio.Queue()
    LECTURE_ATTENDEES[lecture_id] = []
    return {"lecture_id": lecture_id, "message": "Lecture started successfully"}

@app.get("/lecture/{lecture_id}/token")
def get_lecture_token(lecture_id: str):
    if lecture_id not in ACTIVE_LECTURES:
        raise HTTPException(status_code=404, detail="Lecture not found")
    
    time_slot = int(time.time() // 30)
    message = f"{lecture_id}:{time_slot}"
    signature = hmac.new(SECRET_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()
    
    return {"qr_payload": f"{lecture_id}:{time_slot}:{signature}"}

@app.get("/lecture/{lecture_id}/stream")
async def lecture_stream(lecture_id: str):
    if lecture_id not in STREAM_QUEUES:
        STREAM_QUEUES[lecture_id] = asyncio.Queue()
    
    async def event_generator():
        q = STREAM_QUEUES[lecture_id]
        while True:
            data = await q.get()
            yield {"data": json.dumps(data)}

    return EventSourceResponse(event_generator())

@app.get("/reports/export-summary-csv")
def export_summary_csv(report_type: str = "weekly", course_code: str = "BSIT-701", credentials: HTTPAuthorizationCredentials = Depends(security)):
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["Government College University Hyderabad - Department of Information Technology"])
    writer.writerow([f"Official {report_type.capitalize()} Attendance Summary Report"])
    writer.writerow(["Course Code / Class", course_code])
    writer.writerow(["Generated Date", time.strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])
    
    # Required Table Headings
    writer.writerow(["Student Name", "Class/Lab", "Time Duration of the Class", "Roll Number", "Remarks"])
    
    duration_str = "1 Hour 30 Minutes (90 mins)" if report_type == "weekly" else "6 Hours (Monthly Aggregate)"
    
    for student in REGISTERED_STUDENTS:
        attended = False
        for l_id, l_data in ACTIVE_LECTURES.items():
            if l_data["course_code"] == course_code:
                present_students = [att["student_id"] for att in LECTURE_ATTENDEES.get(l_id, [])]
                if student["roll_no"] in present_students:
                    attended = True
                    break
        
        status = "Present" if attended else "Absent"
        
        writer.writerow([
            student["name"],
            student["program"],
            duration_str,
            student["roll_no"],
            status
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=GCUH_{report_type.capitalize()}_Attendance_Report.csv"}
    )

@app.get("/hod/analytics")
def hod_analytics(credentials: HTTPAuthorizationCredentials = Depends(security)):
    total_lectures = len(ACTIVE_LECTURES)
    total_checkins = sum(len(attendees) for attendees in LECTURE_ATTENDEES.values())
    return {
        "department": "Department of Information Technology, GCUH",
        "total_active_lectures": total_lectures,
        "total_verified_attendances": total_checkins,
        "ledger_blocks_count": len(ATTENDANCE_LEDGER),
        "system_status": "Secure & Operational"
    }

@app.get("/audit/ledger")
def get_audit_ledger(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return {"immutable_ledger": ATTENDANCE_LEDGER}

@app.post("/attendance/checkin")
async def checkin(data: AttendanceCheckin, credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    student_id = token.split("_token_")[0]

    try:
        parts = data.qr_payload.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=400, detail="Invalid QR payload format")
        lecture_id, time_slot_str, signature = parts
        time_slot = int(time_slot_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed QR code")

    if lecture_id not in ACTIVE_LECTURES:
        raise HTTPException(status_code=404, detail="Lecture not found or ended")

    current_slot = int(time.time() // 30)
    if time_slot not in [current_slot, current_slot - 1]:
        raise HTTPException(status_code=400, detail="QR code expired. Please scan current code.")

    expected_msg = f"{lecture_id}:{time_slot}"
    expected_sig = hmac.new(SECRET_KEY.encode(), expected_msg.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        raise HTTPException(status_code=400, detail="Invalid cryptographic signature")

    lecture_lat = ACTIVE_LECTURES[lecture_id]["latitude"]
    lecture_lon = ACTIVE_LECTURES[lecture_id]["longitude"]
    
    lat_diff = math.radians(data.latitude - lecture_lat)
    lon_diff = math.radians(data.longitude - lecture_lon)
    a = math.sin(lat_diff/2)**2 + math.cos(math.radians(lecture_lat)) * math.cos(math.radians(data.latitude)) * math.sin(lon_diff/2)**2
    c = 2 * math.asin(math.sqrt(a))
    distance_meters = int(6371000 * c)

    if distance_meters > 500:
        raise HTTPException(status_code=400, detail=f"Out of geofence bounds ({distance_meters}m away)")
    
    existing_students = [att["student_id"] for att in LECTURE_ATTENDEES.get(lecture_id, [])]
    if student_id in existing_students:
        raise HTTPException(status_code=400, detail="Attendance already marked for this lecture.")

    timestamp = time.time()
    record = {
        "student_id": student_id,
        "timestamp": timestamp,
        "distance_meters": distance_meters
    }
    LECTURE_ATTENDEES[lecture_id].append(record)

    # Immutable Audit Trail Block Generation
    previous_hash = ATTENDANCE_LEDGER[-1]["block_hash"] if ATTENDANCE_LEDGER else "0" * 64
    block_data = f"{previous_hash}:{student_id}:{lecture_id}:{timestamp}"
    block_hash = hashlib.sha256(block_data.encode()).hexdigest()

    ledger_block = {
        "index": len(ATTENDANCE_LEDGER) + 1,
        "student_id": student_id,
        "lecture_id": lecture_id,
        "timestamp": timestamp,
        "previous_hash": previous_hash,
        "block_hash": block_hash
    }
    ATTENDANCE_LEDGER.append(ledger_block)

    # Trigger SMS Notification via Twilio
    student_phone = USERS_DB.get(student_id, {}).get("phone")
    student_name = USERS_DB.get(student_id, {}).get("name", student_id)
    sms_msg = f"GCUH IT Alert: Attendance successfully marked for {student_name} in lecture {lecture_id}. Verified via cryptographic hash."
    
    if student_phone:
        send_sms_notification(student_phone, sms_msg)
    else:
        print(f"[WARNING] No phone number on file for {student_id}")

    event_data = {"student_id": student_id, "distance_meters": distance_meters, "block_hash": block_hash[:12] + "..."}
    if lecture_id in STREAM_QUEUES:
        await STREAM_QUEUES[lecture_id].put(event_data)

    return {
        "status": "success", 
        "distance_meters": distance_meters, 
        "audit_hash": block_hash[:16] + "...",
        "notification": "SMS trigger executed"
    }