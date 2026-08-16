import sqlite3
from datetime import datetime
import secrets

# ============================================
# DATABASE SETUP
# ============================================

def init_db():
    """Initialize database with all tables"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    
    # Settings table (Gmail + FamPay)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY,
        gmail_email TEXT,
        gmail_password TEXT,
        fampay_id TEXT,
        fampay_api_key TEXT,
        logged_in BOOLEAN DEFAULT 0,
        login_time TIMESTAMP
    )''')
    
    # Transactions table
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT UNIQUE,
        amount REAL,
        upi_id TEXT,
        status TEXT DEFAULT 'pending',
        transaction_id TEXT,
        qr_code TEXT,
        created_at TIMESTAMP,
        verified_at TIMESTAMP,
        retry_count INTEGER DEFAULT 0
    )''')
    
    # API Keys table
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT UNIQUE,
        user_name TEXT,
        email TEXT,
        created_at TIMESTAMP,
        is_active BOOLEAN DEFAULT 1
    )''')
    
    # API Transactions table (live feed)
    c.execute('''CREATE TABLE IF NOT EXISTS api_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT,
        order_id TEXT,
        transaction_id TEXT,
        amount REAL,
        status TEXT,
        created_at TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

# ============================================
# SETTINGS FUNCTIONS
# ============================================

def get_settings():
    """Get current settings"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1')
    data = c.fetchone()
    conn.close()
    
    if data:
        return {
            'gmail_email': data[1],
            'gmail_password': data[2],
            'fampay_id': data[3],
            'fampay_api_key': data[4],
            'logged_in': data[5],
            'login_time': data[6]
        }
    return None

def save_settings(gmail_email, gmail_password, fampay_id, fampay_api_key):
    """Save settings"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''INSERT INTO settings 
                 (gmail_email, gmail_password, fampay_id, fampay_api_key, logged_in, login_time)
                 VALUES (?, ?, ?, ?, 1, ?)''',
              (gmail_email, gmail_password, fampay_id, fampay_api_key, datetime.now()))
    conn.commit()
    conn.close()

def update_login_status(status=True):
    """Update login status"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('UPDATE settings SET logged_in=?, login_time=?', (status, datetime.now()))
    conn.commit()
    conn.close()

# ============================================
# TRANSACTION FUNCTIONS
# ============================================

def save_transaction(order_id, amount, upi_id, qr_code):
    """Save a new transaction"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''INSERT INTO transactions 
                 (order_id, amount, upi_id, qr_code, created_at)
                 VALUES (?, ?, ?, ?, ?)''',
              (order_id, amount, upi_id, qr_code, datetime.now()))
    conn.commit()
    conn.close()

def get_transaction(order_id):
    """Get transaction by order_id"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('SELECT * FROM transactions WHERE order_id=?', (order_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row[0],
            'order_id': row[1],
            'amount': row[2],
            'upi_id': row[3],
            'status': row[4],
            'transaction_id': row[5],
            'qr_code': row[6],
            'created_at': row[7],
            'verified_at': row[8],
            'retry_count': row[9]
        }
    return None

def update_transaction(order_id, status, transaction_id=None):
    """Update transaction status"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    
    if transaction_id:
        c.execute('''UPDATE transactions 
                     SET status=?, transaction_id=?, verified_at=?
                     WHERE order_id=?''',
                  (status, transaction_id, datetime.now(), order_id))
    else:
        c.execute('''UPDATE transactions 
                     SET status=?, retry_count=retry_count+1
                     WHERE order_id=?''',
                  (status, order_id))
    
    conn.commit()
    conn.close()

def get_all_transactions(limit=50):
    """Get all transactions"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    
    transactions = []
    for row in rows:
        transactions.append({
            'id': row[0],
            'order_id': row[1],
            'amount': row[2],
            'upi_id': row[3],
            'status': row[4],
            'transaction_id': row[5],
            'qr_code': row[6],
            'created_at': row[7],
            'verified_at': row[8],
            'retry_count': row[9]
        })
    return transactions

def get_pending_transactions():
    """Get all pending transactions"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM transactions 
                 WHERE status="pending" 
                 AND created_at > datetime('now', '-1 hour')
                 AND transaction_id IS NOT NULL''')
    rows = c.fetchall()
    conn.close()
    
    transactions = []
    for row in rows:
        transactions.append({
            'id': row[0],
            'order_id': row[1],
            'amount': row[2],
            'upi_id': row[3],
            'status': row[4],
            'transaction_id': row[5],
            'qr_code': row[6],
            'created_at': row[7],
            'verified_at': row[8],
            'retry_count': row[9]
        })
    return transactions

# ============================================
# API KEY FUNCTIONS
# ============================================

def generate_api_key():
    """Generate a new API key"""
    return f"PK_{secrets.token_hex(16).upper()}"

def create_api_key(user_name, email):
    """Create a new API key for a user"""
    api_key = generate_api_key()
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''INSERT INTO api_keys (api_key, user_name, email, created_at)
                 VALUES (?, ?, ?, ?)''',
              (api_key, user_name, email, datetime.now()))
    conn.commit()
    conn.close()
    return api_key

def get_api_keys():
    """Get all API keys"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('SELECT * FROM api_keys ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    
    keys = []
    for row in rows:
        keys.append({
            'id': row[0],
            'api_key': row[1],
            'user_name': row[2],
            'email': row[3],
            'created_at': row[4],
            'is_active': row[5]
        })
    return keys

