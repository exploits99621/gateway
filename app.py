from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
import json
import secrets
import sqlite3
import smtplib
import qrcode
from io import BytesIO
import base64
from datetime import datetime, timedelta
import hashlib
import time
import threading
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'MY_SECRET_KEY_12345'
app.permanent_session_lifetime = timedelta(days=36500)  # 100 years!

# ============================================
# DATABASE SETUP
# ============================================
def init_db():
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    
    # Settings (Gmail + FamPay)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY,
        gmail_email TEXT,
        gmail_password TEXT,
        fampay_id TEXT,
        fampay_api_key TEXT,
        logged_in BOOLEAN DEFAULT 0,
        login_time TIMESTAMP
    )''')
    
    # Transactions
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
    
    # API Keys for users
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        api_key TEXT UNIQUE,
        user_name TEXT,
        email TEXT,
        created_at TIMESTAMP,
        is_active BOOLEAN DEFAULT 1
    )''')
    
    # API Transactions (live)
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

init_db()

# ============================================
# DATABASE FUNCTIONS
# ============================================
def get_settings():
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
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''INSERT INTO settings 
                 (gmail_email, gmail_password, fampay_id, fampay_api_key, logged_in, login_time)
                 VALUES (?, ?, ?, ?, 1, ?)''',
              (gmail_email, gmail_password, fampay_id, fampay_api_key, datetime.now()))
    conn.commit()
    conn.close()

def update_login_status(status=True):
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('UPDATE settings SET logged_in=?, login_time=?', (status, datetime.now()))
    conn.commit()
    conn.close()

def save_transaction(order_id, amount, upi_id, qr_code):
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''INSERT INTO transactions 
                 (order_id, amount, upi_id, qr_code, created_at)
                 VALUES (?, ?, ?, ?, ?)''',
              (order_id, amount, upi_id, qr_code, datetime.now()))
    conn.commit()
    conn.close()

def get_transaction(order_id):
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
            'created_at': row[6],
            'verified_at': row[7],
            'retry_count': row[8]
        })
    return transactions

# ============================================
# API KEY FUNCTIONS
# ============================================
def generate_api_key():
    return f"PK_{secrets.token_hex(16).upper()}"

def create_api_key(user_name, email):
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

def get_api_transactions(api_key):
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('SELECT * FROM api_transactions WHERE api_key=? ORDER BY created_at DESC', (api_key,))
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

