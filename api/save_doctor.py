"""
API Endpoint: Save Doctor Setup
URL: /api/save_doctor
Method: POST

Saves doctor configuration and availability slots to Google Sheets
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
        Doctor data:
        - id: unique identifier (e.g., "dr-joao")
        - name: doctor name
        - specialty: medical specialty (optional)
        - address: clinic address
        - phone: contact phone
        - email: contact email
        - logo_url: URL to logo image (optional)
        - color: theme color (hex, default: #3B82F6)
        - language: interface language (en, pt, es, fr, de, it)
        - welcome_message: greeting message (optional)
        - link: unique link (same as id)
        
        Availability:
        - slots: list of slot objects with date, time, status
    
    Returns:
        200: Doctor saved successfully
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
        required_fields = ['id', 'name', 'address', 'phone', 'email', 'language', 'link']
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
        
        # Check if link is available (if different from current)
        if not sheets.check_link_available(body['link'], exclude_doctor_id=body['id']):
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'This link is already taken. Please choose another one.'
                })
            }
        
        # Prepare doctor data
        doctor_data = {
            'id': body['id'],
            'name': body['name'],
            'specialty': body.get('specialty', ''),
            'address': body['address'],
            'phone': body['phone'],
            'email': body['email'],
            'logo_url': body.get('logo_url', ''),
            'color': body.get('color', '#3B82F6'),
            'language': body['language'],
            'welcome_message': body.get('welcome_message', ''),
            'link': body['link']
        }
        
        # Save doctor data
        doctor_result = sheets.save_doctor(doctor_data)
        
        if not doctor_result['success']:
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps(doctor_result)
            }
        
        # Save availability slots (if provided)
        slots_result = None
        if 'slots' in body and body['slots']:
            slots_result = sheets.save_availability(body['id'], body['slots'])
            
            if not slots_result['success']:
                return {
                    'statusCode': 500,
                    'headers': headers,
                    'body': json.dumps(slots_result)
                }
        
        # Success response
        response_data = {
            'success': True,
            'message': 'Doctor configuration saved successfully',
            'doctor_id': body['id'],
            'link': f"https://slotlymed.com/{body['link']}"  # Update with your actual domain
        }
        
        if slots_result:
            response_data['slots_saved'] = slots_result['slots_count']
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(response_data)
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
        print(f"Error in save_doctor: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': 'Internal server error',
                'details': str(e)
            })
        }
