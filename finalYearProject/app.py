from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import re
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = "supersecretkey"

# -------------------------
# EMAIL CONFIGURATION
# -------------------------
EMAIL_ADDRESS = "xyzl@gmail.com"
EMAIL_PASSWORD = "tyaoxqytreyuuii"

# -------------------------
# DATABASE CONFIG
# -------------------------
import os

basedir = os.path.abspath(os.path.dirname(__file__))

# ensure instance folder exists
instance_path = os.path.join(basedir, 'instance')
os.makedirs(instance_path, exist_ok=True)

# put DB inside instance
db_path = os.path.join(instance_path, 'hostel_leave.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hostel_leave.db'
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

from models import *

# # Create tables if missing
# with app.app_context():
#     db.create_all()

# -------------------------
# MODELS
# -------------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(10), unique=True, nullable=False)
    aadhaar = db.Column(db.String(12), unique=True)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default="Pending")


class Leave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    from_date = db.Column(db.Date)
    to_date = db.Column(db.Date)
    reason = db.Column(db.String(300))
    applied_on = db.Column(db.DateTime, default=datetime.utcnow)
    caretaker_status = db.Column(db.String(20), default="Pending")
    verified_by = db.Column(db.Integer)
    warden_status = db.Column(db.String(20), default="Pending")


# -------------------------
# VALIDATION
# -------------------------

def valid_password(password):
    return re.fullmatch(r'(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}', password)


reset_tokens = {}

# -------------------------
# HOME
# -------------------------

@app.route('/')
def home():
    return render_template("index.html")


# -------------------------
# REGISTER
# -------------------------
@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":

        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        aadhaar = request.form.get('aadhaar')
        password = request.form['password']
        role = request.form['role']

        # ---------------- VALIDATIONS ----------------

        # Email check
        if User.query.filter_by(email=email).first():
            return "Email already registered!"

        # Phone check
        if User.query.filter_by(phone=phone).first():
            return "Phone number already registered!"

        if role in ["Caretaker", "Warden"]:

            # Aadhaar validation
            if not aadhaar or not re.fullmatch(r'\d{12}', aadhaar):
                return "Aadhaar must be exactly 12 digits!"

            if User.query.filter_by(aadhaar=aadhaar).first():
                return "Aadhaar already exists!"

            status = "Pending"   # needs admin approval

        else:
            aadhaar = None
            status = "Approved"  # students can login directly

        user = User(
            name=name,
            email=email,
            phone=phone,
            aadhaar=aadhaar,
            password=password,
            role=role,
            status=status,
        )

        db.session.add(user)
        db.session.commit()

        if role in ["Caretaker", "Warden"]:
            return "Registration successful! Wait for Admin approval."
        else:
            return redirect(url_for('home'))

    return render_template("auth/register.html")

