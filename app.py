from flask import (
    Flask, 
    render_template, 
    request, 
    redirect, 
    url_for, 
    flash, 
    jsonify, 
    send_file, 
    make_response, 
    session
)
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from datetime import datetime
import os
import qrcode
from io import BytesIO, StringIO
import csv
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import secrets
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure app with environment variables or defaults
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Database configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Handle Heroku/Render PostgreSQL URL
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///registrations.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Email configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(100))
    fee = db.Column(db.Float)
    registrations = db.relationship('Registration', backref='program', lazy=True)

class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    organization = db.Column(db.String(200))
    designation = db.Column(db.String(100))
    expectations = db.Column(db.Text)
    event_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    payment_reference = db.Column(db.String(100))
    payment_receipt = db.Column(db.String(200))
    notes = db.Column(db.Text)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

def init_db():
    """Initialize the database and create default data."""
    try:
        with app.app_context():
            # Create all tables
            db.create_all()
            
            # Create default programs if they don't exist
            if not Program.query.first():
                programs = [
                    Program(
                        name='London Masterclass',
                        description='Advanced training program in London',
                        location='London',
                        fee=1500.00
                    ),
                    Program(
                        name='Lagos Masterclass',
                        description='Advanced training program in Lagos',
                        location='Lagos',
                        fee=1000.00
                    )
                ]
                db.session.add_all(programs)
            
            # Create default admin if it doesn't exist
            admin = Admin.query.filter_by(username='admin').first()
            if not admin:
                admin = Admin(username='admin')
                admin.set_password('admin123')
                db.session.add(admin)
            else:
                # Update existing admin password
                admin.set_password('admin123')
            
            try:
                db.session.commit()
                print("Database initialized successfully!")
            except Exception as e:
                print(f"Error during database commit: {str(e)}")
                db.session.rollback()
                
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        db.session.rollback()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Please log in first.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def welcome():
    try:
        return render_template('welcome.html')
    except Exception as e:
        print(f"Error in welcome route: {str(e)}")
        return "An error occurred", 500

@app.route('/register')
def register():
    try:
        programs = Program.query.all()
        return render_template('index.html', programs=programs)
    except Exception as e:
        print(f"Error in register route: {str(e)}")
        flash('Error loading programs. Please try again later.', 'error')
        return redirect(url_for('welcome'))

@app.route('/register/<int:program_id>', methods=['GET', 'POST'])
def program_registration(program_id):
    try:
        program = Program.query.get_or_404(program_id)
        if request.method == 'POST':
            # Handle form submission
            registration = Registration(
                program_id=program_id,
                name=request.form['name'],
                email=request.form['email'],
                phone=request.form['phone'],
                organization=request.form['organization'],
                designation=request.form['designation'],
                expectations=request.form['expectations'],
                event_date=datetime.strptime(request.form['event_date'], '%Y-%m-%d')
            )
            db.session.add(registration)
            db.session.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('welcome'))
        return render_template('registration_form.html', program=program)
    except Exception as e:
        print(f"Error in program_registration route: {str(e)}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('register'))

@app.route('/submit_registration', methods=['POST'])
def submit_registration():
    try:
        program_id = request.form.get('program_id')
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        organization = request.form.get('organization')
        designation = request.form.get('designation')
        expectations = request.form.get('expectations')
        event_date = datetime.strptime(request.form.get('event_date'), '%Y-%m-%d')
        payment_reference = request.form.get('payment_reference')
        
        # Handle file upload
        payment_receipt = None
        if 'payment_receipt' in request.files:
            file = request.files['payment_receipt']
            if file and file.filename:
                filename = secure_filename(file.filename)
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

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(f"Registration ID: {registration.id}\nName: {name}\nEmail: {email}")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Save QR code
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        
        # Send confirmation email with QR code
        msg = Message(
            'Registration Confirmation',
            recipients=[email]
        )
        msg.html = render_template(
            'ticket_email.html',
            name=name,
            registration_id=registration.id,
            event_date=event_date
        )
        msg.attach(
            'registration_qr.png',
            'image/png',
            qr_buffer.getvalue()
        )
        mail.send(msg)

        flash('Registration successful! Check your email for the confirmation.', 'success')
    except Exception as e:
        flash('Registration failed. Please try again.', 'error')
        print(f"Error during registration: {str(e)}")
        
    return redirect(url_for('welcome'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    try:
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            admin = Admin.query.filter_by(username=username).first()
            
            if admin and admin.check_password(password):
                session['admin_logged_in'] = True
                flash('Successfully logged in!', 'success')
                return redirect(url_for('admin'))
            else:
                print(f"Login failed - Username: {username}, Admin exists: {admin is not None}")
                flash('Invalid username or password', 'error')
        
        return render_template('admin_login.html')
    except Exception as e:
        print(f"Error in admin_login route: {str(e)}")
        flash('An error occurred during login. Please try again.', 'error')
        return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Successfully logged out!', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin():
    try:
        registrations = Registration.query.order_by(Registration.created_at.desc()).all()
        return render_template('admin.html', registrations=registrations)
    except Exception as e:
        print(f"Error in admin route: {str(e)}")
        flash('Error loading registrations. Please try again.', 'error')
        return redirect(url_for('admin_login'))

@app.route('/api/registrations/<int:id>', methods=['GET'])
@admin_required
def get_registration(id):
    try:
        registration = Registration.query.get_or_404(id)
        return jsonify({
            'id': registration.id,
            'program_id': registration.program_id,
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

# Initialize the database when the app starts
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
