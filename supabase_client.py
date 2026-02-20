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
                    'customer_id': row.get('customer_id', ''),
                    'created_at': row.get('created_at', '')
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
                    'customer_id': row.get('customer_id', ''),
                    'created_at': row.get('created_at', '')
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
    
    def get_user_by_email(self, email):
        """
        Get user data by email
        
        Args:
            email (str): User email
        
        Returns:
            dict: User data or None if not found
        """
        try:
            result = self.supabase.table('users').select('*').eq('email', email).execute()
            
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
            print(f"Error getting user by email: {e}")
            return None
    
    def update_user_password(self, email, new_password_hash):
        """
        Update user password by email
        
        Args:
            email (str): User email
            new_password_hash (str): New hashed password
        
        Returns:
            dict: Success status
        """
        try:
            result = self.supabase.table('users').update({
                'password_hash': new_password_hash
            }).eq('email', email).execute()
            
            if result.data and len(result.data) > 0:
                return {'success': True}
            
            return {'success': False, 'error': 'User not found'}
        
        except Exception as e:
            print(f"Error updating password: {e}")
            return {'success': False, 'error': str(e)}
    
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
    
    # ==================== REFERRALS METHODS ====================
    
    def save_referral(self, referral_data):
        """
        Save a referral (colleague recommendation)
        
        Args:
            referral_data (dict):
                - referrer_customer_id: Stripe customer ID of who is referring
                - referrer_doctor_link: doctor link of who is referring
                - referred_name: name of the referred colleague
                - referred_email: email of the referred colleague
                - referred_specialty: specialty (optional)
                - message: optional message
                - language: language code
                - invite_slug: slug of the generated invite (optional)
        
        Returns:
            dict: Success status and referral ID
        """
        try:
            db_data = {
                'referrer_customer_id': referral_data['referrer_customer_id'],
                'referrer_doctor_link': referral_data.get('referrer_doctor_link', ''),
                'referred_name': referral_data['referred_name'],
                'referred_email': referral_data['referred_email'],
                'referred_specialty': referral_data.get('referred_specialty', ''),
                'message': referral_data.get('message', ''),
                'language': referral_data.get('language', 'en'),
                'created_at': datetime.now().isoformat()
            }
            
            # Include invite_slug if provided
            if referral_data.get('invite_slug'):
                db_data['invite_slug'] = referral_data['invite_slug']
            
            result = self.supabase.table('referrals').insert(db_data).execute()
            
            referral_id = result.data[0]['id'] if result.data else None
            
            return {
                'success': True,
                'message': 'Referral saved',
                'referral_id': referral_id
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    # ==================== INVITES METHODS ====================
    
    def update_invite_status(self, slug, status):
        """
        Update the status of an invite by slug
        
        Args:
            slug (str): Invite slug
            status (str): New status (pending, clicked, trial_started, converted)
        
        Returns:
            bool: Success status
        """
        try:
            self.supabase.table('invites').update({
                'status': status
            }).eq('slug', slug).execute()
            return True
        except Exception as e:
            print(f"Error updating invite status: {e}")
            return False
    
    def create_invite(self, invite_data):
        """
        Create a new invite record
        
        Args:
            invite_data (dict):
                - invited_name: Name of the invited colleague
                - slug: Unique URL slug
                - referrer_name: Name of doctor who referred (activates green bar)
                - status: Default 'pending'
        
        Returns:
            dict: Success status and slug
        """
        try:
            result = self.supabase.table('invites').insert(invite_data).execute()
            return {
                'success': True,
                'slug': invite_data.get('slug', '')
            }
        except Exception as e:
            print(f"Error creating invite: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_slug_available(self, slug):
        """
        Check if a slug is available in BOTH invites and doctors tables
        
        Args:
            slug (str): Slug to check
        
        Returns:
            bool: True if available, False if taken
        """
        try:
            # Check invites table
            invite_result = self.supabase.table('invites').select('slug').eq('slug', slug).execute()
            if invite_result.data and len(invite_result.data) > 0:
                return False
            
            # Check doctors table (someone may already have this link)
            doctor_result = self.supabase.table('doctors').select('link').eq('link', slug).execute()
            if doctor_result.data and len(doctor_result.data) > 0:
                return False
            
            return True
        except Exception as e:
            print(f"Error checking slug availability: {e}")
            return False
    
    def upgrade_trial_to_paid(self, old_customer_id, new_customer_id):
        """
        Upgrade a trial account to paid by replacing customer_id
        in both doctors and users tables.
        
        Args:
            old_customer_id (str): The trial_xxx customer ID
            new_customer_id (str): The cus_xxx customer ID from Stripe
        
        Returns:
            dict: Success status
        """
        try:
            # Update doctors table
            doc_result = self.supabase.table('doctors').update({
                'customer_id': new_customer_id,
                'updated_at': datetime.now().isoformat()
            }).eq('customer_id', old_customer_id).execute()
            
            if not doc_result.data or len(doc_result.data) == 0:
                return {
                    'success': False,
                    'error': f'No doctor found with customer_id {old_customer_id}'
                }
            
            # Update users table
            self.supabase.table('users').update({
                'customer_id': new_customer_id
            }).eq('customer_id', old_customer_id).execute()
            
            return {
                'success': True,
                'message': f'Upgraded {old_customer_id} to {new_customer_id}'
            }
        
        except Exception as e:
            print(f"Error upgrading trial: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_referral_stats(self, referrer_name):
        """
        Get referral statistics for a doctor by their name.
        Queries invites table where referrer_name matches.
        
        Args:
            referrer_name (str): Name of the referring doctor
        
        Returns:
            dict: Stats with total, pending, clicked, trial_started, converted counts
        """
        try:
            result = self.supabase.table('invites').select('invited_name, slug, status, created_at').eq('referrer_name', referrer_name).execute()
            
            stats = {
                'total': 0,
                'pending': 0,
                'clicked': 0,
                'trial_started': 0,
                'converted': 0,
                'invites': []
            }
            
            if result.data:
                stats['total'] = len(result.data)
                for row in result.data:
                    status = row.get('status', 'pending')
                    if status in stats:
                        stats[status] += 1
                    stats['invites'].append({
                        'name': row.get('invited_name', ''),
                        'slug': row.get('slug', ''),
                        'status': status
                    })
            
            return stats
        except Exception as e:
            print(f"Error getting referral stats: {e}")
            return {'total': 0, 'pending': 0, 'clicked': 0, 'trial_started': 0, 'converted': 0, 'invites': []}

    def save_new_grad(self, data):
        """
        Save new graduate program data to new_grad_data table.

        Args:
            data (dict):
                - customer_id: trial customer ID (optional)
                - university: medical school name
                - graduation_year: year of graduation
                - colleagues: JSON string with list of colleagues
                - communities: communities text (optional)
                - suggestions: suggestions text (optional)

        Returns:
            dict: Success status
        """
        try:
            db_data = {
                'customer_id': data.get('customer_id', ''),
                'university': data['university'],
                'graduation_year': data['graduation_year'],
                'colleagues': data.get('colleagues', '[]'),
                'communities': data.get('communities', ''),
                'suggestions': data.get('suggestions', ''),
                'created_at': datetime.now().isoformat()
            }

            self.supabase.table('new_grad_data').insert(db_data).execute()

            return {
                'success': True,
                'message': 'New grad data saved'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def save_opinion(self, customer_id, opinion_text):
        """
        Save user feedback/opinion to the opinions table.

        Args:
            customer_id (str): Stripe customer ID of the user
            opinion_text (str): The feedback text

        Returns:
            dict: Success status
        """
        try:
            db_data = {
                'customer_id': customer_id,
                'opinion': opinion_text,
                'created_at': datetime.now().isoformat()
            }

            self.supabase.table('opinions').insert(db_data).execute()

            return {'success': True}

        except Exception as e:
            return {'success': False, 'error': str(e)}
