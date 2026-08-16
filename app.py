from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import secrets
import smtplib
import qrcode
from io import BytesIO
import base64
from datetime import datetime, timedelta
import time
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'FIXED_SECRET_KEY_2024'
app.permanent_session_lifetime = timedelta(days=36500)

# ============================================
# DATABASE SETUP (SQLite - Vercel Compatible)
# ============================================

def init_db():
    conn = sqlite3.connect('/tmp/gateway.db')  # Vercel temp path
    c = conn.cursor()
    
    # Settings table
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY,
        gmail_email TEXT,
        gmail_password TEXT,
        fampay_id TEXT,
        fampay_api_key TEXT,
        logged_in INTEGER DEFAULT 0,
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
        is_active INTEGER DEFAULT 1
    )''')
    
    # API Transactions table
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
    print("✅ Database initialized!")

# Initialize database
init_db()

# ============================================
# DATABASE FUNCTIONS
# ============================================

def get_db():
    conn = sqlite3.connect('/tmp/gateway.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_settings():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def save_settings(gmail_email, gmail_password, fampay_id, fampay_api_key):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO settings 
                 (gmail_email, gmail_password, fampay_id, fampay_api_key, logged_in, login_time)
                 VALUES (?, ?, ?, ?, 1, ?)''',
              (gmail_email, gmail_password, fampay_id, fampay_api_key, datetime.now()))
    conn.commit()
    conn.close()

def update_login_status(status=True):
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE settings SET logged_in=?, login_time=?', (1 if status else 0, datetime.now()))
    conn.commit()
    conn.close()

def save_transaction(order_id, amount, upi_id, qr_code):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO transactions 
                 (order_id, amount, upi_id, qr_code, created_at)
                 VALUES (?, ?, ?, ?, ?)''',
              (order_id, amount, upi_id, qr_code, datetime.now()))
    conn.commit()
    conn.close()

def get_transaction(order_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM transactions WHERE order_id=?', (order_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def update_transaction(order_id, status, transaction_id=None):
    conn = get_db()
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
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_pending_transactions():
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT * FROM transactions 
                 WHERE status="pending" 
                 AND created_at > datetime('now', '-1 hour')
                 AND transaction_id IS NOT NULL''')
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM transactions')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM transactions WHERE status="success"')
    success = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM transactions WHERE status="pending"')
    pending = c.fetchone()[0]
    c.execute('SELECT SUM(amount) FROM transactions WHERE status="success"')
    revenue = c.fetchone()[0] or 0
    conn.close()
    return {'total': total, 'success': success, 'pending': pending, 'revenue': revenue}

