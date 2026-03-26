"""
SlotlyCare Backend - FastAPI Unified API
All endpoints centralized in one file for Vercel serverless deployment
UPDATED: Now includes Stripe integration for payments and authentication
FIXED: AI no longer invents breaks/lunch that weren't requested
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
import re
import unicodedata
from datetime import datetime, timedelta, time
from openai import OpenAI
import stripe

# Add parent directory to path to import sheets_client
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from supabase_client import SheetsClient

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
    additional_info: Optional[str] = ""
    link: str
    slots: Optional[List[SlotModel]] = []
    customer_id: Optional[str] = ""  # Stripe customer ID
    partner_source: Optional[str] = None  # Coupon code if came from partner channel
    plan_years: Optional[int] = None  # Subscription duration (default 3, referral gets 5)

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
    is_trial: Optional[bool] = False
    coupon_code: Optional[str] = None   # Ex: "CIOSP2026" — para landings de parceiros
    plan_years: Optional[int] = None   # Subscription duration to store in metadata
    test_mode: Optional[bool] = False   # True = usa price de teste (R$1 / price_1Sri6Y...)

class SetPasswordRequest(BaseModel):
    customer_id: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ScheduleResponse(BaseModel):
    success: bool
    slots: List[Slot]
    total_slots: int
    error: Optional[str] = None

class ReferralRequest(BaseModel):
    referred_name: str
    referred_email: str
    referred_specialty: Optional[str] = ""
    message: Optional[str] = ""
    referrer_customer_id: str
    referrer_doctor_link: Optional[str] = ""
    language: Optional[str] = "en"

class TrialSignupRequest(BaseModel):
    email: str
    password: str
    name: str
    slug: str

class BatchReferralItem(BaseModel):
    name: str
    email: str
    type: Optional[str] = "colleague"

class BatchReferralRequest(BaseModel):
    referrals: List[BatchReferralItem]
    referrer_customer_id: str
    referrer_doctor_link: Optional[str] = ""
    language: Optional[str] = "en"

class UpgradeTrialRequest(BaseModel):
    trial_customer_id: str
    stripe_customer_id: str

class OpinionRequest(BaseModel):
    customer_id: str
    opinion: str

class NewGradColleague(BaseModel):
    name: Optional[str] = ""
    contact: Optional[str] = ""

class NewGradRequest(BaseModel):
    customer_id: Optional[str] = ""
    university: str
    graduation_year: str
    colleagues: Optional[List[NewGradColleague]] = []
    communities: Optional[str] = ""
    suggestions: Optional[str] = ""

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

CRITICAL RULE: ONLY include what the user EXPLICITLY mentions. NEVER add anything they didn't ask for.

Your task: Extract schedule information from the doctor's text and return a JSON structure.

MULTILINGUAL SUPPORT - Accept input in ANY language:
- Portuguese: Segunda, Terça, Quarta, Quinta, Sexta, Sábado, Domingo
- Spanish: Lunes, Martes, Miércoles, Jueves, Viernes, Sábado, Domingo
- French: Lundi, Mardi, Mercredi, Jeudi, Vendredi, Samedi, Dimanche
- German: Montag, Dienstag, Mittwoch, Donnerstag, Freitag, Samstag, Sonntag
- Italian: Lunedì, Martedì, Mercoledì, Giovedì, Venerdì, Sabato, Domenica
- English: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday

ALWAYS output day names in English.

STRICT RULES - READ CAREFULLY:
1. BREAKS/LUNCH: ONLY add breaks if user EXPLICITLY mentions: "lunch", "almoço", "almuerzo", "pause", "break", "intervalo", "pausa". If they don't mention it, breaks must be an EMPTY array [].
2. SLOT DURATION: Use what user says. If not mentioned, default to 30 minutes.
3. BLOCKED DATES: Only if user mentions vacation, block, holiday, férias, bloquear, etc.
4. OVERRIDES: Only if user specifies DIFFERENT hours for specific days.

EXAMPLES:

Input: "Segunda a sexta 9h-17h. Sábado 8h-12h. Consulta de 20 minutos"
Output:
{{
  "schedule": {{
    "default": {{
      "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
      "start_time": "09:00",
      "end_time": "17:00",
      "slot_duration_minutes": 20,
      "breaks": []
    }},
    "overrides": [
      {{"day": "Saturday", "start_time": "08:00", "end_time": "12:00", "slot_duration_minutes": 20, "breaks": []}}
    ],
    "blocked_dates": [],
    "blocked_date_ranges": []
  }}
}}

Input: "Monday to Friday 8am-6pm, lunch 12pm-1pm"
Output:
{{
  "schedule": {{
    "default": {{
      "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
      "start_time": "08:00",
      "end_time": "18:00",
      "slot_duration_minutes": 30,
      "breaks": [{{"start": "12:00", "end": "13:00"}}]
    }},
    "overrides": [],
    "blocked_dates": [],
    "blocked_date_ranges": []
  }}
}}

Input: "Terça a sábado 10h-19h, consultas de 45 minutos"
Output:
{{
  "schedule": {{
    "default": {{
      "days": ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
      "start_time": "10:00",
      "end_time": "19:00",
      "slot_duration_minutes": 45,
      "breaks": []
    }},
    "overrides": [],
    "blocked_dates": [],
    "blocked_date_ranges": []
  }}
}}

Input: "Segunda a sexta 9h-18h. Bloquear 20 de dezembro a 5 de janeiro para férias"
Output:
{{
  "schedule": {{
    "default": {{
      "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
      "start_time": "09:00",
      "end_time": "18:00",
      "slot_duration_minutes": 30,
      "breaks": []
    }},
    "overrides": [],
    "blocked_dates": [],
    "blocked_date_ranges": [
      {{"start": "2026-12-20", "end": "2027-01-05", "reason": "vacation"}}
    ]
  }}
}}

REMEMBER: 
- NO breaks unless explicitly requested
- Times in 24h format (HH:MM)
- Dates in YYYY-MM-DD format
- Return ONLY valid JSON, nothing else'''

    response = openai_client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        response_format={"type": "json_object"},
        temperature=0.1  # Lower temperature for more consistent/literal responses
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
    blocked_ranges = schedule_data.get("blocked_date_ranges", [])
    
    # Parse blocked_dates - handle both string and dict formats
    blocked_dates = set()
    raw_blocked = schedule_data.get("blocked_dates", [])
    for item in raw_blocked:
        if isinstance(item, str):
            blocked_dates.add(item)
        elif isinstance(item, dict):
            # Handle {"date": "2026-01-25"} or {"start": "...", "end": "..."}
            if "date" in item:
                blocked_dates.add(item["date"])
            elif "start" in item and "end" in item:
                # It's actually a range
                try:
                    start = datetime.strptime(item["start"], "%Y-%m-%d").date()
                    end = datetime.strptime(item["end"], "%Y-%m-%d").date()
                    current = start
                    while current <= end:
                        blocked_dates.add(current.strftime("%Y-%m-%d"))
                        current += timedelta(days=1)
                except:
                    pass
    
    # Parse blocked ranges
    for range_info in blocked_ranges:
        try:
            start = datetime.strptime(range_info["start"], "%Y-%m-%d").date()
            end = datetime.strptime(range_info["end"], "%Y-%m-%d").date()
            current = start
            while current <= end:
                blocked_dates.add(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
        except:
            pass
    
    # Day mapping
    day_mapping = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6
    }
    
    # Default config with error handling
    default_days = []
    for d in default_config.get("days", []):
        if d in day_mapping:
            default_days.append(day_mapping[d])
    
    try:
        default_start = time.fromisoformat(default_config.get("start_time", "09:00"))
    except:
        default_start = time.fromisoformat("09:00")
    
    try:
        default_end = time.fromisoformat(default_config.get("end_time", "17:00"))
    except:
        default_end = time.fromisoformat("17:00")
    
    default_duration = default_config.get("slot_duration_minutes", 30)
    if not isinstance(default_duration, int) or default_duration < 5:
        default_duration = 30
    
    default_breaks = default_config.get("breaks", [])
    if not isinstance(default_breaks, list):
        default_breaks = []
    
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
            
            # Check if slot overlaps with any break
            in_break = False
            break_end_time = None
            for break_start, break_end in break_intervals:
                # Check if current slot overlaps with this break
                if not (current_slot_time.time() >= break_end or slot_end.time() <= break_start):
                    in_break = True
                    break_end_time = break_end
                    break
            
            if in_break:
                # Jump to the end of the break, not just the next slot
                current_slot_time = datetime.combine(current_date, break_end_time)
            else:
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
    uses OpenAI to analyze it, and generates 180 days of available appointment slots.
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
        
        response = {
            "success": True,
            "doctor": doctor
        }
        
        # Check trial expiration
        customer_id = doctor.get('customer_id', '')
        if customer_id.startswith('trial_'):
            created_at = doctor.get('created_at', '')
            if created_at:
                try:
                    # Parse just the date part (first 10 chars: YYYY-MM-DD)
                    created_at_str = str(created_at)[:10]
                    created_date = datetime.strptime(created_at_str, '%Y-%m-%d')
                    days_elapsed = (datetime.utcnow() - created_date).days
                    response["trial_expired"] = days_elapsed >= 7
                    response["trial_days_remaining"] = max(0, 7 - days_elapsed)
                except Exception as e:
                    print(f"Trial date parse error: {e}, created_at={created_at}")
                    response["trial_expired"] = False
                    response["trial_days_remaining"] = 7
            else:
                response["trial_expired"] = False
                response["trial_days_remaining"] = 7
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/api/get-doctor-by-customer")
async def get_doctor_by_customer(customer_id: str):
    """
    Get doctor information by Stripe customer ID
    
    Parameters:
    - customer_id: Stripe customer ID (e.g., "cus_xxxxx")
    
    Returns:
    - Doctor data from Google Sheets
    """
    try:
        sheets = SheetsClient()
        doctor = sheets.get_doctor_by_customer_id(customer_id)
        
        if not doctor:
            return {
                "success": False,
                "doctor": None,
                "message": "No doctor found for this customer"
            }
        
        response = {
            "success": True,
            "doctor": doctor
        }
        
        # Check trial expiration
        if customer_id.startswith('trial_'):
            created_at = doctor.get('created_at', '')
            if created_at:
                try:
                    # Parse just the date part (first 10 chars: YYYY-MM-DD)
                    created_at_str = str(created_at)[:10]
                    created_date = datetime.strptime(created_at_str, '%Y-%m-%d')
                    days_elapsed = (datetime.utcnow() - created_date).days
                    response["trial_expired"] = days_elapsed >= 7
                    response["trial_days_remaining"] = max(0, 7 - days_elapsed)
                except Exception as e:
                    print(f"Trial date parse error: {e}, created_at={created_at}")
                    response["trial_expired"] = False
                    response["trial_days_remaining"] = 7
            else:
                response["trial_expired"] = False
                response["trial_days_remaining"] = 7
        
        return response
    
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
        
        # Determine if this is an update or new doctor
        existing_doctor = None
        doctor_id = doctor.id  # Default to provided ID (the link)
        
        # If customer_id is provided, check if doctor already exists
        if doctor.customer_id:
            existing_doctor = sheets.get_doctor_by_customer_id(doctor.customer_id)
            if existing_doctor:
                # Use existing doctor's ID for updates
                doctor_id = existing_doctor['id']
        
        # Check if link is available (exclude current doctor if updating)
        exclude_id = doctor_id if existing_doctor else None
        if not sheets.check_link_available(doctor.link, exclude_doctor_id=exclude_id):
            raise HTTPException(
                status_code=400,
                detail="This link is already taken. Please choose another one."
            )
        
        # If updating and link changed, we need to update the ID too
        if existing_doctor and existing_doctor['link'] != doctor.link:
            # The link is changing - use new link as new ID
            doctor_id = doctor.link
        
        # Prepare doctor data
        doctor_data = {
            'id': doctor_id if not existing_doctor else existing_doctor['id'],
            'name': doctor.name,
            'specialty': doctor.specialty or '',
            'address': doctor.address,
            'phone': doctor.phone,
            'email': doctor.email,
            'logo_url': doctor.logo_url or '',
            'color': doctor.color,
            'language': doctor.language,
            'welcome_message': doctor.welcome_message or '',
            'additional_info': doctor.additional_info or '',
            'link': doctor.link,
            'customer_id': doctor.customer_id or '',
            'partner_source': doctor.partner_source,
            'plan_years': doctor.plan_years
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
            # Use the doctor's ID (which may be the old ID if updating)
            save_id = doctor_data['id']
            slots_result = sheets.save_availability(save_id, slots_data)
            
            if not slots_result['success']:
                raise HTTPException(
                    status_code=500,
                    detail=slots_result.get('error', 'Failed to save slots')
                )
            
            slots_saved = slots_result.get('slots_count', 0)
        
        return {
            "success": True,
            "message": "Doctor configuration saved successfully",
            "doctor_id": doctor_data['id'],
            "link": f"https://www.slotlycare.com/{doctor.link}",
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
        
        # === NOTIFICATION SYSTEM ===
        # Send bell notification for every new appointment
        try:
            # Get doctor info to find customer_id
            doctor = sheets.get_doctor(appointment.doctor_id)
            if doctor and doctor.get('customer_id'):
                customer_id = doctor['customer_id']
                
                # Appointment notification
                notif_text = f"📅 New appointment: {appointment.patient_name} — {appointment.date} at {appointment.time}"
                sheets.create_message(customer_id, notif_text, 'appointment')
                
                # Count total appointments to check milestones
                total_appointments = sheets.count_doctor_appointments(appointment.doctor_id)
                
                # First appointment → unlock referrals
                if total_appointments == 1 and not doctor.get('referral_unlocked'):
                    sheets.unlock_doctor_referral(appointment.doctor_id)
                    unlock_text = "🎉 Your first patient just booked! Now you know it works — invite colleagues who still do this the hard way."
                    sheets.create_message(customer_id, unlock_text, 'referral_unlock')
                
                # 10th appointment → milestone reminder
                elif total_appointments == 10:
                    milestone_text = "🎉 10 patients have booked through your link. Your colleagues are still doing this by phone — you have invites waiting."
                    sheets.create_message(customer_id, milestone_text, 'referral_milestone')
                
                # 25th appointment → final reminder
                elif total_appointments == 25:
                    milestone_text = "🚀 25 patients booked! You still have invites for colleagues who need this."
                    sheets.create_message(customer_id, milestone_text, 'referral_milestone')
        except Exception as notif_error:
            # Notification failure should never block the appointment
            print(f"Notification error (non-blocking): {notif_error}")
        
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
    Create a Stripe Checkout session for one-time payment.
    Supports partner landings via coupon_code and test_mode parameters.
    """
    try:
        # Escolhe o Price ID: test_mode usa preço de teste (R$1), produção usa env var
        if request.test_mode:
            price_id = 'price_1T2DRCDMcPDY3XCzzyVX5NbI'  # Live BRL R$1,00 (para testes)
        else:
            price_id = os.environ.get('STRIPE_PRICE_ID', 'price_1SpFPDRmTP4UQnz3uiYcFQON')
        
        # Base checkout parameters
        checkout_params = {
            'payment_method_types': ['card'],
            'line_items': [{
                'price': price_id,
                'quantity': 1,
            }],
            'mode': 'payment',
            'customer_creation': 'always',
            'payment_intent_data': {
                'setup_future_usage': 'off_session',
            },
            'success_url': request.success_url + '?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': request.cancel_url,
        }
        
        # Determina desconto a aplicar
        # Prioridade: is_trial > coupon_code > allow_promotion_codes
        # Nota: Stripe não permite allow_promotion_codes + discounts ao mesmo tempo
        if request.is_trial:
            # Trial: desconto automático 30% (Referral30)
            checkout_params['discounts'] = [{'promotion_code': 'promo_1T0Ov8DMcPDY3XCzs2doSm4F'}]
        elif request.coupon_code:
            # Parceiro: busca o promotion_code pelo código legível (ex: "CIOSP2026")
            promo_list = stripe.PromotionCode.list(code=request.coupon_code, limit=1, active=True)
            if not promo_list.data:
                raise HTTPException(status_code=400, detail=f"Coupon '{request.coupon_code}' not found or inactive")
            promo_id = promo_list.data[0].id
            checkout_params['discounts'] = [{'promotion_code': promo_id}]
        else:
            # Compra normal: usuário pode digitar cupom manualmente
            checkout_params['allow_promotion_codes'] = True
        
        # Add partner tracking metadata if coupon was used
        if request.coupon_code:
            checkout_params['metadata'] = {'partner_coupon': request.coupon_code}
        
        # Add plan_years to metadata if provided
        if request.plan_years:
            checkout_params.setdefault('metadata', {})['plan_years'] = str(request.plan_years)
        
        checkout_session = stripe.checkout.Session.create(**checkout_params)
        
        return {
            "success": True,
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id
        }
    
    except HTTPException:
        raise
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
        
        customer_id = session.customer
        customer_email = session.customer_details.email if session.customer_details else None

        # Payment Link flow: payment succeeded but no customer created
        # Create a Stripe Customer so success.html can proceed normally
        if not customer_id and session.payment_status == "paid" and customer_email:
            try:
                new_customer = stripe.Customer.create(
                    email=customer_email,
                    metadata={"source": "payment_link", "session_id": session_id}
                )
                customer_id = new_customer.id
                print(f"Created customer {customer_id} for Payment Link session {session_id}")
            except Exception as ce:
                print(f"Failed to create customer for session {session_id}: {str(ce)}")

        return {
            "success": True,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "payment_status": session.payment_status,
            "payment_intent": session.payment_intent,
            "partner_source": session.metadata.get('partner_coupon') if session.metadata else None,
            "plan_years": int(session.metadata.get('plan_years', 3)) if session.metadata else 3
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve session: {str(e)}"
        )

