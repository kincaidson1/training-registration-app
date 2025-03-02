from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from datetime import datetime
import os
import csv
import qrcode
import base64
from io import StringIO, BytesIO
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configure Flask app
app.config['SECRET_KEY'] = 'dev-secret-key-123'
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure upload directory exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Configure Database
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///events.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure Mail
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

db = SQLAlchemy(app)
mail = Mail(app)

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    fee = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    registrations = db.relationship('Registration', backref='program', lazy=True)

class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    organization = db.Column(db.String(200), nullable=False)
    designation = db.Column(db.String(100), nullable=False)
    expectations = db.Column(db.Text)
    event_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    payment_reference = db.Column(db.String(100))
    payment_receipt = db.Column(db.String(200))
    notes = db.Column(db.Text)
    ticket_sent = db.Column(db.Boolean, default=False)

def init_db():
    with app.app_context():
        db.create_all()
        
        # Add programs if they don't exist
        if not Program.query.first():
            programs = [
                Program(
                    name='LSE Masterclass',
                    location='London',
                    fee=3550000,
                    description='LONDON LSE MASTERCLASS - 3-day intensive program'
                ),
                Program(
                    name='Lagos Masterclass',
                    location='Lagos',
                    fee=1250000,
                    description='LAGOS MASTERCLASS - 3-day intensive program'
                )
            ]
            for program in programs:
                db.session.add(program)
            db.session.commit()

init_db()

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Hardcoded admin credentials for testing
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

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

def generate_qr_code(registration_id):
    """Generate QR code for a registration."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(f"Registration ID: {registration_id}")
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def send_ticket_email(registration):
    """Send ticket email to participant."""
    try:
        # Generate QR code
        qr_code_data = generate_qr_code(registration.id)
        
        # Render email template
        html = render_template('ticket_email.html',
                             registration=registration,
                             qr_code=f"data:image/png;base64,{qr_code_data}")
        
        # Create email message
        msg = Message(
            'Your Training Event Ticket',
            recipients=[registration.email]
        )
        msg.html = html
        
        # Send email
        mail.send(msg)
        
        # Update ticket sent status
        registration.ticket_sent = True
        db.session.commit()
        
        return True
    except Exception as e:
        print(f"Error sending ticket email: {str(e)}")
        return False

@app.route('/')
def index():
    programs = Program.query.all()
    return render_template('index.html', programs=programs)

@app.route('/program/<int:program_id>')
def program_registration(program_id):
    program = Program.query.get_or_404(program_id)
    return render_template('registration_form.html', program=program)

@app.route('/register', methods=['POST'])
def register():
    try:
        # Get form data
        program_id = request.form['program_id']
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        organization = request.form['organization']
        designation = request.form['designation']
        expectations = request.form['expectations']
        event_date = datetime.strptime(request.form['event_date'], '%Y-%m-%d')
        payment_reference = request.form['payment_reference']
        
        # Handle file upload
        payment_receipt = None
        if 'payment_receipt' in request.files:
            file = request.files['payment_receipt']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{payment_reference}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                payment_receipt = filename
        
        registration = Registration(
            program_id=program_id,
            name=name,
            email=email,
            phone=phone,
            organization=organization,
            designation=designation,
            expectations=expectations,
            event_date=event_date,
            payment_reference=payment_reference,
            payment_receipt=payment_receipt
        )
        
        db.session.add(registration)
        db.session.commit()
        
        # Send ticket email
        if send_ticket_email(registration):
            flash('Registration successful! Check your email for your ticket.', 'success')
        else:
            flash('Registration successful, but there was an error sending the ticket email. Please contact support.', 'warning')
            
    except Exception as e:
        flash('Registration failed. Please try again.', 'error')
        print(f"Error during registration: {str(e)}")
        
    return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin():
    registrations = Registration.query.order_by(Registration.created_at.desc()).all()
    return render_template('admin.html', registrations=registrations)

@app.route('/api/registrations/<int:id>', methods=['GET'])
@admin_required
def get_registration(id):
    try:
        registration = Registration.query.get_or_404(id)
        return jsonify({
            'id': registration.id,
            'program': registration.program.name,
            'name': registration.name,
            'email': registration.email,
            'phone': registration.phone,
            'organization': registration.organization,
            'designation': registration.designation,
            'expectations': registration.expectations,
            'event_date': registration.event_date.strftime('%Y-%m-%d'),
            'created_at': registration.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'status': registration.status,
            'payment_reference': registration.payment_reference,
            'payment_receipt': registration.payment_receipt,
            'notes': registration.notes
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/registrations/<int:id>', methods=['PUT'])
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
        if 'organization' in data:
            registration.organization = data['organization']
        if 'designation' in data:
            registration.designation = data['designation']
        if 'expectations' in data:
            registration.expectations = data['expectations']
        if 'event_date' in data:
            registration.event_date = datetime.strptime(data['event_date'], '%Y-%m-%d')
        if 'status' in data:
            registration.status = data['status']
        if 'payment_reference' in data:
            registration.payment_reference = data['payment_reference']
        if 'payment_receipt' in data:
            registration.payment_receipt = data['payment_receipt']
        if 'notes' in data:
            registration.notes = data['notes']
        
        db.session.commit()
        return jsonify({'message': 'Registration updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/registrations/<int:id>', methods=['DELETE'])
@admin_required
def delete_registration(id):
    try:
        registration = Registration.query.get_or_404(id)
        db.session.delete(registration)
        db.session.commit()
        return '', 204
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/export')
@admin_required
def export_csv():
    try:
        registrations = Registration.query.order_by(Registration.created_at.desc()).all()
        
        si = StringIO()
        cw = csv.writer(si)
        
        # Write headers
        cw.writerow(['ID', 'Program', 'Name', 'Email', 'Phone', 'Organization', 'Designation', 
                    'Expectations', 'Event Date', 'Registration Date', 'Status', 
                    'Payment Reference', 'Payment Receipt', 'Notes'])
        
        # Write data
        for r in registrations:
            cw.writerow([
                r.id,
                r.program.name,
                r.name,
                r.email,
                r.phone,
                r.organization,
                r.designation,
                r.expectations,
                r.event_date.strftime('%Y-%m-%d'),
                r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                r.status,
                r.payment_reference,
                r.payment_receipt,
                r.notes
            ])
        
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=registrations.csv"
        output.headers["Content-type"] = "text/csv"
        return output
    except Exception as e:
        flash('Error exporting data', 'error')
        return redirect(url_for('admin'))

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
            'program': r.program.name,
            'name': r.name,
            'email': r.email,
            'phone': r.phone,
            'organization': r.organization,
            'designation': r.designation,
            'expectations': r.expectations,
            'event_date': r.event_date.strftime('%Y-%m-%d'),
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'status': r.status,
            'payment_reference': r.payment_reference,
            'payment_receipt': r.payment_receipt,
            'notes': r.notes
        } for r in registrations])
    except Exception as e:
        print(f"Error in get_registrations: {str(e)}")  # Add logging
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
