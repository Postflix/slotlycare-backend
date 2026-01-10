"""
API Endpoint: Get Available Slots
URL: /api/get_slots?doctor_id=dr-joao&date=2026-01-15 (date optional)
Method: GET

Returns available appointment slots for a doctor
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
    
    Query Parameters:
        - doctor_id: doctor unique identifier (required)
        - date: filter by specific date YYYY-MM-DD (optional)
    
    Returns:
        200: Slots found
        400: Missing doctor_id
        500: Internal error
    """
    
    # Set CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
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
        # Get query parameters
        query_params = event.get('queryStringParameters', {})
        
        if not query_params or 'doctor_id' not in query_params:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing required parameter: doctor_id'
                })
            }
        
        doctor_id = query_params['doctor_id']
        date = query_params.get('date', None)  # Optional
        
        # Initialize Sheets client
        sheets = SheetsClient()
        
        # Get available slots
        slots = sheets.get_availability(doctor_id, date)
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'doctor_id': doctor_id,
                'date': date,
                'slots': slots,
                'count': len(slots)
            })
        }
    
    except Exception as e:
        print(f"Error in get_slots: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': 'Internal server error',
                'details': str(e)
            })
        }