# -------------------------
# LOGIN
# -------------------------
@app.route('/login', methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        user = User.query.filter_by(email=email).first()

        # Check credentials first
        if user and user.password == password and user.role.lower() == role.lower():

            # ---------------- STATUS CHECK ----------------

            if user.status == "Pending":
                return "Account not approved by Admin yet."

            if user.status == "Rejected":
                return "Authentication denied by Admin."

            # ---------------- LOGIN SUCCESS ----------------

            session['user_id'] = user.id
            session['role'] = role

            if role == "Student":
                return redirect(url_for('student_dashboard'))
            elif role == "Caretaker":
                return redirect(url_for('caretaker_dashboard'))
            elif role == "Warden":
                return redirect(url_for('warden_dashboard'))
            elif role == "Admin":
                return redirect(url_for('admin_dashboard'))

        return "Invalid Credentials"

    return render_template("index.html")

# -------------------------
# STUDENT DASHBOARD
# -------------------------

@app.route('/student-dashboard')
def student_dashboard():

    if 'user_id' not in session or session.get('role') != "Student":
        return redirect(url_for('home'))

    leaves = Leave.query.filter_by(student_id=session.get('user_id')).all()

    leave_data = []
    for index, leave in enumerate(leaves, start=1):
        leave_data.append({
            "sr_no": index,
            "id": leave.id,
            "from_date": leave.from_date.strftime("%d-%m-%Y"),
            "to_date": leave.to_date.strftime("%d-%m-%Y"),
            "reason": leave.reason,
            "applied_on": leave.applied_on.strftime("%d-%m-%Y"),
            "status": leave.warden_status
        })

    return render_template("student/dashboard.html", leaves=leave_data)


@app.route('/apply-leave', methods=["GET", "POST"])
def apply_leave():
    if request.method == "POST":
        leave = Leave(
            student_id=session.get('user_id'),
            from_date=datetime.strptime(request.form['from_date'], "%Y-%m-%d"),
            to_date=datetime.strptime(request.form['to_date'], "%Y-%m-%d"),
            reason=request.form['reason']
        )
        db.session.add(leave)
        db.session.commit()
        return redirect(url_for('student_dashboard'))

    return render_template("student/apply_leave.html")


# -------------------------
# CARETAKER DASHBOARD
# -------------------------

@app.route('/caretaker-dashboard')
def caretaker_dashboard():
    if 'user_id' not in session or session.get('role') != "Caretaker":
        return redirect(url_for('home'))

    user_id = session.get('user_id')

    # ---------------- PENDING LEAVES ----------------
    pending_leaves = Leave.query.filter_by(caretaker_status="Pending").all()

    # ---------------- RECORD LEAVES ----------------
    # Leaves this caretaker acted on OR leaves which are finalized by warden
    records_leaves = Leave.query.filter(
        (Leave.verified_by == user_id) | 
        (Leave.warden_status.in_(["Approved", "Rejected", "Rejected by Caretaker"]))
    ).all()

    # ---------------- FORMAT DATA ----------------
    def format_leaves(leaves):
        data = []
        for index, leave in enumerate(leaves, start=1):
            student = User.query.get(leave.student_id)
            caretaker = User.query.get(leave.verified_by) if leave.verified_by else None
            data.append({
                "sr_no": index,
                "id": leave.id,
                "student_name": student.name if student else "Unknown",
                "from_date": leave.from_date.strftime("%d-%m-%Y"),
                "to_date": leave.to_date.strftime("%d-%m-%Y"),
                "applied_on": leave.applied_on.strftime("%d-%m-%Y"),
                "reason": leave.reason,
                "caretaker_status": leave.caretaker_status,
                "warden_status": leave.warden_status,
                "verified_by": caretaker.name if caretaker else "Not Verified"
            })
        return data

    pending_data = format_leaves(pending_leaves)
    records_data = format_leaves(records_leaves)

    # ---------------- RENDER DASHBOARD ----------------
    return render_template(
        "caretaker/dashboard.html",
        pending_leaves=pending_data,
        leave_records=records_data
    )
    # verification and rejection route
@app.route('/caretaker-verify/<int:leave_id>')
def caretaker_verify(leave_id):

    leave = Leave.query.get_or_404(leave_id)
    # ✅ KEEP ONLY THESE
    leave.caretaker_status = "Verified"
    leave.verified_by = session.get('user_id')
    leave.warden_status = "Forwarded to Warden"

    db.session.commit()

    return redirect(url_for('caretaker_dashboard'))


@app.route('/caretaker-reject/<int:leave_id>')
def caretaker_reject(leave_id):

    leave = Leave.query.get_or_404(leave_id)
    leave.caretaker_status = "Rejected"
    leave.verified_by = session.get('user_id')   # 👈 ADD THIS LINE
    leave.warden_status = "Rejected by Caretaker"

    db.session.commit()

    return redirect(url_for('caretaker_dashboard'))

# -------------------------
# WARDEN DASHBOARD
# -------------------------
@app.route('/warden-dashboard')
def warden_dashboard():

    if 'user_id' not in session or session.get('role') != "Warden":
        return redirect(url_for('home'))

    search_query = request.args.get('search', '').strip()

    # ---------------- FETCH DATA ----------------
    if search_query:
        pending_leaves = Leave.query.join(User, Leave.student_id == User.id).filter(
            Leave.caretaker_status == "Verified",
            Leave.warden_status == "Forwarded to Warden",
            User.name.ilike(f"%{search_query}%")
        ).all()

        leave_records = Leave.query.join(User, Leave.student_id == User.id).filter(
            Leave.warden_status.in_(["Approved", "Rejected", "Rejected by Caretaker"]),
            User.name.ilike(f"%{search_query}%")
        ).all()
    else:
        pending_leaves = Leave.query.filter(
            Leave.caretaker_status == "Verified",
            Leave.warden_status == "Forwarded to Warden"
        ).all()

        leave_records = Leave.query.filter(
            Leave.warden_status.in_(["Approved", "Rejected", "Rejected by Caretaker"])
        ).all()

    # ---------------- FORMAT DATA ----------------
    def format_leaves(leaves):
        data = []
        for index, leave in enumerate(leaves, start=1):
            student = User.query.get(leave.student_id)
            caretaker = User.query.get(leave.verified_by) if leave.verified_by else None

            data.append({
                "sr_no": index,
                "id": leave.id,
                "student_name": student.name if student else "Unknown",
                "from_date": leave.from_date.strftime("%d-%m-%Y"),
                "to_date": leave.to_date.strftime("%d-%m-%Y"),
                "applied_on": leave.applied_on.strftime("%d-%m-%Y"),
                "reason": leave.reason,
                "warden_status": leave.warden_status,
                "verified_by": caretaker.name if caretaker else "Not Verified"
            })
        return data

    pending_data = format_leaves(pending_leaves)
    records_data = format_leaves(leave_records)

    # ---------------- RENDER ----------------
    return render_template(
        "warden/dashboard.html",
        pending_leaves=pending_data,
        leave_records=records_data,
        search_query=search_query
    )
# -------------------------
# WARDEN DASHBOARD
@app.route('/warden-approve/<int:leave_id>')
def warden_approve(leave_id):
    leave = Leave.query.get(leave_id)
    leave.warden_status = "Approved"
    db.session.commit()
    return redirect(url_for('warden_dashboard'))


@app.route('/warden-reject/<int:leave_id>')
def warden_reject(leave_id):
    leave = Leave.query.get(leave_id)
    leave.warden_status = "Rejected"
    db.session.commit()
    return redirect(url_for('warden_dashboard'))


# -------------------------
# ADMIN DASHBOARD
# -------------------------

@app.route('/admin-dashboard')
def admin_dashboard():

    total_students = User.query.filter_by(role="Student").count()
    total_leaves = Leave.query.count()
    pending = Leave.query.filter_by(warden_status="Pending").count()
    approved = Leave.query.filter_by(warden_status="Approved").count()
    rejected = Leave.query.filter_by(warden_status="Rejected").count()

    pending_users = User.query.filter(
        User.role.in_(["Caretaker", "Warden"]),
        User.status == "Pending"
    ).all()

    return render_template(
        "admin/dashboard.html",
        pending_users=pending_users,
        total_students=total_students,
        total_leaves=total_leaves,
        pending_leaves=pending,
        approved_leaves=approved,
        rejected_leaves=rejected
    )


@app.route('/approve-user/<int:user_id>')
def approve_user(user_id):

    if session.get('role') != "Admin":
        return redirect(url_for('home'))

    user = User.query.get(user_id)
    if user:
        user.status = "Approved"
        db.session.commit()

    return redirect(url_for('admin_dashboard'))
@app.route('/reject-user/<int:user_id>')
def reject_user(user_id):

    if session.get('role') != "Admin":
        return redirect(url_for('home'))

    user = User.query.get(user_id)
    if user:
        user.status = "Rejected"
        db.session.commit()

    return redirect(url_for('admin_dashboard'))


# -------------------------
# FORGOT PASSWORD
# -------------------------

@app.route('/forgot-password', methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form['email']
        user = User.query.filter_by(email=email).first()

        if user:
            token = secrets.token_hex(16)
            reset_tokens[token] = user.id
            reset_link = url_for('reset_password', token=token, _external=True)

            msg = MIMEMultipart()
            msg['From'] = EMAIL_ADDRESS
            msg['To'] = email
            msg['Subject'] = "Password Reset"

            body = f"Click link to reset password:\n{reset_link}"
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()

            return "Reset link sent!"

        return "Email not found!"

    return render_template("auth/forgot_password.html")


@app.route('/reset-password/<token>', methods=["GET", "POST"])
def reset_password(token):
    if token not in reset_tokens:
        return "Invalid Token"

    if request.method == "POST":
        new_password = request.form['password']
        if not valid_password(new_password):
            return "Password not strong"

        user = User.query.get(reset_tokens[token])
        user.password = new_password
        db.session.commit()
        del reset_tokens[token]
        return redirect(url_for('home'))

    return render_template("auth/reset_password.html")


# -------------------------
# LOGOUT
# -------------------------

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


# -------------------------
# INITIAL SETUP
# -------------------------

with app.app_context():
    db.create_all()

    admin = User.query.filter_by(role="Admin").first()
    if not admin:
        admin_user = User(
            name="Admin",
            email="sheadmin@gmail.com",
            phone="9998887776",
            password="Sheher@123",
            role="Admin",
            status="Approved"   # ✅ correct
        )
        db.session.add(admin_user)
        db.session.commit()
# RUN
# -------------------------

if __name__ == "__main__":
    app.run(debug=True)