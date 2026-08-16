from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
import json
import secrets
import smtplib
import qrcode
from io import BytesIO
import base64
from datetime import datetime, timedelta
import hashlib
import time
import threading
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================
# FLASK APP INITIALIZATION
# ============================================
app = Flask(__name__)
app.secret_key = 'MY_SECRET_KEY_12345_VERY_SECURE'
app.permanent_session_lifetime = timedelta(days=36500)

# ============================================
# DATABASE IMPORT WITH ERROR HANDLING
# ============================================
try:
    from database import *
    print("✅ Database module imported successfully!")
except ImportError as e:
    print(f"❌ Database import error: {e}")
    # Fallback functions if database import fails
    def get_settings():
        return None
    def save_settings(gmail_email, gmail_password, fampay_id, fampay_api_key):
        return None
    def save_transaction(order_id, amount, upi_id, qr_code):
        return None
    def get_transaction(order_id):
        return None
    def update_transaction(order_id, status, transaction_id=None):
        return None
    def get_all_transactions(limit=50):
        return []
    def get_stats():
        return {'total': 0, 'success': 0, 'pending': 0, 'revenue': 0}
    def create_api_key(user_name, email):
        return None
    def get_api_keys():
        return []
    def verify_api_key(api_key):
        return False
    def add_api_transaction(api_key, order_id, transaction_id, amount, status):
        return None
    def get_api_transactions(api_key=None, limit=100):
        return []
    def get_pending_transactions():
        return []
    def update_login_status(status=True):
        return None

# ============================================
# SUPABASE CONNECTION TEST
# ============================================
def test_database_connection():
    """Test if database is connected"""
    try:
        settings = get_settings()
        if settings:
            print("✅ Database connected! Settings found.")
            return True
        else:
            print("⚠️ Database connected but no settings found.")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

# Test connection on startup
with app.app_context():
    test_database_connection()

# ============================================
# QR CODE GENERATION
# ============================================
def generate_qr(data):
    """Generate QR code from data"""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        print(f"QR generation error: {e}")
        return None

# ============================================
# FAMPAY VERIFICATION
# ============================================
def verify_with_fampay(transaction_id):
    """Verify transaction with FamPay"""
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
        print(f"FamPay verification error: {e}")
        return {'status': 'error', 'message': str(e)}

# ============================================
# EMAIL NOTIFICATION
# ============================================
def send_email(subject, body):
    """Send email via Gmail"""
    settings = get_settings()
    if not settings:
        print("❌ No settings found for email")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = settings.get('gmail_email')
        msg['To'] = settings.get('gmail_email')
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(settings.get('gmail_email'), settings.get('gmail_password'))
        server.send_message(msg)
        server.quit()
        print(f"✅ Email sent: {subject}")
        return True
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False

