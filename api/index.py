"""
SlotlyMed Backend - FastAPI Unified API
All endpoints centralized in one file for Vercel serverless deployment
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import sys
import os
import json

# Add parent directory to path to import sheets_client
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from sheets_client import SheetsClient

# Initialize FastAPI app
app = FastAPI(
    title="SlotlyMed API",
    description="Medical appointment scheduling system with AI-powered slot generation",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class AppointmentModel(BaseModel):
    doctor_id: str
    patient_name: str
    patient_email: str
    patient_phone: str
    date: str
    time: str
    notes: Optional[str] = ""

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
        "timestamp": "2026-01-10"
    }

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

# Vercel expects a handler function for serverless deployment
def handler(request, context):
    """Vercel serverless handler wrapper"""
    return app(request, context)
