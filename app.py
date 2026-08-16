import sys
import traceback
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'test_key_123'

# ============================================
# DIAGNOSTIC ROUTE - SABSE PEHLE YE CHECK KAREIN
# ============================================

@app.route('/')
def index():
    try:
        return "✅ Server is working! Flask is running."
    except Exception as e:
        return f"❌ Error: {str(e)}"

@app.route('/test')
def test():
    """Test route to check all imports"""
    import sys
    import os
    import flask
    import requests
    import qrcode
    import sqlite3
    
    result = {
        'python_version': sys.version,
        'flask_version': flask.__version__,
        'requests_installed': 'requests' in sys.modules,
        'qrcode_installed': 'qrcode' in sys.modules,
        'sqlite3_installed': 'sqlite3' in sys.modules,
        'working_directory': os.getcwd(),
        'files_in_dir': os.listdir('.') if os.path.exists('.') else []
    }
    return jsonify(result)

@app.route('/db-test')
def db_test():
    """Test database connection"""
    try:
        import sqlite3
        conn = sqlite3.connect('/tmp/test.db')
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS test (id INTEGER)')
        c.execute('INSERT INTO test VALUES (1)')
        conn.commit()
        c.execute('SELECT * FROM test')
        data = c.fetchall()
        conn.close()
        return jsonify({'status': 'success', 'data': data})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e), 'traceback': traceback.format_exc()})

@app.route('/import-test')
def import_test():
    """Test all imports one by one"""
    results = {}
    
    # Test each import
    modules = [
        ('Flask', 'flask'),
        ('requests', 'requests'),
        ('qrcode', 'qrcode'),
        ('sqlite3', 'sqlite3'),
        ('smtplib', 'smtplib'),
        ('email', 'email'),
        ('base64', 'base64'),
        ('datetime', 'datetime'),
        ('secrets', 'secrets'),
        ('threading', 'threading'),
        ('time', 'time'),
        ('json', 'json'),
        ('os', 'os'),
        ('sys', 'sys')
    ]
    
    for name, module in modules:
        try:
            __import__(module)
            results[name] = '✅ Installed'
        except Exception as e:
            results[name] = f'❌ {str(e)}'
    
    return jsonify(results)

@app.route('/full-test')
def full_test():
    """Complete test - try to import everything"""
    try:
        # Try full app import
        import sys
        import os
        import flask
        import requests
        import qrcode
        import sqlite3
        import smtplib
        import email
        import base64
        import datetime
        import secrets
        import threading
        import time
        import json
        from io import BytesIO
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        return jsonify({
            'status': 'ALL IMPORTS SUCCESSFUL',
            'flask_version': flask.__version__,
            'python_version': sys.version,
            'working_dir': os.getcwd()
        })
    except Exception as e:
        return jsonify({
            'status': 'IMPORT FAILED',
            'error': str(e),
            'traceback': traceback.format_exc()
        })

# ============================================
# MAIN APP
# ============================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
