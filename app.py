from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import csv
from io import StringIO
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Configure Flask app
app.config['SECRET_KEY'] = 'dev-secret-key-123'  # Temporary hard-coded secret key

# Configure Database
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Handle Heroku/Render style database URLs
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Fallback to SQLite for local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///events.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Hardcoded admin credentials for testing
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    event_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    notes = db.Column(db.Text, nullable=True)

def create_tables():
    with app.app_context():
        db.create_all()

# Create tables
create_tables()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated_function

def check_auth(username, password):
    """Check if username and password are valid."""
    print(f"Login attempt - Username: {username}, Password: {password}")  # Debug log
    is_valid = username == ADMIN_USERNAME and password == ADMIN_PASSWORD
    print(f"Login valid: {is_valid}")  # Debug log
    return is_valid

def authenticate():
    """Sends a 401 response that enables basic auth."""
    return ('Could not verify your access level for that URL.\n'
            'You have to login with proper credentials', 401,
            {'WWW-Authenticate': 'Basic realm="Login Required"'})

@app.route('/')
def index():
    registrations = Registration.query.all()
    return render_template('index.html', registrations=registrations)

@app.route('/register', methods=['POST'])
def register():
    try:
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        event_date = datetime.strptime(request.form['event_date'], '%Y-%m-%d')
        
        registration = Registration(
            name=name,
            email=email,
            phone=phone,
            event_date=event_date
        )
        
        db.session.add(registration)
        db.session.commit()
        flash('Registration successful!', 'success')
    except Exception as e:
        flash('Registration failed. Please try again.', 'error')
        print(f"Error during registration: {str(e)}")  # Add logging
        
    return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin():
    try:
        registrations = Registration.query.order_by(Registration.created_at.desc()).all()
        return render_template('admin.html', registrations=registrations)
    except Exception as e:
        print(f"Error in admin route: {str(e)}")  # Add logging
        return "An error occurred", 500

@app.route('/api/registrations')
@admin_required
def get_registrations():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        status = request.args.get('status')
        
        query = Registration.query
        
        if start_date:
            query = query.filter(Registration.event_date >= datetime.strptime(start_date, '%Y-%m-%d'))
        if end_date:
            query = query.filter(Registration.event_date <= datetime.strptime(end_date, '%Y-%m-%d'))
        if status:
            query = query.filter(Registration.status == status)
            
        registrations = query.order_by(Registration.created_at.desc()).all()
        
        return jsonify([{
            'id': r.id,
            'name': r.name,
            'email': r.email,
            'phone': r.phone,
            'event_date': r.event_date.strftime('%Y-%m-%d'),
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'status': r.status,
            'notes': r.notes
        } for r in registrations])
    except Exception as e:
        print(f"Error in get_registrations: {str(e)}")  # Add logging
        return jsonify({'error': 'An error occurred'}), 500

@app.route('/api/registration/<int:id>', methods=['DELETE'])
@admin_required
def delete_registration(id):
    try:
        registration = Registration.query.get_or_404(id)
        db.session.delete(registration)
        db.session.commit()
        return jsonify({'message': 'Registration deleted successfully'})
    except Exception as e:
        print(f"Error in delete_registration: {str(e)}")  # Add logging
        return jsonify({'error': 'An error occurred'}), 500

@app.route('/api/registration/<int:id>', methods=['PUT'])
@admin_required
def update_registration(id):
    try:
        registration = Registration.query.get_or_404(id)
        data = request.get_json()
        
        if 'name' in data:
            registration.name = data['name']
        if 'email' in data:
            registration.email = data['email']
        if 'phone' in data:
            registration.phone = data['phone']
        if 'event_date' in data:
            registration.event_date = datetime.strptime(data['event_date'], '%Y-%m-%d')
        if 'status' in data:
            registration.status = data['status']
        if 'notes' in data:
            registration.notes = data['notes']
        
        db.session.commit()
        return jsonify({'message': 'Registration updated successfully'})
    except Exception as e:
        print(f"Error in update_registration: {str(e)}")  # Add logging
        return jsonify({'error': 'An error occurred'}), 500

@app.route('/api/registrations/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete():
    try:
        ids = request.get_json().get('ids', [])
        Registration.query.filter(Registration.id.in_(ids)).delete()
        db.session.commit()
        return jsonify({'message': f'{len(ids)} registrations deleted successfully'})
    except Exception as e:
        print(f"Error in bulk_delete: {str(e)}")  # Add logging
        return jsonify({'error': 'An error occurred'}), 500

@app.route('/api/export-csv')
@admin_required
def export_csv():
    try:
        registrations = Registration.query.order_by(Registration.created_at.desc()).all()
        
        si = StringIO()
        cw = csv.writer(si)
        
        # Write headers
        cw.writerow(['ID', 'Name', 'Email', 'Phone', 'Event Date', 'Registration Date', 'Status', 'Notes'])
        
        # Write data
        for r in registrations:
            cw.writerow([
                r.id,
                r.name,
                r.email,
                r.phone,
                r.event_date.strftime('%Y-%m-%d'),
                r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                r.status,
                r.notes
            ])
        
        output = si.getvalue()
        si.close()
        
        return send_file(
            StringIO(output),
            mimetype='text/csv',
            as_attachment=True,
            download_name='registrations.csv'
        )
    except Exception as e:
        print(f"Error in export_csv: {str(e)}")  # Add logging
        return "An error occurred while exporting data", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
