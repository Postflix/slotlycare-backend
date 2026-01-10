"""
API Endpoint: Get Doctor Data
URL: /api/get_doctor?id=dr-joao
Method: GET

Returns doctor information from Google Sheets
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
        - id: doctor unique identifier (e.g., "dr-joao")
    
    Returns:
        200: Doctor data found
        404: Doctor not found
        400: Missing id parameter
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
        
        if not query_params or 'id' not in query_params:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'Missing required parameter: id'
                })
            }
        
        doctor_id = query_params['id']
        
        # Initialize Sheets client
        sheets = SheetsClient()
        
        # Get doctor data
        doctor = sheets.get_doctor(doctor_id)
        
        if not doctor:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({
                    'success': False,
                    'error': 'Doctor not found'
                })
            }
        
        # Get availability (optional - can be loaded separately)
        # availability = sheets.get_availability(doctor_id)
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'doctor': doctor
                # 'availability': availability  # Uncomment if needed
            })
        }
    
    except Exception as e:
        print(f"Error in get_doctor: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'success': False,
                'error': 'Internal server error',
                'details': str(e)
            })
        }