def create_api_key(user_name, email):
    api_key = f"PK_{secrets.token_hex(16).upper()}"
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO api_keys (api_key, user_name, email, created_at)
                 VALUES (?, ?, ?, ?)''',
              (api_key, user_name, email, datetime.now()))
    conn.commit()
    conn.close()
    return api_key

def get_api_keys():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM api_keys ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def verify_api_key(api_key):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM api_keys WHERE api_key=? AND is_active=1', (api_key,))
    row = c.fetchone()
    conn.close()
    return row is not None

def add_api_transaction(api_key, order_id, transaction_id, amount, status):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO api_transactions 
                 (api_key, order_id, transaction_id, amount, status, created_at)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (api_key, order_id, transaction_id, amount, status, datetime.now()))
    conn.commit()
    conn.close()

def get_api_transactions(api_key=None, limit=100):
    conn = get_db()
    c = conn.cursor()
    if api_key:
        c.execute('SELECT * FROM api_transactions WHERE api_key=? ORDER BY created_at DESC LIMIT ?', (api_key, limit))
    else:
        c.execute('SELECT * FROM api_transactions ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

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
    import requests
    settings = get_settings()
    if not settings:
        return {'status': 'error', 'message': 'Settings not configured'}
    
    try:
        url = "https://fampaygateway.site/api/verify.php"
        params = {
            'order_id': transaction_id,
            'api_key': settings.get('fampay_api_key', 'FAM_371735AC5A8C95B29EDB8EA7E7CD51DA57863D3C')
        }
        response = requests.get(url, params=params, timeout=30)
        data = response.json()
        if data.get('status') == 'success':
            return {'status': 'success', 'data': data.get('data', {})}
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
    if settings and settings.get('logged_in'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    settings = get_settings()
    if settings and settings.get('logged_in'):
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        gmail = request.form.get('gmail')
        app_password = request.form.get('app_password')
        fampay_id = request.form.get('fampay_id')
        fampay_api_key = request.form.get('fampay_api_key')
        
        if not gmail or not app_password:
            return render_template('login.html', error='Gmail and App Password required')
        
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(gmail, app_password)
            server.quit()
            
            save_settings(gmail, app_password, fampay_id or '9817317740@fam', 
                         fampay_api_key or 'FAM_371735AC5A8C95B29EDB8EA7E7CD51DA57863D3C')
            session.permanent = True
            
            send_email("✅ Gateway Activated!", f"<h2>Your Gateway is Live!</h2><p>FamPay ID: {fampay_id}</p>")
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            return render_template('login.html', error=f'Login failed: {str(e)}')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    
    transactions = get_all_transactions(20)
    stats = get_stats()
    
    return render_template('dashboard.html',
                         settings=settings,
                         transactions=transactions,
                         total=stats['total'],
                         success=stats['success'],
                         pending=stats['pending'],
                         revenue=stats['revenue'])

@app.route('/generate', methods=['GET', 'POST'])
def generate_qr_page():
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        if amount <= 0:
            return render_template('generate_qr.html', error='Invalid amount')
        
        order_id = f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4).upper()}"
        upi_id = settings.get('fampay_id', '9817317740@fam')
        upi_link = f"upi://pay?pa={upi_id}&am={amount}&cu=INR&tn=Payment%20{order_id}"
        qr_code = generate_qr(upi_link)
        
        save_transaction(order_id, amount, upi_id, qr_code)
        
        return render_template('verify.html',
                             order_id=order_id,
                             amount=amount,
                             qr_code=qr_code,
                             upi_id=upi_id)
    
    return render_template('generate_qr.html')

@app.route('/verify', methods=['POST'])
def verify_payment():
    order_id = request.form.get('order_id')
    transaction_id = request.form.get('transaction_id')
    
    if not order_id or not transaction_id:
        return jsonify({'status': 'error', 'message': 'Order ID and Transaction ID required'})
    
    txn = get_transaction(order_id)
    if not txn:
        return jsonify({'status': 'error', 'message': 'Order not found'})
    
    result = verify_with_fampay(transaction_id)
    
    if result.get('status') == 'success':
        update_transaction(order_id, 'success', transaction_id)
        send_email(f"✅ Payment Received - {order_id}", 
                  f"<h2>Payment Successful!</h2><p>Amount: ₹{txn['amount']}</p><p>Transaction: {transaction_id}</p>")
        return jsonify({'status': 'success', 'message': 'Payment verified!', 'amount': txn['amount']})
    
    elif result.get('status') == 'pending':
        time.sleep(5)
        retry_result = verify_with_fampay(transaction_id)
        if retry_result.get('status') == 'success':
            update_transaction(order_id, 'success', transaction_id)
            return jsonify({'status': 'success', 'message': 'Payment verified after retry!', 'amount': txn['amount']})
        else:
            update_transaction(order_id, 'cancelled')
            return jsonify({'status': 'cancelled', 'message': 'Payment verification failed. Order cancelled.'})
    else:
        return jsonify({'status': 'error', 'message': result.get('message', 'Verification failed')})

@app.route('/api-keys', methods=['GET', 'POST'])
def manage_api_keys():
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        user_name = request.form.get('user_name')
        email = request.form.get('email')
        if not user_name or not email:
            return jsonify({'status': 'error', 'message': 'Name and email required'})
        api_key = create_api_key(user_name, email)
        return jsonify({'status': 'success', 'api_key': api_key, 'user_name': user_name, 'email': email})
    
    keys = get_api_keys()
    return render_template('api_keys.html', keys=keys)

@app.route('/api-docs')
def api_docs():
    settings = get_settings()
    if not settings or not settings.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('api_docs.html', gateway_url=request.host_url)

@app.route('/api/create', methods=['POST'])
def api_create_payment():
    api_key = request.headers.get('X-API-Key')
    if not api_key or not verify_api_key(api_key):
        return jsonify({'error': 'Invalid API Key'}), 401
    
    amount = request.json.get('amount')
    if not amount:
        return jsonify({'error': 'Amount required'}), 400
    
    amount = float(amount)
    settings = get_settings()
    order_id = f"API_{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4).upper()}"
    upi_id = settings.get('fampay_id', '9817317740@fam')
    upi_link = f"upi://pay?pa={upi_id}&am={amount}&cu=INR&tn=Payment%20{order_id}"
    qr_code = generate_qr(upi_link)
    
    save_transaction(order_id, amount, upi_id, qr_code)
    add_api_transaction(api_key, order_id, None, amount, 'pending')
    
    return jsonify({'status': 'success', 'order_id': order_id, 'amount': amount, 'qr_code': qr_code, 'upi_id': upi_id})

@app.route('/api/verify', methods=['POST'])
def api_verify_payment():
    api_key = request.headers.get('X-API-Key')
    if not api_key or not verify_api_key(api_key):
        return jsonify({'error': 'Invalid API Key'}), 401
    
    order_id = request.json.get('order_id')
    transaction_id = request.json.get('transaction_id')
    
    if not order_id or not transaction_id:
        return jsonify({'error': 'Order ID and Transaction ID required'}), 400
    
    result = verify_with_fampay(transaction_id)
    if result.get('status') == 'success':
        update_transaction(order_id, 'success', transaction_id)
        add_api_transaction(api_key, order_id, transaction_id, 0, 'success')
        return jsonify({'status': 'success', 'message': 'Payment verified'})
    else:
        return jsonify({'status': 'pending', 'message': 'Payment not found'})

@app.route('/logout')
def logout():
    update_login_status(False)
    return redirect(url_for('login'))

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error='Internal server error'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    return render_template('error.html', error=str(e)), 500

# ============================================
# RUN APP
# ============================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