def add_api_transaction(api_key, order_id, transaction_id, amount, status):
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('''INSERT INTO api_transactions 
                 (api_key, order_id, transaction_id, amount, status, created_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (api_key, order_id, transaction_id, amount, status, datetime.now()))
    conn.commit()
    conn.close()

# ============================================
# QR CODE GENERATION
# ============================================
def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

# ============================================
# FAMPAY VERIFICATION
# ============================================
def verify_with_fampay(transaction_id):
    """Verify transaction with FamPay"""
    settings = get_settings()
    if not settings:
        return {'status': 'error', 'message': 'Settings not configured'}
    
    try:
        # FamPay verification API
        url = "https://fampaygateway.site/api/verify.php"
        params = {
            'order_id': transaction_id,
            'api_key': settings['fampay_api_key']
        }
        
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
        
        if data.get('status') == 'success':
            payment_data = data.get('data', {})
            return {
                'status': 'success',
                'amount': payment_data.get('amount'),
                'utr': payment_data.get('utr'),
                'payment_time': payment_data.get('payment_time')
            }
        else:
            return {'status': 'pending', 'message': 'Transaction not found'}
            
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

# ============================================
# EMAIL NOTIFICATION
# ============================================
def send_email(subject, body):
    settings = get_settings()
    if not settings:
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = settings['gmail_email']
        msg['To'] = settings['gmail_email']
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(settings['gmail_email'], settings['gmail_password'])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# ============================================
# ROUTES
# ============================================

@app.route('/')
def index():
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Check if already logged in (100 years session)
    settings = get_settings()
    if settings and settings.get('logged_in'):
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        gmail = request.form.get('gmail')
        app_password = request.form.get('app_password')
        fampay_id = request.form.get('fampay_id')
        fampay_api_key = request.form.get('fampay_api_key')
        
        # Verify Gmail login
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(gmail, app_password)
            server.quit()
            
            # Save settings with auto-login
            save_settings(gmail, app_password, fampay_id, fampay_api_key)
            session.permanent = True
            
            # Send welcome email
            send_email(
                "✅ Gateway Activated!",
                f"""
                <h2>Your Payment Gateway is Live!</h2>
                <p><strong>FamPay ID:</strong> {fampay_id}</p>
                <p><strong>Logged in:</strong> {datetime.now()}</p>
                <p>You'll receive notifications for all payments.</p>
                """
            )
            
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            return render_template('login.html', error=f'Gmail login failed: {str(e)}')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    
    transactions = get_all_transactions(20)
    total = len(transactions)
    success = len([t for t in transactions if t['status'] == 'success'])
    pending = len([t for t in transactions if t['status'] == 'pending'])
    
    return render_template('dashboard.html',
                         settings=settings,
                         transactions=transactions,
                         total=total,
                         success=success,
                         pending=pending)

@app.route('/generate', methods=['GET', 'POST'])
def generate_qr_page():
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        amount = float(request.form.get('amount'))
        
        # Generate unique order ID
        order_id = f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4).upper()}"
        
        # Create QR data
        qr_data = {
            'order_id': order_id,
            'amount': amount,
            'upi_id': settings['fampay_id'],
            'pay': f"upi://pay?pa={settings['fampay_id']}&am={amount}&cu=INR&tn=Payment%20{order_id}"
        }
        
        # Generate QR
        qr_code = generate_qr(qr_data['pay'])
        
        # Save to database
        save_transaction(order_id, amount, settings['fampay_id'], qr_code)
        
        return render_template('verify.html',
                             order_id=order_id,
                             amount=amount,
                             qr_code=qr_code,
                             upi_id=settings['fampay_id'])
    
    return render_template('generate_qr.html')

@app.route('/verify', methods=['POST'])
def verify_payment():
    order_id = request.form.get('order_id')
    transaction_id = request.form.get('transaction_id')
    
    if not order_id or not transaction_id:
        return jsonify({'status': 'error', 'message': 'Order ID and Transaction ID required'})
    
    # Get transaction
    txn = get_transaction(order_id)
    if not txn:
        return jsonify({'status': 'error', 'message': 'Order not found'})
    
    # Verify with FamPay
    result = verify_with_fampay(transaction_id)
    
    if result['status'] == 'success':
        # Payment verified
        update_transaction(order_id, 'success', transaction_id)
        
        # Send notification
        send_email(
            f"✅ Payment Received - {order_id}",
            f"""
            <h2>Payment Successful!</h2>
            <p><strong>Order ID:</strong> {order_id}</p>
            <p><strong>Amount:</strong> ₹{txn['amount']}</p>
            <p><strong>Transaction ID:</strong> {transaction_id}</p>
            <p><strong>Time:</strong> {datetime.now()}</p>
            """
        )
        
        return jsonify({
            'status': 'success',
            'message': 'Payment verified!',
            'amount': txn['amount']
        })
    
    elif result['status'] == 'pending':
        # Retry logic - 5-6 seconds
        time.sleep(5)
        
        # Retry verification
        retry_result = verify_with_fampay(transaction_id)
        
        if retry_result['status'] == 'success':
            update_transaction(order_id, 'success', transaction_id)
            return jsonify({
                'status': 'success',
                'message': 'Payment verified after retry!',
                'amount': txn['amount']
            })
        else:
            # Cancel payment
            update_transaction(order_id, 'cancelled')
            return jsonify({
                'status': 'cancelled',
                'message': 'Payment verification failed. Order cancelled.'
            })
    
    else:
        return jsonify({
            'status': 'error',
            'message': result.get('message', 'Verification failed')
        })

@app.route('/api/create', methods=['POST'])
def api_create_payment():
    """External API for others to create payment"""
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API Key required'}), 401
    
    # Verify API key
    conn = sqlite3.connect('gateway.db')
    c = conn.cursor()
    c.execute('SELECT * FROM api_keys WHERE api_key=? AND is_active=1', (api_key,))
    key_data = c.fetchone()
    conn.close()
    
    if not key_data:
        return jsonify({'error': 'Invalid API Key'}), 401
    
    amount = request.json.get('amount')
    if not amount:
        return jsonify({'error': 'Amount required'}), 400
    
    # Generate order
    order_id = f"API_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4).upper()}"
    settings = get_settings()
    
    # Generate QR
    qr_data = f"upi://pay?pa={settings['fampay_id']}&am={amount}&cu=INR&tn=Payment%20{order_id}"
    qr_code = generate_qr(qr_data)
    
    # Save
    save_transaction(order_id, amount, settings['fampay_id'], qr_code)
    
    # Add to API transactions
    add_api_transaction(api_key, order_id, None, amount, 'pending')
    
    return jsonify({
        'status': 'success',
        'order_id': order_id,
        'amount': amount,
        'qr_code': qr_code,
        'upi_id': settings['fampay_id']
    })

@app.route('/api/verify', methods=['POST'])
def api_verify_payment():
    """External API to verify payment"""
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return jsonify({'error': 'API Key required'}), 401
    
    order_id = request.json.get('order_id')
    transaction_id = request.json.get('transaction_id')
    
    if not order_id or not transaction_id:
        return jsonify({'error': 'Order ID and Transaction ID required'}), 400
    
    # Verify with FamPay
    result = verify_with_fampay(transaction_id)
    
    if result['status'] == 'success':
        update_transaction(order_id, 'success', transaction_id)
        add_api_transaction(api_key, order_id, transaction_id, 0, 'success')
        return jsonify({
            'status': 'success',
            'message': 'Payment verified'
        })
    else:
        return jsonify({
            'status': 'pending',
            'message': 'Payment not found'
        })

@app.route('/api-keys', methods=['GET', 'POST'])
def manage_api_keys():
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        user_name = request.form.get('user_name')
        email = request.form.get('email')
        
        api_key = create_api_key(user_name, email)
        
        return jsonify({
            'status': 'success',
            'api_key': api_key,
            'user_name': user_name,
            'email': email
        })
    
    keys = get_api_keys()
    return render_template('api_keys.html', keys=keys)

@app.route('/api-docs')
def api_docs():
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    
    return render_template('api_docs.html', gateway_url=request.host_url)

@app.route('/transaction/<order_id>')
def transaction_detail(order_id):
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    
    txn = get_transaction(order_id)
    if not txn:
        return "Transaction not found", 404
    
    return render_template('transaction_detail.html', txn=txn)

@app.route('/logout')
def logout():
    update_login_status(False)
    return redirect(url_for('login'))

# ============================================
# AUTO-VERIFY BACKGROUND THREAD
# ============================================
def auto_verify_worker():
    """Background thread to auto-verify pending transactions"""
    while True:
        try:
            settings = get_settings()
            if not settings or not settings.get('logged_in'):
                time.sleep(60)
                continue
            
            # Get pending transactions
            conn = sqlite3.connect('gateway.db')
            c = conn.cursor()
            c.execute('''SELECT order_id, transaction_id FROM transactions 
                         WHERE status="pending" AND transaction_id IS NOT NULL
                         AND created_at > datetime('now', '-1 hour')''')
            pending = c.fetchall()
            conn.close()
            
            for row in pending:
                order_id = row[0]
                transaction_id = row[1]
                
                # Verify
                result = verify_with_fampay(transaction_id)
                if result['status'] == 'success':
                    update_transaction(order_id, 'success', transaction_id)
                    send_email(
                        f"✅ Auto-Verified - {order_id}",
                        f"<h2>Payment Auto-Verified!</h2><p>Order: {order_id}</p>"
                    )
            
            time.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            print(f"Auto-verify error: {e}")
            time.sleep(60)

# Start background thread
thread = threading.Thread(target=auto_verify_worker, daemon=True)
thread.start()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)