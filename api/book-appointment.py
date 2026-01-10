"""
API Endpoint: Book Appointment
URL: /api/book_appointment
Method: POST

Creates a new appointment and marks the slot as booked
"""

import json
import sys
import os

# Add parent directory to path to import sheets_client
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sheets_client import SheetsClient

def handler(event, context):
    """
    Vercel serverless function handler
    
    Body Parameters (JSON):
        - doctor_id: doctor unique identifier
        - patient_name: patient full name
        - patient_email: patient email
        - patient_phone: patient phone
        - date: appointment date (YYYY-MM-DD)
        - time: appointment time (HH:MM)
        - notes: optional notes
    
    Returns:
        200: Appointment created
        400: Invalid data
        500: Internal error
    """
    
    # Set CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }
    
    # Handle OPTIONS request (CORS preflight)
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': ''
        }
    
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        # Validate required fields
        required_fields = ['doctor_id', 'patient_name', 'patient_email', 'patient_phone', 'date', 'time']
        missing_fields = [field for field in required_fields if field not in body]
        
        if missing_fields:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': f'Missing required fields: {", ".join(missing_fields)}'
                })
            }
        
        # Initialize Sheets client
        sheets = SheetsClient()
        
        # Verify slot is still available
        slots = sheets.get_availability(body['doctor_id'], body['date'])
        slot_available = any(
            slot['date'] == body['date'] and 
            slot['time'] == body['time'] and 
            slot['status'] == 'available'
            for slot in slots
        )
        
        if not slot_available:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'This time slot is no longer available'
                })
            }
        
        # Create appointment
        appointment_data = {
            'doctor_id': body['doctor_id'],
            'patient_name': body['patient_name'],
            'patient_email': body['patient_email'],
            'patient_phone': body['patient_phone'],
            'date': body['date'],
            'time': body['time'],
            'notes': body.get('notes', '')
        }
        
        result = sheets.create_appointment(appointment_data)
        
        if not result['success']:
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps(result)
            }
        
        # Success response
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'message': 'Appointment booked successfully',
                'appointment_id': result['appointment_id'],
                'appointment': {
                    'date': body['date'],
                    'time': body['time'],
                    'patient_name': body['patient_name']
                }
            })
        }
    
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': 'Invalid JSON in request body'
            })
        }
    
    except Exception as e:
        print(f"Error in book_appointment: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': 'Internal server error',
                'details': str(e)
            })
        }
