"""
SlotlyMed - AI Schedule Generation Endpoint (Vercel Compatible)
"""

from http.server import BaseHTTPRequestHandler
import json
import os
from datetime import datetime, timedelta

class handler(BaseHTTPRequestHandler):
    
    def _set_headers(self, status=200):
        """Set response headers with CORS"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self._set_headers(200)
    
    def do_GET(self):
        """Handle GET requests - health check"""
        self._set_headers(200)
        response = {
            "message": "SlotlyMed Schedule API is running",
            "endpoint": "/api/schedule",
            "status": "operational",
            "version": "5.0-vercel-compatible"
        }
        self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        """Handle POST requests - generate schedule"""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_error(400, "Empty request body")
                return
                
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            schedule_text = data.get('schedule_text', '').strip()
            
            if not schedule_text:
                self._send_error(400, "schedule_text is required")
                return
            
            # Validate context (anti-abuse)
            if not self._validate_schedule_text(schedule_text):
                self._send_error(400, "Invalid schedule description. Please describe your medical practice schedule.")
                return
            
            # Generate slots with OpenAI
            try:
                slots = self._generate_slots_with_ai(schedule_text)
                
                self._set_headers(200)
                response = {
                    "success": True,
                    "slots": slots,
                    "total_slots": len(slots)
                }
                self.wfile.write(json.dumps(response).encode())
                
            except Exception as ai_error:
                self._send_error(500, f"AI processing error: {str(ai_error)}")
            
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
        except Exception as e:
            self._send_error(500, f"Server error: {str(e)}")
    
    def _validate_schedule_text(self, text):
        """Validate if text is about medical scheduling"""
        text_lower = text.lower()
        
        # Block non-medical requests
        blocked = ['recipe', 'receita', 'bolo', 'cake', 'poem', 'poema', 'story', 'história', 'joke', 'piada']
        if any(word in text_lower for word in blocked):
            return False
        
        # Check minimum length
        if len(text.strip()) < 10:
            return False
        
        return True
    
    def _generate_slots_with_ai(self, schedule_text):
        """Generate slots using OpenAI API"""
        import urllib.request
        import re
        
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        
        # OpenAI prompt
        prompt = f"""Extract scheduling information and return ONLY valid JSON.

Text: "{schedule_text}"

Return this exact JSON structure:
{{
    "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "start_time": "09:00",
    "end_time": "17:00",
    "slot_duration_minutes": 30,
    "breaks": [{{"start": "12:00", "end": "13:00"}}]
}}

Rules:
- Use English day names
- 24h format (HH:MM)
- If no breaks, return empty array
- If no duration specified, use 30 minutes
- Return ONLY the JSON, no explanation"""

        # Call OpenAI
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a scheduling assistant. Return valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 500
        })
        
        req = urllib.request.Request(url, data=payload.encode(), headers=headers, method='POST')
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                ai_text = result['choices'][0]['message']['content'].strip()
                
                # Clean markdown
                if ai_text.startswith("```"):
                    ai_text = re.sub(r'```(?:json)?\n?|\n?```', '', ai_text).strip()
                
                # Parse schedule data
                schedule_data = json.loads(ai_text)
                
                # Generate slots from schedule data
                return self._create_slots_from_schedule(schedule_data)
                
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _create_slots_from_schedule(self, schedule_data):
        """Create slot list from schedule data"""
        DAY_MAP = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6
        }
        
        slots = []
        
        # Get days of week
        days_of_week = []
        for day_name in schedule_data.get("days", []):
            day_num = DAY_MAP.get(day_name.lower())
            if day_num is not None:
                days_of_week.append(day_num)
        
        if not days_of_week:
            raise ValueError("No valid days in schedule")
        
        # Parse times
        start_time = schedule_data.get("start_time", "09:00")
        end_time = schedule_data.get("end_time", "17:00")
        duration = schedule_data.get("slot_duration_minutes", 30)
        
        start_h, start_m = map(int, start_time.split(":"))
        end_h, end_m = map(int, end_time.split(":"))
        
        # Parse breaks
        breaks = []
        for brk in schedule_data.get("breaks", []):
            if brk.get("start") and brk.get("end"):
                bh, bm = map(int, brk["start"].split(":"))
                eh, em = map(int, brk["end"].split(":"))
                breaks.append({"start": bh * 60 + bm, "end": eh * 60 + em})
        
        # Generate 90 days of slots
        today = datetime.now().date()
        
        for day_offset in range(90):
            current_date = today + timedelta(days=day_offset)
            
            if current_date.weekday() not in days_of_week:
                continue
            
            time_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m
            
            while time_minutes < end_minutes:
                # Check if in break
                in_break = False
                for brk in breaks:
                    if brk["start"] <= time_minutes < brk["end"]:
                        time_minutes = brk["end"]
                        in_break = True
                        break
                
                if in_break or time_minutes >= end_minutes:
                    continue
                
                # Create slot
                hour = time_minutes // 60
                minute = time_minutes % 60
                
                slots.append({
                    "date": current_date.strftime("%Y-%m-%d"),
                    "time": f"{hour:02d}:{minute:02d}",
                    "status": "available"
                })
                
                time_minutes += duration
        
        return slots
    
    def _send_error(self, code, message):
        """Send error response"""
        self._set_headers(code)
        response = {
            "success": False,
            "error": message
        }
        self.wfile.write(json.dumps(response).encode())
