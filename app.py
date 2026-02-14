from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
import sqlite3
import json
from datetime import datetime, date
import csv
import io
import os
import hashlib
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)

# Database configuration
DATABASE = 'job_tracker.db'

def get_db_connection():
    """Create a database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    """Hash a password with salt."""
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return salt + ':' + password_hash.hex()

def verify_password(password, hashed):
    """Verify a password against its hash."""
    try:
        salt, password_hash = hashed.split(':')
        return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex() == password_hash
    except:
        return False

def init_db():
    """Initialize the database with required tables."""
    conn = get_db_connection()
    
    # Create users table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create jobs table with user_id foreign key
    conn.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company TEXT NOT NULL,
            position TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'applied',
            applied_date DATE,
            job_url TEXT,
            salary TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create indexes for better performance
    conn.execute('CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
    
    conn.commit()
    conn.close()

def dict_factory(cursor, row):
    """Convert database row to dictionary."""
    d = {}
    for idx, col in enumerate(cursor.description):
        value = row[idx]
        # Convert date strings to proper format for frontend
        if col[0] in ['applied_date', 'created_at', 'updated_at'] and value:
            if isinstance(value, str):
                try:
                    # Parse different date formats
                    if 'T' in value:  # ISO format with time
                        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        d[col[0]] = dt.date().isoformat()
                    else:  # Date only
                        d[col[0]] = value
                except ValueError:
                    d[col[0]] = value
            else:
                d[col[0]] = value
        else:
            d[col[0]] = value
    return d

def login_required(f):
    """Decorator to require login for routes."""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Routes
@app.route('/')
def landing():
    """Serve the landing page."""
    print(f"Landing route called. Session: {dict(session)}")
    if 'user_id' in session:
        print("User is logged in, redirecting to dashboard")
        return redirect(url_for('dashboard'))
    print("User not logged in, showing landing page")
    return render_template('landing.html')

@app.route('/dashboard')
def dashboard():
    """Serve the main dashboard page."""
    print(f"Dashboard route called. Session: {dict(session)}")
    if 'user_id' not in session:
        print("User not logged in, redirecting to landing")
        return redirect(url_for('landing'))
    print("User is logged in, showing dashboard")
    return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def register():
    """Register a new user."""
    data = request.get_json()
    print(f"Register request: {data}")
    
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    confirm_password = data.get('confirmPassword', '')

    errors = {}

    # Validation
    if not username:
        errors['username'] = "Username is required"
    elif len(username) < 3:
        errors['username'] = "Username must be at least 3 characters"

    if not email:
        errors['email'] = "Email is required"
    elif '@' not in email:
        errors['email'] = "Please enter a valid email address"

    if not password:
        errors['password'] = "Password is required"
    elif len(password) < 6:
        errors['password'] = "Password must be at least 6 characters"

    if password != confirm_password:
        errors['confirmPassword'] = "Passwords do not match"

    if errors:
        return jsonify({"errors": errors}), 400

    try:
        with get_db_connection() as conn:
            # Check if username or email already exists
            username_exists = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            email_exists = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()

            if username_exists or email_exists:
                message = "Username or email is not available"
                errors['username'] = message
                errors['email'] = message

            if errors:
                return jsonify({"errors": errors}), 400

            # Create new user
            password_hash = hash_password(password)
            cursor = conn.execute('''
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
            ''', (username, email, password_hash))

            user_id = cursor.lastrowid
            conn.commit()

        session['user_id'] = user_id
        session['username'] = username
        print(f"User {username} registered and logged in with ID {user_id}")

        return jsonify({'message': 'Registration successful'}), 201

    except Exception as e:
        print(f"Registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500



@app.route('/api/login', methods=['POST'])
def login():
    """Log in a user with username or email."""
    data = request.get_json()
    print(f"Login request: {data}")
    
    identifier = data.get('username', '').strip()  # could be username or email
    password = data.get('password', '')

    if not identifier or not password:
        return jsonify({'error': 'Username/Email and password are required'}), 400

    try:
        with get_db_connection() as conn:
            # Try to find by username first, then by email
            user = conn.execute(
                'SELECT id, username, email, password_hash FROM users WHERE username = ?',
                (identifier,)
            ).fetchone()

            if not user:
                user = conn.execute(
                    'SELECT id, username, email, password_hash FROM users WHERE email = ?',
                    (identifier.lower(),)
                ).fetchone()

            if not user or not verify_password(password, user['password_hash']):
                return jsonify({'error': 'Invalid username/email or password'}), 401

            # Log in the user
            session['user_id'] = user['id']
            session['username'] = user['username']
            print(f"User {user['username']} logged in with ID {user['id']}")

            return jsonify({'message': 'Login successful'}), 200

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500


@app.route('/api/logout', methods=['POST'])
def logout():
    """Log out the current user."""
    print(f"Logout request. Current session: {dict(session)}")
    session.clear()
    print("Session cleared")
    return jsonify({'message': 'Logged out successfully'}), 200

@app.route('/api/jobs', methods=['GET'])
@login_required
def get_jobs():
    """Get all jobs for the current user with optional filtering."""
    conn = get_db_connection()
    conn.row_factory = dict_factory
    
    user_id = session['user_id']
    print(f"Getting jobs for user_id: {user_id}")
    
    # Get filter parameters
    status = request.args.get('status', '')
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')
    
    # Build query - only get jobs for current user
    query = 'SELECT * FROM jobs WHERE user_id = ?'
    params = [user_id]
    
    if status:
        query += ' AND status = ?'
        params.append(status)
    
    # Add sorting
    valid_sort_columns = ['company', 'position', 'status', 'applied_date', 'created_at']
    if sort_by in valid_sort_columns:
        query += f' ORDER BY {sort_by} {sort_order.upper()}'
    
    jobs = conn.execute(query, params).fetchall()
    print(f"Found {len(jobs)} jobs for user {user_id}")
    conn.close()
    
    return jsonify([dict(job) for job in jobs])

@app.route('/api/jobs', methods=['POST'])
@login_required
def create_job():
    """Create a new job application for the current user."""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('company') or not data.get('position'):
        return jsonify({'error': 'Company and position are required'}), 400
    
    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            INSERT INTO jobs (user_id, company, position, status, applied_date, job_url, salary, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session['user_id'],
            data.get('company', ''),
            data.get('position', ''),
            data.get('status', 'applied'),
            data.get('appliedDate') or None,
            data.get('jobUrl', ''),
            data.get('salary', ''),
            data.get('notes', '')
        ))
        
        job_id = cursor.lastrowid
        conn.commit()
        
        # Return the created job
        conn.row_factory = dict_factory
        job = conn.execute('SELECT * FROM jobs WHERE id = ? AND user_id = ?', (job_id, session['user_id'])).fetchone()
        conn.close()
        
        return jsonify(dict(job)), 201
    
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs/<int:job_id>', methods=['PUT'])
@login_required
def update_job(job_id):
    """Update an existing job application for the current user."""
    data = request.get_json()
    
    # Validate required fields
    if not data.get('company') or not data.get('position'):
        return jsonify({'error': 'Company and position are required'}), 400
    
    conn = get_db_connection()
    try:
        # Check if job exists and belongs to current user
        existing = conn.execute('SELECT id FROM jobs WHERE id = ? AND user_id = ?', (job_id, session['user_id'])).fetchone()
        if not existing:
            conn.close()
            return jsonify({'error': 'Job not found'}), 404
        
        # Update the job
        conn.execute('''
            UPDATE jobs 
            SET company = ?, position = ?, status = ?, 
                applied_date = ?, job_url = ?, salary = ?, notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        ''', (
            data.get('company', ''),
            data.get('position', ''),
            data.get('status', 'applied'),
            data.get('appliedDate') or None,
            data.get('jobUrl', ''),
            data.get('salary', ''),
            data.get('notes', ''),
            job_id,
            session['user_id']
        ))
        
        conn.commit()
        
        # Return the updated job
        conn.row_factory = dict_factory
        job = conn.execute('SELECT * FROM jobs WHERE id = ? AND user_id = ?', (job_id, session['user_id'])).fetchone()
        conn.close()
        
        return jsonify(dict(job))
    
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/jobs/<int:job_id>', methods=['DELETE'])
@login_required
def delete_job(job_id):
    """Delete a job application for the current user."""
    conn = get_db_connection()
    try:
        # Check if job exists and belongs to current user
        existing = conn.execute('SELECT id FROM jobs WHERE id = ? AND user_id = ?', (job_id, session['user_id'])).fetchone()
        if not existing:
            conn.close()
            return jsonify({'error': 'Job not found'}), 404
        
        # Delete the job
        conn.execute('DELETE FROM jobs WHERE id = ? AND user_id = ?', (job_id, session['user_id']))
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Job deleted successfully'})
    
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    """Get application statistics for the current user."""
    conn = get_db_connection()
    
    user_id = session['user_id']
    
    # Get total counts for current user
    total = conn.execute('SELECT COUNT(*) as count FROM jobs WHERE user_id = ?', (user_id,)).fetchone()['count']
    
    # Get counts by status for current user
    status_counts = conn.execute('''
        SELECT status, COUNT(*) as count 
        FROM jobs 
        WHERE user_id = ?
        GROUP BY status
    ''', (user_id,)).fetchall()
    
    conn.close()
    
    stats = {
        'total': total,
        'byStatus': {row['status']: row['count'] for row in status_counts}
    }
    
    return jsonify(stats)

@app.route('/api/export/csv', methods=['GET'])
@login_required
def export_csv():
    """Export all jobs for the current user to CSV format."""
    conn = get_db_connection()
    conn.row_factory = dict_factory
    
    jobs = conn.execute('''
        SELECT company, position, status, applied_date, 
               job_url, salary, notes, created_at
        FROM jobs 
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    # Create CSV content
    output = io.StringIO()
    fieldnames = ['company', 'position', 'status', 'applied_date', 'job_url', 'salary', 'notes', 'created_at']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    
    writer.writeheader()
    for job in jobs:
        writer.writerow(dict(job))
    
    # Create file-like object
    output.seek(0)
    filename = f"job_applications_{date.today().isoformat()}.csv"
    
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Initialize database
    init_db()
    

    app.run(debug=True, host='0.0.0.0', port=5000)