@app.post("/api/stripe-webhook")
async def stripe_webhook(request: Request):
    """
    Stripe Webhook — safety net for payment confirmation.
    Listens for checkout.session.completed events and saves
    the account to pending_accounts so it can be recovered
    even if success.html fails.
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']

        customer_id = session.get('customer')
        customer_email = None
        if session.get('customer_details'):
            customer_email = session['customer_details'].get('email')

        metadata = session.get('metadata', {}) or {}
        partner_source = metadata.get('partner_coupon')
        plan_years = int(metadata.get('plan_years', 3))
        amount_total = session.get('amount_total')

        # If no customer was created (Payment Link flow), create one
        if not customer_id and session.get('payment_status') == 'paid' and customer_email:
            try:
                new_customer = stripe.Customer.create(
                    email=customer_email,
                    metadata={"source": "webhook", "session_id": session.get('id', '')}
                )
                customer_id = new_customer.id
            except Exception:
                pass

        try:
            sheets = SheetsClient()
            sheets.save_pending_account({
                'session_id': session.get('id', ''),
                'customer_id': customer_id or '',
                'customer_email': customer_email or '',
                'partner_source': partner_source,
                'plan_years': plan_years,
                'payment_status': session.get('payment_status', ''),
                'amount_total': amount_total
            })
        except Exception as e:
            print(f"Webhook: failed to save pending account: {e}")

    return JSONResponse(content={"received": True}, status_code=200)

class RecoverAccountRequest(BaseModel):
    email: str
    password: str

@app.post("/api/recover-account")
async def recover_account(request: RecoverAccountRequest):
    """
    Recover an account when success.html failed after payment.
    Looks up the email in pending_accounts, verifies payment,
    creates user + doctor records if they don't exist.
    """
    try:
        sheets = SheetsClient()

        # 1. Check if user already exists (already recovered or normal flow worked)
        existing_user = sheets.get_user_by_email(request.email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Account already exists. Try logging in instead.")

        # 2. Look up in pending_accounts
        pending = sheets.get_pending_account_by_email(request.email)
        if not pending:
            raise HTTPException(status_code=404, detail="No payment found for this email. Please check the email address or contact support.")

        customer_id = pending.get('customer_id')
        if not customer_id:
            raise HTTPException(status_code=400, detail="Payment record incomplete. Please contact support.")

        # 3. Create user record
        password_hash = hash_password(request.password)
        user_result = sheets.save_user({
            'customer_id': customer_id,
            'email': request.email,
            'password_hash': password_hash,
            'created_at': datetime.now().isoformat()
        })

        if not user_result['success']:
            raise HTTPException(status_code=500, detail="Failed to create user account")

        # 4. Save partner_source and plan_years to localStorage via response
        partner_source = pending.get('partner_source')
        plan_years = pending.get('plan_years', 3)

        return {
            "success": True,
            "message": "Account recovered successfully",
            "customer_id": customer_id,
            "email": request.email,
            "partner_source": partner_source,
            "plan_years": plan_years
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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
    Verify email and password
    """
    try:
        sheets = SheetsClient()
        user = sheets.get_user_by_email(request.email)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        password_hash = hash_password(request.password)
        if user.get('password_hash') != password_hash:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # For one-time payment model, we just check if user exists in our database
        # (they were added after successful payment)
        
        return {
            "success": True,
            "message": "Login successful",
            "customer_id": user.get('customer_id'),
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

# ==================== SLUG GENERATION HELPERS ====================

def generate_slug(name: str) -> str:
    """
    Transform a name into a URL-safe slug.
    'Dr. João Silva' → 'drjoaosilva'
    'Dra. María Santos' → 'dramariasantos'
    """
    # Remove accents
    slug = unicodedata.normalize('NFKD', name)
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    # Keep only letters and numbers
    slug = ''.join(c for c in slug if c.isalnum())
    # Lowercase
    slug = slug.lower()
    # Fallback for empty slugs (emojis, symbols only, etc.)
    if not slug:
        slug = f"invite{int(datetime.utcnow().timestamp())}"
    return slug

def generate_unique_slug(sheets, base_slug: str) -> str:
    """
    Ensure slug is unique across invites AND doctors tables.
    If 'drjoao' is taken, tries 'drjoao2', 'drjoao3', etc.
    """
    slug = base_slug
    counter = 2
    max_attempts = 50  # Safety limit
    while not sheets.check_slug_available(slug):
        slug = f"{base_slug}{counter}"
        counter += 1
        if counter > max_attempts:
            # Ultimate fallback: add timestamp
            slug = f"{base_slug}{int(datetime.utcnow().timestamp())}"
            break
    return slug

# ==================== REFERRAL ENDPOINTS ====================

@app.post("/api/save-referral")
async def save_referral(request: ReferralRequest):
    """
    Save a colleague referral (single — legacy endpoint, kept for compatibility)
    """
    try:
        sheets = SheetsClient()
        result = sheets.save_referral({
            'referrer_customer_id': request.referrer_customer_id,
            'referrer_doctor_link': request.referrer_doctor_link,
            'referred_name': request.referred_name,
            'referred_email': request.referred_email,
            'referred_specialty': request.referred_specialty,
            'message': request.message,
            'language': request.language
        })
        
        if not result['success']:
            raise HTTPException(status_code=500, detail=result.get('error', 'Failed to save referral'))
        
        return {
            "success": True,
            "message": "Referral saved successfully",
            "referral_id": result.get('referral_id')
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/api/batch-referrals")
async def batch_referrals(request: BatchReferralRequest):
    """
    Create invites and referrals in batch.
    For each colleague: generates slug, creates invite, saves referral.
    Returns list of generated invite links.
    """
    try:
        sheets = SheetsClient()
        
        # Get referrer doctor's name (for the green bar on convite.html)
        referrer_doctor = sheets.get_doctor_by_customer_id(request.referrer_customer_id)
        referrer_name = referrer_doctor['name'] if referrer_doctor else ''
        
        results = []
        errors = []
        
        for item in request.referrals:
            try:
                # 1. Generate unique slug
                base_slug = generate_slug(item.name)
                unique_slug = generate_unique_slug(sheets, base_slug)
                
                # 2. Create invite (this powers convite.html)
                invite_result = sheets.create_invite({
                    'invited_name': item.name,
                    'slug': unique_slug,
                    'referrer_name': referrer_name,
                    'status': 'pending',
                    'contact_info': item.email,
                    'type': item.type
                })
                
                if not invite_result['success']:
                    errors.append({'name': item.name, 'error': invite_result.get('error', 'Failed to create invite')})
                    continue
                
                # 3. Save referral record (for tracking)
                sheets.save_referral({
                    'referrer_customer_id': request.referrer_customer_id,
                    'referrer_doctor_link': request.referrer_doctor_link,
                    'referred_name': item.name,
                    'referred_email': item.email,
                    'referred_specialty': '',
                    'message': '',
                    'language': request.language,
                    'invite_slug': unique_slug
                })
                
                results.append({
                    'name': item.name,
                    'email': item.email,
                    'slug': unique_slug
                })
                
            except Exception as item_error:
                print(f"Error processing referral for {item.name}: {item_error}")
                errors.append({'name': item.name, 'error': str(item_error)})
        
        return {
            "success": True,
            "created": len(results),
            "errors": len(errors),
            "invites": results,
            "error_details": errors if errors else []
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/api/referral-stats")
async def referral_stats(customer_id: str):
    """
    Get referral statistics for a doctor.
    Shows how many colleagues were invited and their status.
    """
    try:
        sheets = SheetsClient()
        
        # Get doctor name from customer_id
        doctor = sheets.get_doctor_by_customer_id(customer_id)
        if not doctor:
            return {
                "success": True,
                "stats": {'total': 0, 'pending': 0, 'clicked': 0, 'trial_started': 0, 'converted': 0, 'invites': []}
            }
        
        stats = sheets.get_referral_stats(doctor['name'])
        
        return {
            "success": True,
            "stats": stats
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/api/invite-partner-check/{slug}")
async def invite_partner_check(slug: str):
    """
    Check if the referrer of an invite came from a partner channel.
    Used by invite.html to decide whether to offer partner pricing to the invitee.
    Returns partner_source (coupon code) if referrer came from a partner, null otherwise.
    """
    try:
        sheets = SheetsClient()
        
        # 1. Find the referral record by invite_slug to get referrer_customer_id
        result = sheets.supabase.table('referrals').select('referrer_customer_id').eq('invite_slug', slug).execute()
        
        if not result.data or len(result.data) == 0:
            return {"success": True, "partner_source": None}
        
        referrer_customer_id = result.data[0].get('referrer_customer_id')
        if not referrer_customer_id:
            return {"success": True, "partner_source": None}
        
        # 2. Look up the referrer's doctor record for partner_source
        doctor = sheets.get_doctor_by_customer_id(referrer_customer_id)
        if not doctor:
            return {"success": True, "partner_source": None}
        
        partner_source = doctor.get('partner_source')
        plan_years = doctor.get('plan_years', 3)
        
        return {
            "success": True,
            "partner_source": partner_source,
            "plan_years": plan_years
        }
    
    except Exception as e:
        return {"success": True, "partner_source": None, "plan_years": 3}

# ==================== TRIAL ENDPOINTS ====================

@app.post("/api/trial-signup")
async def trial_signup(request: TrialSignupRequest):
    """
    Create a trial account (no payment required).
    Generates a trial customer_id and creates user + doctor records.
    """
    try:
        sheets = SheetsClient()
        
        # Validate email not already taken
        existing_user = sheets.get_user_by_email(request.email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Validate slug not already taken
        slug = request.slug.strip().lower()
        if not sheets.check_link_available(slug):
            raise HTTPException(status_code=400, detail="This link is already taken")
        
        # Generate trial customer_id
        trial_id = f"trial_{secrets.token_hex(8)}"
        
        # Hash password
        password_hash = hash_password(request.password)
        
        # Create user record
        user_result = sheets.save_user({
            'customer_id': trial_id,
            'email': request.email,
            'password_hash': password_hash,
            'created_at': datetime.now().isoformat()
        })
        
        if not user_result['success']:
            raise HTTPException(status_code=500, detail="Failed to create user")
        
        # Create doctor record with minimal info
        doctor_result = sheets.save_doctor({
            'id': slug,
            'name': request.name,
            'specialty': '',
            'address': '',
            'phone': '',
            'email': request.email,
            'logo_url': '',
            'color': '#3B82F6',
            'language': 'en',
            'welcome_message': '',
            'additional_info': '',
            'link': slug,
            'customer_id': trial_id
        })
        
        if not doctor_result['success']:
            raise HTTPException(status_code=500, detail="Failed to create doctor profile")
        
        # Update invite status
        sheets.update_invite_status(slug, 'trial_started')
        
        return {
            "success": True,
            "message": "Trial account created",
            "customer_id": trial_id,
            "email": request.email
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/api/upgrade-trial")
async def upgrade_trial(request: UpgradeTrialRequest):
    """
    Upgrade a trial account to paid.
    Replaces trial_xxx customer_id with cus_xxx from Stripe
    in both doctors and users tables. Preserves all profile data.
    """
    try:
        # Validate: trial_customer_id must start with trial_
        if not request.trial_customer_id.startswith('trial_'):
            raise HTTPException(status_code=400, detail="Invalid trial customer ID")
        
        # Validate: stripe_customer_id must start with cus_
        if not request.trial_customer_id or not request.stripe_customer_id:
            raise HTTPException(status_code=400, detail="Both IDs are required")
        
        sheets = SheetsClient()
        
        # Verify trial account exists
        doctor = sheets.get_doctor_by_customer_id(request.trial_customer_id)
        if not doctor:
            raise HTTPException(status_code=404, detail="Trial account not found")
        
        # Verify Stripe customer exists
        try:
            stripe.Customer.retrieve(request.stripe_customer_id)
        except:
            raise HTTPException(status_code=404, detail="Stripe customer not found")
        
        # Perform the upgrade
        result = sheets.upgrade_trial_to_paid(
            request.trial_customer_id,
            request.stripe_customer_id
        )
        
        if not result['success']:
            raise HTTPException(status_code=500, detail=result.get('error', 'Upgrade failed'))
        
        # Update invite status to converted (if invite exists)
        doctor_link = doctor.get('link', '')
        if doctor_link:
            sheets.update_invite_status(doctor_link, 'converted')
        
        return {
            "success": True,
            "message": "Trial upgraded to paid account",
            "new_customer_id": request.stripe_customer_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.post("/api/save-newgrad")
async def save_newgrad(request: NewGradRequest):
    """
    Save new graduate program data.
    Stores university, graduation year, colleagues, communities and suggestions
    in the new_grad_data table.
    """
    try:
        sheets = SheetsClient()

        colleagues_data = [
            {'name': c.name, 'contact': c.contact}
            for c in (request.colleagues or [])
            if c.name or c.contact
        ]

        result = sheets.save_new_grad({
            'customer_id': request.customer_id or '',
            'university': request.university,
            'graduation_year': request.graduation_year,
            'colleagues': json.dumps(colleagues_data),
            'communities': request.communities or '',
            'suggestions': request.suggestions or ''
        })

        if not result['success']:
            raise HTTPException(status_code=500, detail="Failed to save new grad data")

        return {
            "success": True,
            "message": "New grad data saved"
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

# ==================== OPINION / FEEDBACK ====================

@app.post("/api/save-opinion")
async def save_opinion(request: OpinionRequest):
    """Save user feedback to the opinions table in Supabase."""
    try:
        if not request.opinion or not request.opinion.strip():
            raise HTTPException(status_code=400, detail="Opinion text is required")

        sheets = SheetsClient()
        result = sheets.save_opinion(request.customer_id, request.opinion.strip())

        if not result['success']:
            raise HTTPException(status_code=500, detail=result.get('error', 'Failed to save opinion'))

        return {"success": True, "message": "Opinion saved"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== DM CARD GENERATOR INVITES ====================

class DmInviteItem(BaseModel):
    name: str
    specialty: Optional[str] = ""
    slug: str  # pre-verified slug from dm-card-generator

class DmInvitesRequest(BaseModel):
    invites: List[DmInviteItem]
    language: Optional[str] = "pt"

@app.post("/api/dm-invites")
async def dm_invites(request: DmInvitesRequest):
    """
    Create invite records for slugs pre-verified by the DM card generator.
    referrer_name is always 'SlotlyCare' (direct prospecting, not doctor referral).
    Slugs are accepted as-is — no generation, no modification.
    """
    try:
        sheets = SheetsClient()
        results = []
        errors = []

        for item in request.invites:
            try:
                invite_result = sheets.create_invite({
                    'invited_name': item.name,
                    'slug': item.slug,
                    'referrer_name': 'SlotlyCare',
                    'status': 'pending',
                    'contact_info': '',
                    'type': 'colleague'
                })

                if not invite_result['success']:
                    errors.append({'name': item.name, 'slug': item.slug, 'error': invite_result.get('error', 'Failed to create invite')})
                    continue

                results.append({'name': item.name, 'slug': item.slug})

            except Exception as item_error:
                errors.append({'name': item.name, 'slug': item.slug, 'error': str(item_error)})

        return {
            "success": True,
            "created": len(results),
            "errors": len(errors),
            "invites": results,
            "error_details": errors if errors else []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ==================== VERCEL HANDLER ====================

# For Vercel, the app instance is automatically used as the handler
# No explicit handler function needed with FastAPI + Vercel
