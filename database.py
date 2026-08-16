import os
from supabase import create_client, Client
from datetime import datetime
import secrets
from dotenv import load_dotenv

load_dotenv()

# ============================================
# SUPABASE CONFIGURATION
# ============================================

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'your_supabase_url')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'your_supabase_key')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================
# TABLE CREATION (Run once in Supabase SQL Editor)
# ============================================

SQL_CREATE_TABLES = """
-- Settings table
CREATE TABLE IF NOT EXISTS settings (
    id BIGSERIAL PRIMARY KEY,
    gmail_email TEXT,
    gmail_password TEXT,
    fampay_id TEXT,
    fampay_api_key TEXT,
    logged_in BOOLEAN DEFAULT FALSE,
    login_time TIMESTAMP
);

-- Transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT UNIQUE,
    amount DECIMAL(10,2),
    upi_id TEXT,
    status TEXT DEFAULT 'pending',
    transaction_id TEXT,
    qr_code TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    verified_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0
);

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id BIGSERIAL PRIMARY KEY,
    api_key TEXT UNIQUE,
    user_name TEXT,
    email TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- API Transactions table
CREATE TABLE IF NOT EXISTS api_transactions (
    id BIGSERIAL PRIMARY KEY,
    api_key TEXT,
    order_id TEXT,
    transaction_id TEXT,
    amount DECIMAL(10,2),
    status TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
"""

# ============================================
# SETTINGS FUNCTIONS
# ============================================

def get_settings():
    """Get current settings"""
    try:
        response = supabase.table('settings').select('*').order('id', desc=True).limit(1).execute()
        if response.data:
            data = response.data[0]
            return {
                'gmail_email': data.get('gmail_email'),
                'gmail_password': data.get('gmail_password'),
                'fampay_id': data.get('fampay_id'),
                'fampay_api_key': data.get('fampay_api_key'),
                'logged_in': data.get('logged_in', False),
                'login_time': data.get('login_time')
            }
    except Exception as e:
        print(f"Error getting settings: {e}")
    return None

def save_settings(gmail_email, gmail_password, fampay_id, fampay_api_key):
    """Save settings"""
    try:
        data = {
            'gmail_email': gmail_email,
            'gmail_password': gmail_password,
            'fampay_id': fampay_id,
            'fampay_api_key': fampay_api_key,
            'logged_in': True,
            'login_time': datetime.now().isoformat()
        }
        response = supabase.table('settings').insert(data).execute()
        return response.data
    except Exception as e:
        print(f"Error saving settings: {e}")
        return None

def update_login_status(status=True):
    """Update login status"""
    try:
        data = {
            'logged_in': status,
            'login_time': datetime.now().isoformat()
        }
        response = supabase.table('settings').update(data).eq('id', 1).execute()
        return response.data
    except Exception as e:
        print(f"Error updating login status: {e}")
        return None

# ============================================
# TRANSACTION FUNCTIONS
# ============================================

def save_transaction(order_id, amount, upi_id, qr_code):
    """Save a new transaction"""
    try:
        data = {
            'order_id': order_id,
            'amount': amount,
            'upi_id': upi_id,
            'qr_code': qr_code,
            'created_at': datetime.now().isoformat(),
            'status': 'pending'
        }
        response = supabase.table('transactions').insert(data).execute()
        return response.data
    except Exception as e:
        print(f"Error saving transaction: {e}")
        return None

def get_transaction(order_id):
    """Get transaction by order_id"""
    try:
        response = supabase.table('transactions').select('*').eq('order_id', order_id).execute()
        if response.data:
            data = response.data[0]
            return {
                'id': data.get('id'),
                'order_id': data.get('order_id'),
                'amount': data.get('amount'),
                'upi_id': data.get('upi_id'),
                'status': data.get('status'),
                'transaction_id': data.get('transaction_id'),
                'qr_code': data.get('qr_code'),
                'created_at': data.get('created_at'),
                'verified_at': data.get('verified_at'),
                'retry_count': data.get('retry_count', 0)
            }
    except Exception as e:
        print(f"Error getting transaction: {e}")
    return None

def update_transaction(order_id, status, transaction_id=None):
    """Update transaction status"""
    try:
        data = {
            'status': status,
            'verified_at': datetime.now().isoformat()
        }
        if transaction_id:
            data['transaction_id'] = transaction_id
        
        # Also increment retry_count if status is pending
        if status == 'pending':
            # First get current retry_count
            txn = get_transaction(order_id)
            if txn:
                data['retry_count'] = (txn.get('retry_count', 0) + 1)
        
        response = supabase.table('transactions').update(data).eq('order_id', order_id).execute()
        return response.data
    except Exception as e:
        print(f"Error updating transaction: {e}")
        return None

def get_all_transactions(limit=50):
    """Get all transactions"""
    try:
        response = supabase.table('transactions').select('*').order('created_at', desc=True).limit(limit).execute()
        transactions = []
        for data in response.data:
            transactions.append({
                'id': data.get('id'),
                'order_id': data.get('order_id'),
                'amount': data.get('amount'),
                'upi_id': data.get('upi_id'),
                'status': data.get('status'),
                'transaction_id': data.get('transaction_id'),
                'qr_code': data.get('qr_code'),
                'created_at': data.get('created_at'),
                'verified_at': data.get('verified_at'),
                'retry_count': data.get('retry_count', 0)
            })
        return transactions
    except Exception as e:
        print(f"Error getting transactions: {e}")
        return []

