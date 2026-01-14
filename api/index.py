"""
SlotlyCare Backend - FastAPI Unified API
All endpoints centralized in one file for Vercel serverless deployment
UPDATED: Now includes Stripe integration for payments and authentication
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import sys
import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta, time
from openai import OpenAI
import stripe

# Add parent directory to path to import sheets_client
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from sheets_client import SheetsClient

# Initialize FastAPI app
app = FastAPI(
    title="SlotlyCare API",
    description="Healthcare appointment scheduling system with AI-powered slot generation",
    version="2.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
openai_client = OpenAI()

# Initialize Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# ==================== PYDANTIC MODELS ====================

class SlotModel(BaseModel):
    date: str
    time: str
    status: str = "available"

class DoctorModel(BaseModel):
    id: str
    name: str
    specialty: Optional[str] = ""
    address: str
    phone: str
    email: str
    logo_url: Optional[str] = ""
    color: str = "#3B82F6"
    language: str
    welcome_message: Optional[str] = ""
    link: str
    slots: Optional[List[SlotModel]] = []
    customer_id: Optional[str] = ""  # Stripe customer ID

class AppointmentModel(BaseModel):
    doctor_id: str
    patient_name: str
    patient_email: str
    patient_phone: str
    date: str
    time: str
    notes: Optional[str] = ""

class ScheduleRequest(BaseModel):
    schedule_text: str

class Slot(BaseModel):
    date: str
    time: str
    status: str = "available"

# Stripe and Auth models
class CreateCheckoutRequest(BaseModel):
    success_url: str
    cancel_url: str

class SetPasswordRequest(BaseModel):
    customer_id: str
    password: str

class LoginRequest(BaseModel):
    customer_id: str
    password: str

class ScheduleResponse(BaseModel):
    success: bool
    slots: List[Slot]
    total_slots: int
    error: Optional[str] = None

# ==================== SCHEDULE FUNCTIONS ====================

def validate_schedule_text(text: str) -> Optional[str]:
    """Valida o texto de entrada para evitar abuso e garantir o mínimo de qualidade."""
    text_lower = text.lower().strip()
    if len(text_lower) < 15:
        return "Schedule text is too short. Please provide more details (minimum 15 characters)."
    
    blocked_keywords = ["recipe", "receita", "bolo", "cake", "poem", "poema", "piada", "joke"]
    if any(word in text_lower for word in blocked_keywords):
        return "The text does not appear to be schedule-related. Please enter only information about your work hours."
    
    return None

def get_schedule_structure_from_openai(text: str) -> dict:
    """Chama a API da OpenAI para extrair uma estrutura FLEXÍVEL de horários."""
    today = datetime.now().date()
    end_date = today + timedelta(days=180)
    
    system_prompt = f'''You are a medical scheduling assistant. Today is {today.strftime("%Y-%m-%d")}.

Your task: Generate a complete schedule for the next 180 days (until {end_date.strftime("%Y-%m-%d")}) based on the doctor's instructions.

IMPORTANT MULTILINGUAL SUPPORT:
- Accept input in ANY language (English, Portuguese, Spanish, French, German, Italian, etc.)
- User may write "Segunda a sexta" (Portuguese) or "Monday to Friday" (English)
- User may write "Terça" or "Tuesday", "Sábado" or "Saturday"
- Detect the language and interpret accordingly
- ALWAYS return JSON in English format (day names in English)

Day name translations:
- Monday = Segunda, Lunes, Lundi, Montag, Lunedì
- Tuesday = Terça, Martes, Mardi, Dienstag, Martedì
- Wednesday = Quarta, Miércoles, Mercredi, Mittwoch, Mercoledì
- Thursday = Quinta, Jueves, Jeudi, Donnerstag, Giovedì
- Friday = Sexta, Viernes, Vendredi, Freitag, Venerdì
- Saturday = Sábado, Samedi, Samstag, Sabato
- Sunday = Domingo, Dimanche, Sonntag, Domenica

Handle ALL types of requests:
- Regular weekly schedules
- Blocked dates (vacations, conferences, specific weeks)
- Day-specific hours
- Partial day blocks
- Breaks and lunch hours
- Any other scheduling instruction

Return JSON with this structure:
{{
  "schedule": {{
    "default": {{
      "days": ["Monday", "Tuesday", ...],
      "start_time": "09:00",
      "end_time": "17:00",
      "slot_duration_minutes": 30,
      "breaks": [{{"start": "12:00", "end": "13:00"}}]
    }},
    "overrides": [
      {{"day": "Saturday", "start_time": "08:00", "end_time": "12:00"}}
    ],
    "blocked_dates": ["2026-03-17", "2026-03-18"],
    "blocked_date_ranges": [
      {{"start": "2026-12-20", "end": "2026-01-05", "reason": "vacation"}}
    ]
  }}
}}

Rules:
- ALWAYS use English day names in output: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday
- Times in 24h format HH:MM
- Dates in YYYY-MM-DD format
- If text mentions weeks (third week of March / terceira semana de março), calculate exact dates
- If text says "block", "bloquear", "bloquer" - add to blocked_dates
- If different hours per day - add to overrides
- If no specific duration mentioned, use 30 minutes
- Return ONLY valid JSON'''

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def generate_slots(structure: dict) -> List[Slot]:
    """Gera slots baseado em estrutura FLEXÍVEL com suporte a exceções."""
    slots = []
    today = datetime.now().date()
    end_date = today + timedelta(days=180)
    current_date = today

    schedule_data = structure.get("schedule", structure)
    default_config = schedule_data.get("default", schedule_data)
    overrides = schedule_data.get("overrides", [])
    blocked_dates = set(schedule_data.get("blocked_dates", []))
    blocked_ranges = schedule_data.get("blocked_date_ranges", [])
    
    # Parse blocked ranges
    for range_info in blocked_ranges:
        start = datetime.strptime(range_info["start"], "%Y-%m-%d").date()
        end = datetime.strptime(range_info["end"], "%Y-%m-%d").date()
        current = start
        while current <= end:
            blocked_dates.add(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
    
    # Day mapping
    day_mapping = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6
    }
    
    # Default config
    default_days = [day_mapping[d] for d in default_config.get("days", [])]
    default_start = time.fromisoformat(default_config.get("start_time", "09:00"))
    default_end = time.fromisoformat(default_config.get("end_time", "17:00"))
    default_duration = default_config.get("slot_duration_minutes", 30)
    default_breaks = default_config.get("breaks", [])
    
    # Process overrides by day
    day_overrides = {}
    for override in overrides:
        day_name = override.get("day")
        if day_name in day_mapping:
            day_overrides[day_name] = override
    
    # Generate slots day by day
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        
        # Skip blocked dates
        if date_str in blocked_dates:
            current_date += timedelta(days=1)
            continue
        
        weekday = current_date.weekday()
        day_name = [k for k, v in day_mapping.items() if v == weekday][0]
        
        # Check if this day has override
        if day_name in day_overrides:
            override = day_overrides[day_name]
            start_time = time.fromisoformat(override.get("start_time", "09:00"))
            end_time = time.fromisoformat(override.get("end_time", "17:00"))
            duration = override.get("slot_duration_minutes", default_duration)
            breaks = override.get("breaks", [])
        elif weekday in default_days:
            start_time = default_start
            end_time = default_end
            duration = default_duration
            breaks = default_breaks
        else:
            current_date += timedelta(days=1)
            continue
        
        # Parse breaks
        break_intervals = []
        for b in breaks:
            break_intervals.append((
                time.fromisoformat(b["start"]),
                time.fromisoformat(b["end"])
            ))
        
        # Generate slots for this day
        current_slot_time = datetime.combine(current_date, start_time)
        end_of_day = datetime.combine(current_date, end_time)
        slot_delta = timedelta(minutes=duration)
        
        while current_slot_time < end_of_day:
            slot_end = current_slot_time + slot_delta
            if slot_end > end_of_day:
                break
            
            # Check breaks
            in_break = False
            for break_start, break_end in break_intervals:
                if not (current_slot_time.time() >= break_end or slot_end.time() <= break_start):
                    in_break = True
                    break
            
            if not in_break:
                slots.append(Slot(
                    date=current_slot_time.strftime("%Y-%m-%d"),
                    time=current_slot_time.strftime("%H:%M")
                ))
            
            current_slot_time = slot_end
        
        current_date += timedelta(days=1)
    
    return slots

# ==================== ENDPOINTS ====================

@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {
        "success": True,
        "message": "SlotlyMed API is running",
        "version": "1.0.0",
        "endpoints": [
            "GET /api/test",
            "GET /api/get-doctor?id={doctor_id}",
            "POST /api/save-doctor",
            "POST /api/schedule",
            "GET /api/get-slots?doctor_id={doctor_id}&date={date}",
            "POST /api/book-appointment"
        ]
    }

@app.get("/api/test")
async def test_endpoint():
    """Test endpoint to verify API is working"""
    return {
        "success": True,
        "message": "FastAPI endpoint is working perfectly!",
        "timestamp": "2026-01-11"
    }

@app.post("/api/schedule", response_model=ScheduleResponse, tags=["Scheduling"])
async def generate_schedule(request: ScheduleRequest):
    """
    Receives a natural language description of work hours,
    uses OpenAI to analyze it, and generates 90 days of available appointment slots.
    """
    # 1. Validation
    validation_error = validate_schedule_text(request.schedule_text)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    try:
        # 2. OpenAI Processing
        schedule_structure = get_schedule_structure_from_openai(request.schedule_text)

        # Validate structure from OpenAI
        schedule_data = schedule_structure.get("schedule", schedule_structure)
        default_config = schedule_data.get("default", schedule_data)
        
        required_keys = ["days", "start_time", "end_time", "slot_duration_minutes"]
        if not all(key in default_config for key in required_keys):
            raise HTTPException(
                status_code=500, 
                detail="AI could not extract a valid schedule structure. Try rephrasing your text."
            )

        # 3. Generate Slots
        generated_slots = generate_slots(schedule_structure)
        
        if not generated_slots:
            raise HTTPException(
                status_code=404, 
                detail="No appointment slots could be generated based on the provided text. Check days and hours."
            )

        # 4. Return Response
        return ScheduleResponse(
            success=True,
            slots=generated_slots,
            total_slots=len(generated_slots)
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"An internal error occurred while processing your request: {str(e)}"
        )

@app.get("/api/get-doctor")
async def get_doctor(id: str):
    """
    Get doctor information by ID
    
    Parameters:
    - id: Doctor unique identifier (e.g., "dr-joao")
    
    Returns:
    - Doctor data from Google Sheets
    """
    try:
        sheets = SheetsClient()
        doctor = sheets.get_doctor(id)
        
        if not doctor:
            raise HTTPException(
                status_code=404,
                detail="Doctor not found"
            )
        
        return {
            "success": True,
            "doctor": doctor
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/api/save-doctor")
async def save_doctor(doctor: DoctorModel):
    """
    Save or update doctor configuration and availability slots
    
    Body:
    - Doctor data including slots
    
    Returns:
    - Success message with doctor ID and link
    """
    try:
        sheets = SheetsClient()
        
        # Check if link is available
        if not sheets.check_link_available(doctor.link, exclude_doctor_id=doctor.id):
            raise HTTPException(
                status_code=400,
                detail="This link is already taken. Please choose another one."
            )
        
        # Prepare doctor data
        doctor_data = {
            'id': doctor.id,
            'name': doctor.name,
            'specialty': doctor.specialty or '',
            'address': doctor.address,
            'phone': doctor.phone,
            'email': doctor.email,
            'logo_url': doctor.logo_url or '',
            'color': doctor.color,
            'language': doctor.language,
            'welcome_message': doctor.welcome_message or '',
            'link': doctor.link
        }
        
        # Save doctor data
        doctor_result = sheets.save_doctor(doctor_data)
        
        if not doctor_result['success']:
            raise HTTPException(
                status_code=500,
                detail=doctor_result.get('error', 'Failed to save doctor')
            )
        
        # Save availability slots if provided
        slots_saved = 0
        if doctor.slots:
            slots_data = [slot.dict() for slot in doctor.slots]
            slots_result = sheets.save_availability(doctor.id, slots_data)
            
            if not slots_result['success']:
                raise HTTPException(
                    status_code=500,
                    detail=slots_result.get('error', 'Failed to save slots')
                )
            
            slots_saved = slots_result.get('slots_count', 0)
        
        return {
            "success": True,
            "message": "Doctor configuration saved successfully",
            "doctor_id": doctor.id,
            "link": f"https://slotlymed.com/{doctor.link}",
            "slots_saved": slots_saved
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/api/get-slots")
async def get_slots(doctor_id: str, date: Optional[str] = None):
    """
    Get available appointment slots for a doctor
    
    Parameters:
    - doctor_id: Doctor unique identifier (required)
    - date: Filter by specific date YYYY-MM-DD (optional)
    
    Returns:
    - List of available slots
    """
    try:
        sheets = SheetsClient()
        slots = sheets.get_availability(doctor_id, date)
        
        return {
            "success": True,
            "doctor_id": doctor_id,
            "date": date,
            "slots": slots,
            "count": len(slots)
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/api/book-appointment")
async def book_appointment(appointment: AppointmentModel):
    """
    Create a new appointment
    
    Body:
    - doctor_id: Doctor unique identifier
    - patient_name: Patient full name
    - patient_email: Patient email
    - patient_phone: Patient phone
    - date: Appointment date (YYYY-MM-DD)
    - time: Appointment time (HH:MM)
    - notes: Optional notes
    
    Returns:
    - Appointment confirmation
    """
    try:
        sheets = SheetsClient()
        
        # Verify slot is still available
        slots = sheets.get_availability(appointment.doctor_id, appointment.date)
        slot_available = any(
            slot['date'] == appointment.date and 
            slot['time'] == appointment.time and 
            slot['status'] == 'available'
            for slot in slots
        )
        
        if not slot_available:
            raise HTTPException(
                status_code=400,
                detail="This time slot is no longer available"
            )
        
        # Create appointment
        appointment_data = appointment.dict()
        result = sheets.create_appointment(appointment_data)
        
        if not result['success']:
            raise HTTPException(
                status_code=500,
                detail=result.get('error', 'Failed to create appointment')
            )
        
        return {
            "success": True,
            "message": "Appointment booked successfully",
            "appointment_id": result['appointment_id'],
            "appointment": {
                "date": appointment.date,
                "time": appointment.time,
                "patient_name": appointment.patient_name
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ==================== STRIPE & AUTH ENDPOINTS ====================

def hash_password(password: str) -> str:
    """Hash password with SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

