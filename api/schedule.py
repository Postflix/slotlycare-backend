from http.server import BaseHTTPRequestHandler
import json
import os
from datetime import datetime, timedelta

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response = {
            "message": "SlotlyMed API is running. Use POST to generate schedule.",
            "endpoint": "/api/schedule"
        }
        self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        """Handle POST requests"""
        try:
            # Read request body
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            schedule_text = data.get('schedule_text', '').strip()
            
            if not schedule_text:
                self.send_error_response(400, "schedule_text is required")
                return
            
            # Validate context (anti-abuse)
            if not self.validate_medical_context(schedule_text):
                self.send_error_response(400, "Please describe medical appointment scheduling only")
                return
            
            # Mock response (OpenAI will be added after testing structure works)
            # For now, return success with mock data
            response = {
                "success": True,
                "message": "Schedule processing works! OpenAI integration pending.",
                "received_text": schedule_text,
                "mock_slots": [
                    "2025-01-10T09:00:00",
                    "2025-01-10T09:30:00",
                    "2025-01-10T10:00:00"
                ],
                "total_slots": 3
            }
            
            self.send_success_response(response)
            
        except Exception as e:
            self.send_error_response(500, str(e))
    
    def validate_medical_context(self, text):
        """Validate if text is about medical scheduling"""
        text_lower = text.lower()
        
        keywords = [
            'atendo', 'consulta', 'horário', 'agenda', 'paciente',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
            'segunda', 'terça', 'quarta', 'quinta', 'sexta',
            'appointment', 'schedule', 'patient', 'slots'
        ]
        
        keyword_count = sum(1 for keyword in keywords if keyword in text_lower)
        return keyword_count >= 1
    
    def send_success_response(self, data):
        """Send successful JSON response"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_error_response(self, code, message):
        """Send error JSON response"""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        error_response = {
            "success": False,
            "error": message
        }
        self.wfile.write(json.dumps(error_response).encode())
