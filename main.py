cat << 'EOF' > main.py
import time
import io
import base64
import qrcode
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="GCUH Attendance System")

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
    return {"status": "online", "system": "GCUH Attendance Backend"}

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
        return {"status": "error", "detail": "Invalid attendance token format"}
    
    try:
        *_, token_time_str = data.token.rsplit("-", 1)
        token_time_window = int(token_time_str)
        current_time_window = int(time.time() // 10)
        
        if current_time_window - token_time_window > 1:
            return {"status": "error", "detail": "QR Code has expired. Please scan the current code."}
    except Exception as e:
        return {"status": "error", "detail": f"Malformed token: {str(e)}"}

    return {
        "status": "success", 
        "message": f"Attendance recorded for {data.student_roll}!"
    }
EOF
