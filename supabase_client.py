"""
Supabase Client for SlotlyCare
Handles all interactions with Supabase database
Drop-in replacement for sheets_client.py
"""

from supabase import create_client, Client
import os
from datetime import datetime

class SheetsClient:
    """
    Named SheetsClient for backward compatibility with existing code.
    This is actually a Supabase client.
    """
    
    def __init__(self):
        """Initialize Supabase client with credentials from environment"""
        # Get credentials from environment variables
        supabase_url = os.environ.get('SUPABASE_URL')
        supabase_key = os.environ.get('SUPABASE_KEY')
        
        if not supabase_url:
            raise ValueError("SUPABASE_URL environment variable not set")
        
        if not supabase_key:
            raise ValueError("SUPABASE_KEY environment variable not set")
        
        # Create Supabase client
        self.supabase: Client = create_client(supabase_url, supabase_key)
    
    # ==================== DOCTORS METHODS ====================
    
    def save_doctor(self, doctor_data):
        """
        Save or update doctor data
        
        Args:
            doctor_data (dict): Doctor information
        
        Returns:
            dict: Success status and doctor ID
        """
        try:
            # Check if doctor already exists
            existing = self.get_doctor(doctor_data['id'])
            
            # Prepare data for Supabase
            db_data = {
                'id': doctor_data['id'],
                'name': doctor_data['name'],
                'specialty': doctor_data.get('specialty', ''),
                'address': doctor_data.get('address', ''),
                'phone': doctor_data.get('phone', ''),
                'email': doctor_data.get('email', ''),
                'logo_url': doctor_data.get('logo_url', ''),
                'color': doctor_data.get('color', '#3B82F6'),
                'language': doctor_data.get('language', 'en'),
                'welcome_message': doctor_data.get('welcome_message', ''),
                'additional_info': doctor_data.get('additional_info', ''),
                'link': doctor_data['link'],
                'customer_id': doctor_data.get('customer_id', existing.get('customer_id', '') if existing else ''),
                'updated_at': datetime.now().isoformat()
            }
            
            if existing:
                # Update existing doctor
                self.supabase.table('doctors').update(db_data).eq('id', doctor_data['id']).execute()
                
                return {
                    'success': True,
                    'message': 'Doctor updated',
                    'doctor_id': doctor_data['id']
                }
            else:
                # Insert new doctor
                db_data['created_at'] = datetime.now().isoformat()
                self.supabase.table('doctors').insert(db_data).execute()
                
                return {
                    'success': True,
                    'message': 'Doctor created',
                    'doctor_id': doctor_data['id']
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_doctor(self, doctor_id):
        """
        Get doctor data by ID
        
        Args:
            doctor_id (str): Doctor unique identifier
        
        Returns:
            dict: Doctor data or None if not found
        """
        try:
            result = self.supabase.table('doctors').select('*').eq('id', doctor_id).execute()
            
            if result.data and len(result.data) > 0:
                row = result.data[0]
                return {
                    'id': row['id'],
                    'name': row['name'],
                    'specialty': row.get('specialty', ''),
                    'address': row.get('address', ''),
                    'phone': row.get('phone', ''),
                    'email': row.get('email', ''),
                    'logo_url': row.get('logo_url', ''),
                    'color': row.get('color', '#3B82F6'),
                    'language': row.get('language', 'en'),
                    'welcome_message': row.get('welcome_message', ''),
                    'additional_info': row.get('additional_info', ''),
                    'link': row.get('link', ''),
                    'customer_id': row.get('customer_id', '')
                }
            
            return None
        
        except Exception as e:
            print(f"Error getting doctor: {e}")
            return None
    
    def get_doctor_by_customer_id(self, customer_id):
        """
        Get doctor data by Stripe customer ID
        
        Args:
            customer_id (str): Stripe customer ID
        
        Returns:
            dict: Doctor data or None if not found
        """
        try:
            result = self.supabase.table('doctors').select('*').eq('customer_id', customer_id).execute()
            
            if result.data and len(result.data) > 0:
                row = result.data[0]
                return {
                    'id': row['id'],
                    'name': row['name'],
                    'specialty': row.get('specialty', ''),
                    'address': row.get('address', ''),
                    'phone': row.get('phone', ''),
                    'email': row.get('email', ''),
                    'logo_url': row.get('logo_url', ''),
                    'color': row.get('color', '#3B82F6'),
                    'language': row.get('language', 'en'),
                    'welcome_message': row.get('welcome_message', ''),
                    'additional_info': row.get('additional_info', ''),
                    'link': row.get('link', ''),
                    'customer_id': row.get('customer_id', '')
                }
            
            return None
        
        except Exception as e:
            print(f"Error getting doctor by customer_id: {e}")
            return None
    
    def check_link_available(self, link, exclude_doctor_id=None):
        """
        Check if a link is available (not taken by another doctor)
        
        Args:
            link (str): Link to check
            exclude_doctor_id (str): Doctor ID to exclude from check (for updates)
        
        Returns:
            bool: True if available, False if taken
        """
        try:
            query = self.supabase.table('doctors').select('id').eq('link', link)
            
            if exclude_doctor_id:
                query = query.neq('id', exclude_doctor_id)
            
            result = query.execute()
            
            # Available if no results found
            return len(result.data) == 0
        
        except Exception as e:
            print(f"Error checking link: {e}")
            return False
    
    # ==================== USERS METHODS ====================
    
    def save_user(self, user_data):
        """
        Save user data (for authentication)
        
        Args:
            user_data (dict):
                - customer_id: Stripe customer ID
                - email: user email
                - password_hash: hashed password
                - created_at: timestamp
        
        Returns:
            dict: Success status
        """
        try:
            # Check if user already exists
            existing = self.get_user(user_data['customer_id'])
            
            db_data = {
                'customer_id': user_data['customer_id'],
                'email': user_data.get('email', ''),
                'password_hash': user_data['password_hash']
            }
            
            if existing:
                # Update existing user
                self.supabase.table('users').update(db_data).eq('customer_id', user_data['customer_id']).execute()
                
                return {
                    'success': True,
                    'message': 'User updated'
                }
            else:
                # Insert new user
                db_data['created_at'] = user_data.get('created_at', datetime.now().isoformat())
                self.supabase.table('users').insert(db_data).execute()
                
                return {
                    'success': True,
                    'message': 'User created'
                }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_user(self, customer_id):
        """
        Get user data by customer ID
        
        Args:
            customer_id (str): Stripe customer ID
        
        Returns:
            dict: User data or None if not found
        """
        try:
            result = self.supabase.table('users').select('*').eq('customer_id', customer_id).execute()
            
            if result.data and len(result.data) > 0:
                row = result.data[0]
                return {
                    'customer_id': row['customer_id'],
                    'email': row.get('email', ''),
                    'password_hash': row.get('password_hash', ''),
                    'created_at': row.get('created_at', '')
                }
            
            return None
        
        except Exception as e:
            print(f"Error getting user: {e}")
            return None
    
    # ==================== AVAILABILITY METHODS ====================
    
    def save_availability(self, doctor_id, slots):
        """
        Save availability slots for a doctor
        Clears existing slots and adds new ones
        
        Args:
            doctor_id (str): Doctor unique identifier
            slots (list): List of slot dictionaries with date, time, status
        
        Returns:
            dict: Success status
        """
        try:
            # Clear existing slots for this doctor
            self.clear_availability(doctor_id)
            
            # Prepare rows for batch insert
            rows_to_add = []
            for slot in slots:
                rows_to_add.append({
                    'doctor_id': doctor_id,
                    'date': slot['date'],  # Format: YYYY-MM-DD
                    'time': slot['time'],  # Format: HH:MM
                    'status': slot.get('status', 'available')
                })
            
            # Batch insert for performance
            if rows_to_add:
                self.supabase.table('availability').insert(rows_to_add).execute()
            
            return {
                'success': True,
                'message': f'{len(rows_to_add)} slots saved',
                'slots_count': len(rows_to_add)
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def clear_availability(self, doctor_id):
        """
        Clear all availability slots for a doctor
        
        Args:
            doctor_id (str): Doctor unique identifier
        """
        try:
            self.supabase.table('availability').delete().eq('doctor_id', doctor_id).execute()
        except Exception as e:
            print(f"Error clearing availability: {e}")
    
    def get_availability(self, doctor_id, date=None):
        """
        Get available slots for a doctor
        
        Args:
            doctor_id (str): Doctor unique identifier
            date (str): Optional date filter (YYYY-MM-DD)
        
        Returns:
            list: List of available slots
        """
        try:
            query = self.supabase.table('availability').select('*').eq('doctor_id', doctor_id).eq('status', 'available')
            
            if date:
                query = query.eq('date', date)
            
            result = query.execute()
            
            slots = []
            for row in result.data:
                slots.append({
                    'date': str(row['date']),
                    'time': str(row['time']),
                    'status': row['status']
                })
            
            return slots
        
        except Exception as e:
            print(f"Error getting availability: {e}")
            return []
    
    def update_slot_status(self, doctor_id, date, time, status):
        """
        Update status of a specific slot
        
        Args:
            doctor_id (str): Doctor unique identifier
            date (str): Slot date (YYYY-MM-DD)
            time (str): Slot time (HH:MM)
            status (str): New status (available/booked)
        
        Returns:
            bool: Success status
        """
        try:
            result = self.supabase.table('availability').update({
                'status': status
            }).eq('doctor_id', doctor_id).eq('date', date).eq('time', time).execute()
            
            return len(result.data) > 0
        
        except Exception as e:
            print(f"Error updating slot status: {e}")
            return False
    
    # ==================== APPOINTMENTS METHODS ====================
    
    def create_appointment(self, appointment_data):
        """
        Create a new appointment
        
        Args:
            appointment_data (dict):
                - doctor_id: doctor unique identifier
                - patient_name: patient full name
                - patient_email: patient email
                - patient_phone: patient phone
                - date: appointment date (YYYY-MM-DD)
                - time: appointment time (HH:MM)
                - notes: optional notes
        
        Returns:
            dict: Success status and appointment ID
        """
        try:
            # Prepare appointment data
            db_data = {
                'doctor_id': appointment_data['doctor_id'],
                'patient_name': appointment_data['patient_name'],
                'patient_email': appointment_data.get('patient_email', ''),
                'patient_phone': appointment_data.get('patient_phone', ''),
                'date': appointment_data['date'],
                'time': appointment_data['time'],
                'notes': appointment_data.get('notes', ''),
                'created_at': datetime.now().isoformat()
            }
            
            # Insert appointment
            result = self.supabase.table('appointments').insert(db_data).execute()
            
            appointment_id = result.data[0]['id'] if result.data else None
            
            # Update slot status to booked
            self.update_slot_status(
                appointment_data['doctor_id'],
                appointment_data['date'],
                appointment_data['time'],
                'booked'
            )
            
            return {
                'success': True,
                'message': 'Appointment created',
                'appointment_id': appointment_id
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_appointments(self, doctor_id):
        """
        Get all appointments for a doctor
        
        Args:
            doctor_id (str): Doctor unique identifier
        
        Returns:
            list: List of appointments
        """
        try:
            result = self.supabase.table('appointments').select('*').eq('doctor_id', doctor_id).order('date', desc=False).execute()
            
            appointments = []
            for row in result.data:
                appointments.append({
                    'id': str(row['id']),
                    'doctor_id': row['doctor_id'],
                    'patient_name': row['patient_name'],
                    'patient_email': row.get('patient_email', ''),
                    'patient_phone': row.get('patient_phone', ''),
                    'date': str(row['date']),
                    'time': str(row['time']),
                    'notes': row.get('notes', ''),
                    'created_at': row.get('created_at', '')
                })
            
            return appointments
        
        except Exception as e:
            print(f"Error getting appointments: {e}")
            return []
    
    def cancel_appointment(self, appointment_id, doctor_id):
        """
        Cancel an appointment and release the time slot
        
        Args:
            appointment_id (str): Appointment ID to cancel
            doctor_id (str): Doctor ID (for verification)
        
        Returns:
            dict: Success status with date/time info
        """
        try:
            # First get the appointment to know the date/time
            result = self.supabase.table('appointments').select('*').eq('id', appointment_id).eq('doctor_id', doctor_id).execute()
            
            if not result.data or len(result.data) == 0:
                return {
                    'success': False,
                    'error': 'Appointment not found'
                }
            
            appointment = result.data[0]
            apt_date = str(appointment['date'])
            apt_time = str(appointment['time'])
            
            # Normalize time to HH:MM format (remove seconds if present)
            if len(apt_time) > 5:
                apt_time = apt_time[:5]
            
            # Delete the appointment
            self.supabase.table('appointments').delete().eq('id', appointment_id).execute()
            
            # Release the time slot (change status back to available)
            self.supabase.table('availability').update({
                'status': 'available'
            }).eq('doctor_id', doctor_id).eq('date', apt_date).eq('time', apt_time).execute()
            
            return {
                'success': True,
                'message': 'Appointment cancelled',
                'date': apt_date,
                'time': apt_time
            }
        
        except Exception as e:
            print(f"Error cancelling appointment: {e}")
            return {
                'success': False,
                'error': str(e)
            }