def verify_api_key(api_key):
    """Verify if API key is valid"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('SELECT * FROM api_keys WHERE api_key=? AND is_active=1', (api_key,))
    row = c.fetchone()
    conn.close()
    return row is not None

def deactivate_api_key(api_key):
    """Deactivate an API key"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('UPDATE api_keys SET is_active=0 WHERE api_key=?', (api_key,))
    conn.commit()
    conn.close()

# ============================================
# API TRANSACTION FUNCTIONS (Live Feed)
# ============================================

def add_api_transaction(api_key, order_id, transaction_id, amount, status):
    """Add a transaction to API feed"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''INSERT INTO api_transactions 
                 (api_key, order_id, transaction_id, amount, status, created_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (api_key, order_id, transaction_id, amount, status, datetime.now()))
    conn.commit()
    conn.close()

def get_api_transactions(api_key=None, limit=100):
    """Get API transactions (live feed)"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    
    if api_key:
        c.execute('''SELECT * FROM api_transactions 
                     WHERE api_key=? 
                     ORDER BY created_at DESC LIMIT ?''',
                  (api_key, limit))
    else:
        c.execute('SELECT * FROM api_transactions ORDER BY created_at DESC LIMIT ?', (limit,))
    
    rows = c.fetchall()
    conn.close()
    
    transactions = []
    for row in rows:
        transactions.append({
            'id': row[0],
            'api_key': row[1],
            'order_id': row[2],
            'transaction_id': row[3],
            'amount': row[4],
            'status': row[5],
            'created_at': row[6]
        })
    return transactions

def get_api_transactions_by_order(order_id):
    """Get API transactions by order_id"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM api_transactions 
                 WHERE order_id=? 
                 ORDER BY created_at DESC''',
              (order_id,))
    rows = c.fetchall()
    conn.close()
    
    transactions = []
    for row in rows:
        transactions.append({
            'id': row[0],
            'api_key': row[1],
            'order_id': row[2],
            'transaction_id': row[3],
            'amount': row[4],
            'status': row[5],
            'created_at': row[6]
        })
    return transactions

# ============================================
# STATS FUNCTIONS
# ============================================

def get_stats():
    """Get statistics"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    
    # Total transactions
    c.execute('SELECT COUNT(*) FROM transactions')
    total = c.fetchone()[0]
    
    # Success transactions
    c.execute('SELECT COUNT(*) FROM transactions WHERE status="success"')
    success = c.fetchone()[0]
    
    # Pending transactions
    c.execute('SELECT COUNT(*) FROM transactions WHERE status="pending"')
    pending = c.fetchone()[0]
    
    # Cancelled transactions
    c.execute('SELECT COUNT(*) FROM transactions WHERE status="cancelled"')
    cancelled = c.fetchone()[0]
    
    # Total revenue
    c.execute('SELECT SUM(amount) FROM transactions WHERE status="success"')
    revenue = c.fetchone()[0] or 0
    
    # Total API keys
    c.execute('SELECT COUNT(*) FROM api_keys WHERE is_active=1')
    api_keys_count = c.fetchone()[0]
    
    conn.close()
    
    return {
        'total': total,
        'success': success,
        'pending': pending,
        'cancelled': cancelled,
        'revenue': revenue,
        'api_keys_count': api_keys_count
    }

# ============================================
# UTILITY FUNCTIONS
# ============================================

def clear_old_transactions(days=30):
    """Clear transactions older than specified days"""
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''DELETE FROM transactions 
                 WHERE created_at < datetime('now', ?) 
                 AND status="success"''',
              (f'-{days} days',))
    conn.commit()
    conn.close()

def get_db_size():
    """Get database file size"""
    import os
    if os.path.exists('gateway.db'):
        size = os.path.getsize('gateway.db')
        if size < 1024:
            return f"{size} bytes"
        elif size < 1024 * 1024:
            return f"{size/1024:.2f} KB"
        else:
            return f"{size/(1024*1024):.2f} MB"
    return "0 bytes"

# ============================================
# INITIALIZE DATABASE
# ============================================

if __name__ == '__main__':
    init_db()
    print("Database tables created successfully!")
    print(f"Database size: {get_db_size()}")