def get_pending_transactions():
    """Get all pending transactions"""
    try:
        response = supabase.table('transactions').select('*').eq('status', 'pending').execute()
        transactions = []
        for data in response.data:
            transactions.append({
                'id': data.get('id'),
                'order_id': data.get('order_id'),
                'amount': data.get('amount'),
                'upi_id': data.get('upi_id'),
                'status': data.get('status'),
                'transaction_id': data.get('transaction_id'),
                'qr_code': data.get('qr_code'),
                'created_at': data.get('created_at'),
                'verified_at': data.get('verified_at'),
                'retry_count': data.get('retry_count', 0)
            })
        return transactions
    except Exception as e:
        print(f"Error getting pending transactions: {e}")
        return []

# ============================================
# API KEY FUNCTIONS
# ============================================

def generate_api_key():
    """Generate a new API key"""
    return f"PK_{secrets.token_hex(16).upper()}"

def create_api_key(user_name, email):
    """Create a new API key for a user"""
    api_key = generate_api_key()
    try:
        data = {
            'api_key': api_key,
            'user_name': user_name,
            'email': email,
            'created_at': datetime.now().isoformat(),
            'is_active': True
        }
        response = supabase.table('api_keys').insert(data).execute()
        return api_key
    except Exception as e:
        print(f"Error creating API key: {e}")
        return None

def get_api_keys():
    """Get all API keys"""
    try:
        response = supabase.table('api_keys').select('*').order('created_at', desc=True).execute()
        keys = []
        for data in response.data:
            keys.append({
                'id': data.get('id'),
                'api_key': data.get('api_key'),
                'user_name': data.get('user_name'),
                'email': data.get('email'),
                'created_at': data.get('created_at'),
                'is_active': data.get('is_active', True)
            })
        return keys
    except Exception as e:
        print(f"Error getting API keys: {e}")
        return []

def verify_api_key(api_key):
    """Verify if API key is valid"""
    try:
        response = supabase.table('api_keys').select('*').eq('api_key', api_key).eq('is_active', True).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error verifying API key: {e}")
        return False

# ============================================
# API TRANSACTION FUNCTIONS
# ============================================

def add_api_transaction(api_key, order_id, transaction_id, amount, status):
    """Add a transaction to API feed"""
    try:
        data = {
            'api_key': api_key,
            'order_id': order_id,
            'transaction_id': transaction_id,
            'amount': amount,
            'status': status,
            'created_at': datetime.now().isoformat()
        }
        response = supabase.table('api_transactions').insert(data).execute()
        return response.data
    except Exception as e:
        print(f"Error adding API transaction: {e}")
        return None

def get_api_transactions(api_key=None, limit=100):
    """Get API transactions (live feed)"""
    try:
        if api_key:
            response = supabase.table('api_transactions').select('*').eq('api_key', api_key).order('created_at', desc=True).limit(limit).execute()
        else:
            response = supabase.table('api_transactions').select('*').order('created_at', desc=True).limit(limit).execute()
        
        transactions = []
        for data in response.data:
            transactions.append({
                'id': data.get('id'),
                'api_key': data.get('api_key'),
                'order_id': data.get('order_id'),
                'transaction_id': data.get('transaction_id'),
                'amount': data.get('amount'),
                'status': data.get('status'),
                'created_at': data.get('created_at')
            })
        return transactions
    except Exception as e:
        print(f"Error getting API transactions: {e}")
        return []

# ============================================
# STATS FUNCTIONS
# ============================================

def get_stats():
    """Get statistics"""
    try:
        # Total
        response = supabase.table('transactions').select('*', count='exact').execute()
        total = response.count or 0
        
        # Success
        response = supabase.table('transactions').select('*', count='exact').eq('status', 'success').execute()
        success = response.count or 0
        
        # Pending
        response = supabase.table('transactions').select('*', count='exact').eq('status', 'pending').execute()
        pending = response.count or 0
        
        # Cancelled
        response = supabase.table('transactions').select('*', count='exact').eq('status', 'cancelled').execute()
        cancelled = response.count or 0
        
        # Revenue
        response = supabase.table('transactions').select('amount').eq('status', 'success').execute()
        revenue = sum([d.get('amount', 0) for d in response.data])
        
        # API keys count
        response = supabase.table('api_keys').select('*', count='exact').eq('is_active', True).execute()
        api_keys_count = response.count or 0
        
        return {
            'total': total,
            'success': success,
            'pending': pending,
            'cancelled': cancelled,
            'revenue': revenue,
            'api_keys_count': api_keys_count
        }
    except Exception as e:
        print(f"Error getting stats: {e}")
        return {
            'total': 0,
            'success': 0,
            'pending': 0,
            'cancelled': 0,
            'revenue': 0,
            'api_keys_count': 0
        }