@app.post("/api/create-checkout-session")
async def create_checkout_session(request: CreateCheckoutRequest):
    """
    Create a Stripe Checkout session for subscription
    """
    try:
        price_id = os.environ.get('STRIPE_PRICE_ID', 'price_1SpFPDRmTP4UQnz3uiYcFQON')
        
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.cancel_url,
        )
        
        return {
            "success": True,
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create checkout session: {str(e)}"
        )

@app.get("/api/checkout-session/{session_id}")
async def get_checkout_session(session_id: str):
    """
    Get checkout session details after payment
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        return {
            "success": True,
            "customer_id": session.customer,
            "customer_email": session.customer_details.email if session.customer_details else None,
            "payment_status": session.payment_status,
            "subscription_id": session.subscription
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve session: {str(e)}"
        )

@app.post("/api/set-password")
async def set_password(request: SetPasswordRequest):
    """
    Set password for a customer after payment
    """
    try:
        # Verify customer exists in Stripe
        try:
            customer = stripe.Customer.retrieve(request.customer_id)
        except:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Hash password
        password_hash = hash_password(request.password)
        
        # Save to Google Sheets (new tab: users)
        sheets = SheetsClient()
        result = sheets.save_user({
            'customer_id': request.customer_id,
            'email': customer.email,
            'password_hash': password_hash,
            'created_at': datetime.now().isoformat()
        })
        
        if not result['success']:
            raise HTTPException(status_code=500, detail="Failed to save user")
        
        return {
            "success": True,
            "message": "Password set successfully",
            "customer_id": request.customer_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/api/login")
async def login(request: LoginRequest):
    """
    Verify customer_id and password
    """
    try:
        sheets = SheetsClient()
        user = sheets.get_user(request.customer_id)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        password_hash = hash_password(request.password)
        if user.get('password_hash') != password_hash:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify Stripe subscription is active
        try:
            subscriptions = stripe.Subscription.list(customer=request.customer_id, status='active')
            if not subscriptions.data:
                raise HTTPException(status_code=403, detail="Subscription inactive")
        except HTTPException:
            raise
        except:
            # If Stripe check fails, allow access (for testing)
            pass
        
        return {
            "success": True,
            "message": "Login successful",
            "customer_id": request.customer_id,
            "email": user.get('email')
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/api/verify-subscription/{customer_id}")
async def verify_subscription(customer_id: str):
    """
    Check if customer has active subscription
    """
    try:
        subscriptions = stripe.Subscription.list(customer=customer_id, status='active')
        
        return {
            "success": True,
            "active": len(subscriptions.data) > 0,
            "customer_id": customer_id
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify subscription: {str(e)}"
        )

@app.get("/api/get-appointments")
async def get_appointments(customer_id: str):
    """
    Get all appointments for a doctor (by customer_id)
    """
    try:
        sheets = SheetsClient()
        
        # First get doctor_id from customer_id
        doctor = sheets.get_doctor_by_customer_id(customer_id)
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor not found")
        
        appointments = sheets.get_appointments(doctor['id'])
        
        return {
            "success": True,
            "appointments": appointments,
            "count": len(appointments)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

# ==================== EXCEPTION HANDLERS ====================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent JSON response"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "details": str(exc)
        }
    )

# ==================== VERCEL HANDLER ====================

# For Vercel, the app instance is automatically used as the handler
# No explicit handler function needed with FastAPI + Vercel
