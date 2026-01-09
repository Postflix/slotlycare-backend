from http.server import BaseHTTPRequestHandler
import json
import os
from datetime import datetime, timedelta
from openai import OpenAI

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
            "message": "SlotlyMed API with OpenAI is running!",
            "endpoint": "/api/schedule",
            "status": "operational"
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
            
            # Process with OpenAI
            try:
                schedule_data = self.parse_with_openai(schedule_text)
                slots = self.generate_slots(schedule_data)
                
                response = {
                    "success": True,
                    "message": "Schedule generated successfully!",
                    "slots": slots,
                    "schedule_data": schedule_data,
                    "total_slots": len(slots)
                }
                
                self.send_success_response(response)
                
            except Exception as ai_error:
                self.send_error_response(500, f"AI processing error: {str(ai_error)}")
            
        except Exception as e:
            self.send_error_response(500, str(e))
    
    def validate_medical_context(self, text):
        """Validate if text is about medical scheduling"""
        text_lower = text.lower()
        
        keywords = [
            'atendo', 'consulta', 'horário', 'agenda', 'paciente',
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
            'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo',
            'lunes', 'martes', 'miércoles', 'jueves', 'viernes',
            'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi',
            'montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag',
            'lunedì', 'martedì', 'mercoledì', 'giovedì', 'venerdì',
            'appointment', 'schedule', 'patient', 'slots', 'minutes', 'hours',
            'cita', 'horario', 'rendez-vous', 'termin', 'appuntamento'
        ]
        
        keyword_count = sum(1 for keyword in keywords if keyword in text_lower)
        return keyword_count >= 2
    
    def parse_with_openai(self, schedule_text):
        """Use OpenAI to parse schedule text"""
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        prompt = f"""Extract scheduling information from this text and return ONLY valid JSON.

Text: "{schedule_text}"

Return this exact structure:
{{
    "days": ["Monday", "Tuesday", ...],
    "start_time": "09:00",
    "end_time": "17:00",
    "slot_duration_minutes": 30,
    "breaks": [
        {{"start": "12:00", "end": "13:00", "name": "Lunch"}}
    ]
}}

Rules:
- Use English day names
- Use 24h format (HH:MM)
- If no breaks mentioned, return empty array
- If duration not mentioned, use 30 minutes
- Return ONLY the JSON, no explanation"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a medical scheduling assistant. Always return valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Try to parse JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                raise ValueError("Could not parse AI response as JSON")
    
    def generate_slots(self, schedule_data, num_days=30):
        """Generate appointment slots from schedule data"""
        DAY_MAP = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }
        
        slots = []
        
        # Convert day names to numbers
        days_of_week = []
        for day_name in schedule_data.get("days", []):
            day_lower = day_name.lower()
            if day_lower in DAY_MAP:
                days_of_week.append(DAY_MAP[day_lower])
        
        if not days_of_week:
            raise ValueError("No valid days found")
        
        # Parse times
        start_time_str = schedule_data.get("start_time", "09:00")
        end_time_str = schedule_data.get("end_time", "17:00")
        slot_duration = schedule_data.get("slot_duration_minutes", 30)
        
        start_hour, start_minute = map(int, start_time_str.split(":"))
        end_hour, end_minute = map(int, end_time_str.split(":"))
        
        # Parse breaks
        breaks = []
        for break_info in schedule_data.get("breaks", []):
            break_start = break_info.get("start", "")
            break_end = break_info.get("end", "")
            if break_start and break_end:
                bh, bm = map(int, break_start.split(":"))
                eh, em = map(int, break_end.split(":"))
                breaks.append({
                    "start": (bh * 60) + bm,
                    "end": (eh * 60) + em
                })
        
        # Generate slots
        today = datetime.now().date()
        
        for day_offset in range(num_days):
            current_date = today + timedelta(days=day_offset)
            
            if current_date.weekday() not in days_of_week:
                continue
            
            current_time_minutes = (start_hour * 60) + start_minute
            end_time_minutes = (end_hour * 60) + end_minute
            
            while current_time_minutes < end_time_minutes:
                # Check if in break
                in_break = False
                for break_info in breaks:
                    if break_info["start"] <= current_time_minutes < break_info["end"]:
                        in_break = True
                        current_time_minutes = break_info["end"]
                        break
                
                if in_break:
                    continue
                
                # Create slot
                slot_hour = current_time_minutes // 60
                slot_minute = current_time_minutes % 60
                
                slot_datetime = datetime.combine(
                    current_date,
                    datetime.min.time().replace(hour=slot_hour, minute=slot_minute)
                )
                
                slots.append(slot_datetime.isoformat())
                current_time_minutes += slot_duration
        
        return slots
    
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