# ============================================
# GENERATE ORDER ID
# ============================================
def generate_order_id():
    """Generate unique order ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_part = secrets.token_hex(4).upper()
    return f"ORD_{timestamp}_{random_part}"

# ============================================
# BACKGROUND AUTO-VERIFY THREAD
# ============================================
def auto_verify_worker():
    """Background thread to verify pending payments"""
    while True:
        try:
            settings = get_settings()
            if not settings:
                time.sleep(60)
                continue
            
            pending = get_pending_transactions()
            for txn in pending:
                if txn.get('transaction_id'):
                    result = verify_with_fampay(txn['transaction_id'])
                    if result.get('status') == 'success':
                        update_transaction(txn['order_id'], 'success', txn['transaction_id'])
                        send_email(
                            f"✅ Payment Auto-Verified - {txn['order_id']}",
                            f"<h2>Payment Confirmed!</h2><p>Order: {txn['order_id']}</p><p>Amount: ₹{txn['amount']}</p>"
                        )
            
            time.sleep(30)
            
        except Exception as e:
            print(f"Auto-verify error: {e}")
            time.sleep(60)

# Start background thread
try:
    thread = threading.Thread(target=auto_verify_worker, daemon=True)
    thread.start()
    print("✅ Auto-verify thread started")
except Exception as e:
    print(f"❌ Failed to start auto-verify thread: {e}")

# ============================================
# ROUTES
# ============================================

@app.route('/')
def index():
    """Home page - redirect to login or dashboard"""
    try:
        settings = get_settings()
        if settings and settings.get('logged_in'):
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))
    except Exception as e:
        print(f"Index error: {e}")
        return render_template('error.html', error=str(e))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    try:
        # Check if already logged in
        settings = get_settings()
        if settings and settings.get('logged_in'):
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            gmail = request.form.get('gmail')
            app_password = request.form.get('app_password')
            fampay_id = request.form.get('fampay_id')
            fampay_api_key = request.form.get('fampay_api_key')
            
            # Validate inputs
            if not gmail or not app_password or not fampay_id:
                return render_template('login.html', error='All fields are required')
            
            # Verify Gmail login
            try:
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(gmail, app_password)
                server.quit()
                
                # Save settings
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
        
    except Exception as e:
        print(f"Login error: {e}")
        return render_template('error.html', error=str(e))

@app.route('/dashboard')
def dashboard():
    """Dashboard page"""
    try:
        settings = get_settings()
        if not settings or not settings.get('logged_in'):
            return redirect(url_for('login'))
        
        transactions = get_all_transactions(20)
        stats = get_stats()
        
        return render_template('dashboard.html',
                             settings=settings,
                             transactions=transactions,
                             total=stats.get('total', 0),
                             success=stats.get('success', 0),
                             pending=stats.get('pending', 0))
                             
    except Exception as e:
        print(f"Dashboard error: {e}")
        return render_template('error.html', error=str(e))

@app.route('/generate', methods=['GET', 'POST'])
def generate_qr_page():
    """Generate QR code page"""
    try:
        settings = get_settings()
        if not settings or not settings.get('logged_in'):
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            amount = float(request.form.get('amount', 0))
            if amount <= 0:
                return render_template('generate_qr.html', error='Invalid amount')
            
            order_id = generate_order_id()
            upi_id = settings.get('fampay_id', '9817317740@fam')
            
            # Create UPI payment link
            upi_link = f"upi://pay?pa={upi_id}&am={amount}&cu=INR&tn=Payment%20{order_id}"
            
            # Generate QR
            qr_code = generate_qr(upi_link)
            if not qr_code:
                return render_template('generate_qr.html', error='QR generation failed')
            
            # Save to database
            save_transaction(order_id, amount, upi_id, qr_code)
            
            return render_template('verify.html',
                                 order_id=order_id,
                                 amount=amount,
                                 qr_code=qr_code,
                                 upi_id=upi_id)
        
        return render_template('generate_qr.html')
        
    except Exception as e:
        print(f"Generate QR error: {e}")
        return render_template('error.html', error=str(e))

@app.route('/verify', methods=['POST'])
def verify_payment():
    """Verify payment with transaction ID"""
    try:
        settings = get_settings()
        if not settings or not settings.get('logged_in'):
            return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
        
        order_id = request.form.get('order_id')
        transaction_id = request.form.get('transaction_id')
        
        if not order_id or not transaction_id:
            return jsonify({'status': 'error', 'message': 'Order ID and Transaction ID required'}), 400
        
        # Get transaction
        txn = get_transaction(order_id)
        if not txn:
            return jsonify({'status': 'error', 'message': 'Order not found'}), 404
        
        # Verify with FamPay
        result = verify_with_fampay(transaction_id)
        
        if result.get('status') == 'success':
            update_transaction(order_id, 'success', transaction_id)
            
            send_email(
                f"✅ Payment Received - {order_id}",
                f"""
                <h2>Payment Successful!</h2>
                <p><strong>Order ID:</strong> {order_id}</p>
                <p><strong>Amount:</strong> ₹{txn['amount']}</p>
                <p><strong>Transaction ID:</strong> {transaction_id}</p>
                """
            )
            
            return jsonify({
                'status': 'success',
                'message': 'Payment verified!',
                'amount': txn['amount']
            })
            
        elif result.get('status') == 'pending':
            # Retry after 5 seconds
            time.sleep(5)
            retry_result = verify_with_fampay(transaction_id)
            
            if retry_result.get('status') == 'success':
                update_transaction(order_id, 'success', transaction_id)
                return jsonify({
                    'status': 'success',
                    'message': 'Payment verified after retry!',
                    'amount': txn['amount']
                })
            else:
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
            
    except Exception as e:
        print(f"Verify error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api-keys', methods=['GET', 'POST'])
def manage_api_keys():
    """API Keys management"""
    try:
        settings = get_settings()
        if not settings or not settings.get('logged_in'):
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            user_name = request.form.get('user_name')
            email = request.form.get('email')
            
            if not user_name or not email:
                return jsonify({'status': 'error', 'message': 'Name and email required'}), 400
            
            api_key = create_api_key(user_name, email)
            if api_key:
                return jsonify({
                    'status': 'success',
                    'api_key': api_key,
                    'user_name': user_name,
                    'email': email
                })
            else:
                return jsonify({'status': 'error', 'message': 'Failed to create API key'}), 500
        
        keys = get_api_keys()
        return render_template('api_keys.html', keys=keys)
        
    except Exception as e:
        print(f"API Keys error: {e}")
        return render_template('error.html', error=str(e))

@app.route('/api-docs')
def api_docs():
    """API Documentation"""
    try:
        settings = get_settings()
        if not settings or not settings.get('logged_in'):
            return redirect(url_for('login'))
        
        return render_template('api_docs.html', gateway_url=request.host_url)
    except Exception as e:
        print(f"API Docs error: {e}")
        return render_template('error.html', error=str(e))

@app.route('/api/create', methods=['POST'])
def api_create_payment():
    """External API: Create payment"""
    try:
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API Key required'}), 401
        
        if not verify_api_key(api_key):
            return jsonify({'error': 'Invalid API Key'}), 401
        
        amount = request.json.get('amount')
        if not amount:
            return jsonify({'error': 'Amount required'}), 400
        
        amount = float(amount)
        if amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400
        
        settings = get_settings()
        if not settings:
            return jsonify({'error': 'Gateway not configured'}), 500
        
        order_id = generate_order_id()
        upi_id = settings.get('fampay_id', '9817317740@fam')
        upi_link = f"upi://pay?pa={upi_id}&am={amount}&cu=INR&tn=Payment%20{order_id}"
        
        qr_code = generate_qr(upi_link)
        if not qr_code:
            return jsonify({'error': 'QR generation failed'}), 500
        
        save_transaction(order_id, amount, upi_id, qr_code)
        add_api_transaction(api_key, order_id, None, amount, 'pending')
        
        return jsonify({
            'status': 'success',
            'order_id': order_id,
            'amount': amount,
            'qr_code': qr_code,
            'upi_id': upi_id
        })
        
    except Exception as e:
        print(f"API create error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/verify', methods=['POST'])
def api_verify_payment():
    """External API: Verify payment"""
    try:
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API Key required'}), 401
        
        if not verify_api_key(api_key):
            return jsonify({'error': 'Invalid API Key'}), 401
        
        order_id = request.json.get('order_id')
        transaction_id = request.json.get('transaction_id')
        
        if not order_id or not transaction_id:
            return jsonify({'error': 'Order ID and Transaction ID required'}), 400
        
        result = verify_with_fampay(transaction_id)
        
        if result.get('status') == 'success':
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
            
    except Exception as e:
        print(f"API verify error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    """Logout"""
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
    return render_template('error.html', error='Internal server error. Please check logs.'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    print(f"Unhandled exception: {e}")
    return render_template('error.html', error=str(e)), 500

# ============================================
# RUN APP
# ============================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
