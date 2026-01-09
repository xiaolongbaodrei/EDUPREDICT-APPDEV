from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sqlite3
from datetime import datetime
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.exc import OperationalError
from sqlalchemy import or_
from functools import wraps
import math
import time

# Extras for CSV import
import csv
import io
import json
import uuid

app = Flask(__name__)
app.secret_key = "edupredict_secret_key"

# =========================
# DATABASE CONFIG
# =========================
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'database.db')
# Use absolute path to ensure the DB lives next to the app script
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path.replace('\\', '/')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Increase SQLite busy timeout to reduce 'database is locked' errors on Windows/OneDrive
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = { 'connect_args': { 'timeout': 30 } }
# How long confirmation tokens are valid (seconds)
app.config['CONFIRM_TOKEN_TTL'] = 600  # 10 minutes

# Ensure instance confirm dir exists
os.makedirs(os.path.join(app.instance_path, 'confirm'), exist_ok=True)

db = SQLAlchemy(app)

# =========================
# LOAD AI MODEL (lazy-loaded)
# =========================
# Model may require compiled libraries which can crash the server at import time.
# Lazy-load it inside the predict route to avoid startup crashes.
model = None

# Serializer for password reset tokens
serializer = URLSafeTimedSerializer(app.secret_key)

# =========================
# DATABASE MODELS
# =========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # Admin / Teacher


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    attendance = db.Column(db.Float)
    # legacy 'grade' has been replaced conceptually by 'final_grade'
    grade = db.Column(db.Float)  # kept for backward compatibility

    # New assessment components
    activities = db.Column(db.Float)
    quizzes = db.Column(db.Float)
    notes = db.Column(db.Text)
    written_works = db.Column(db.Float)
    performance_task = db.Column(db.Float)
    exam = db.Column(db.Float)

    final_grade = db.Column(db.Float)

    risk = db.Column(db.String(50))
    added_by = db.Column(db.String(100))
    section = db.Column(db.String(100))
    subject = db.Column(db.String(50))


class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(20))  # create, update, delete
    user = db.Column(db.String(100))
    student_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)

    def __repr__(self):
        return f"<Audit {self.action} by {self.user} on {self.timestamp}>" 

def add_role_column_if_missing():
    """Add the 'role' column to the 'user' table if it doesn't exist."""
    db_path = os.path.join(os.getcwd(), 'database.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info('user')")
            cols = [row[1] for row in cur.fetchall()]
            if 'role' not in cols:
                app.logger.info("Adding 'role' column to 'user' table (runtime fallback).")
                cur.execute("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'Teacher'")
                conn.commit()
                # Refresh SQLAlchemy engine/session to pick up schema changes
                try:
                    db.session.remove()
                    db.engine.dispose()
                except Exception:
                    pass
        except Exception as e:
            app.logger.exception('Runtime migration failed during role runtime migration')
        finally:
            conn.close()

# -----------------
# PASSWORD RESET
# -----------------

def generate_reset_token(username):
    return serializer.dumps({'username': username})


def verify_reset_token(token, max_age=3600):
    try:
        data = serializer.loads(token, max_age=max_age)
        return data.get('username')
    except SignatureExpired:
        return None
    except BadSignature:
        return None


def ensure_student_columns():
    pass


# Helper: commit with retry on SQLite 'database is locked' errors
def commit_with_retry(max_retries=6, initial_delay=0.05):
    """Commit the current session with retries on 'database is locked'.
    Raises OperationalError if still failing after retries.
    """
    for i in range(max_retries):
        try:
            db.session.commit()
            return
        except OperationalError as e:
            # SQLite 'database is locked' message
            if 'database is locked' in str(e).lower():
                sleep_time = initial_delay * (i + 1)
                app.logger.warning('Database locked, retrying commit after %.3fs (attempt %d/%d)', sleep_time, i+1, max_retries)
                time.sleep(sleep_time)
                continue
            # For other SQLAlchemy OperationalErrors, re-raise
            db.session.rollback()
            raise
    db.session.rollback()
    raise OperationalError('Database locked after retries')

def ensure_student_columns():
    """Ensure assessment-related columns exist on the student table."""
    db_path = os.path.join(os.getcwd(), 'database.db')
    cols_to_add = {
        'activities': "REAL DEFAULT 0",
        'quizzes': "REAL DEFAULT 0",
        'notes': "TEXT DEFAULT ''",
        'written_works': "REAL DEFAULT 0",
        'performance_task': "REAL DEFAULT 0",
        'exam': "REAL DEFAULT 0",
        'final_grade': "REAL DEFAULT 0",
        'section': "TEXT DEFAULT ''",
        'subject': "TEXT DEFAULT ''"
    }
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info('student')")
            existing = [row[1] for row in cur.fetchall()]
            for col, sql_type in cols_to_add.items():
                if col not in existing:
                    app.logger.info(f"Adding '{col}' column to 'student' table.")
                    cur.execute(f"ALTER TABLE student ADD COLUMN {col} {sql_type}")
                    conn.commit()
            # Refresh SQLAlchemy engine/session to pick up schema changes
            try:
                db.session.remove()
                db.engine.dispose()
            except Exception:
                pass
        except Exception as e:
            app.logger.exception('Student table migration failed during ensure_student_columns')
        finally:
            conn.close()


# ----- Confirmation session helpers (PRG flow) -----
def cleanup_confirm_sessions(ttl_seconds=None):
    """Remove confirm session files older than TTL (in seconds)."""
    tmpdir = os.path.join(app.instance_path, 'confirm')
    if not os.path.exists(tmpdir):
        return
    try:
        ttl = ttl_seconds if ttl_seconds is not None else app.config.get('CONFIRM_TOKEN_TTL', 600)
        now = time.time()
        for fname in os.listdir(tmpdir):
            if not fname.endswith('.json'):
                continue
            path = os.path.join(tmpdir, fname)
            try:
                mtime = os.path.getmtime(path)
                if now - mtime > ttl:
                    os.remove(path)
                    app.logger.info('Removed expired confirm token %s', fname)
            except Exception:
                # Ignore problems removing individual files
                app.logger.debug('Failed to remove confirm file %s', path)
    except Exception:
        pass


def create_confirm_session(payload):
    """Store a confirmation payload in instance/confirm and return token."""
    tmpdir = os.path.join(app.instance_path, 'confirm')
    os.makedirs(tmpdir, exist_ok=True)
    # Cleanup expired tokens opportunistically
    try:
        cleanup_confirm_sessions()
    except Exception:
        pass
    token = uuid.uuid4().hex
    path = os.path.join(tmpdir, token + '.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh)
    return token

@app.route('/confirm/<token>')
def confirm_view(token):
    tmpdir = os.path.join(app.instance_path, 'confirm')
    path = os.path.join(tmpdir, token + '.json')
    # Cleanup expired tokens opportunistically
    try:
        cleanup_confirm_sessions()
    except Exception:
        pass

    if not os.path.exists(path):
        flash('Confirmation expired or invalid.')
        return redirect(url_for('dashboard'))
    with open(path, 'r', encoding='utf-8') as fh:
        payload = json.load(fh)
    # Render the overlay-style confirm page
    return render_template('confirm_action.html', **payload)


# -------------------------
# AUTHZ HELPERS
# -------------------------

def admin_required(f):
    """Decorator to ensure the current user is an Admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in as an admin to access that page.')
            return redirect(url_for('login'))
        if session.get('role') != 'Admin':
            flash('Admin access required.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# =========================
# AUTH ROUTES
# =========================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            user = User.query.filter_by(username=username).first()
        except OperationalError as e:
            # Try to fix schema, then retry
            app.logger.warning('OperationalError querying user table, attempting migration: %s', e)
            add_role_column_if_missing()
            user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user'] = user.username
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']

        # prevent duplicate usernames
        try:
            exists = User.query.filter_by(username=username).first()
        except OperationalError as e:
            app.logger.warning('OperationalError querying user table, attempting migration: %s', e)
            add_role_column_if_missing()
            exists = User.query.filter_by(username=username).first()

        if exists:
            flash('Username already exists')
            return render_template('register.html')

        user = User(username=username, password=password, role=role)
        db.session.add(user)
        try:
            commit_with_retry()
            flash('Registration successful. Please log in.')
            return redirect(url_for('login'))
        except OperationalError:
            flash('Registration failed due to database being busy. Please try again.')
            return render_template('register.html')

    return render_template('register.html')


@app.route('/logout', methods=['GET','POST'])
def logout():
    # Support both GET (tests/quick) and POST (confirmed actions from UI)
    if request.method == 'POST':
        # Server-side confirmation fallback (switch to PRG: create session and redirect to confirm view)
        if request.form.get('_requires_confirm') and not request.form.get('_confirmed'):
            hidden_items = {'_requires_confirm': '1'}
            token = create_confirm_session({
                'message': f"Logout {session.get('user')}?",
                'action': url_for('logout'),
                'hidden_items': hidden_items,
                'cancel_url': url_for('dashboard')
            })
            return redirect(url_for('confirm_view', token=token), 303)

        session.clear()
        flash('You have been logged out.')
        return redirect(url_for('login'))
    # Allow GET for programmatic logout (tests)
    session.clear()
    return redirect(url_for('login'))


@app.route('/forgot', methods=['GET', 'POST'])
def forgot_password():
    reset_link = None
    if request.method == 'POST':
        username = request.form.get('username')
        user = User.query.filter_by(username=username).first()
        # Do not reveal whether username exists; show link only for testing/development
        if user:
            token = generate_reset_token(user.username)
            reset_link = url_for('reset_password', token=token, _external=True)
            flash('Reset link generated (for testing).')
        else:
            flash('If that username exists, a reset link was sent.')
    return render_template('forgot_password.html', reset_link=reset_link)


@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    username = verify_reset_token(token)
    if not username:
        flash('Invalid or expired token.')
        return redirect(url_for('forgot_password'))
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('Invalid token user.')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        pw = request.form.get('password')
        pw2 = request.form.get('confirm')
        if pw != pw2:
            flash('Passwords do not match.')
            return render_template('reset_password.html')
        user.password = generate_password_hash(pw)
        try:
            commit_with_retry()
            flash('Password updated. Please log in.')
            return redirect(url_for('login'))
        except OperationalError:
            flash('Could not update password right now (database busy). Please try again.')
            return render_template('reset_password.html')

    return render_template('reset_password.html')


# -------------------------
# ADMIN ROUTES
# -------------------------
@app.route('/admin/users')
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if user:
        if user.username == session.get('user'):
            flash("You cannot delete your own account while signed in.")
            return redirect(url_for('manage_users'))

        # Server-side confirmation fallback (PRG)
        if request.method == 'POST' and request.form.get('_requires_confirm') and not request.form.get('_confirmed'):
            hidden_items = {'_requires_confirm': '1'}
            token = create_confirm_session({
                'message': f"Delete user {user.username}? This cannot be undone.",
                'action': url_for('delete_user', user_id=user_id),
                'hidden_items': hidden_items,
                'cancel_url': url_for('manage_users'),
                'items': [user.username]
            })
            return redirect(url_for('confirm_view', token=token), 303)

        db.session.delete(user)
        try:
            commit_with_retry()
            flash('User deleted')
        except OperationalError:
            flash('Could not delete user right now (database busy). Please try again.')
    return redirect(url_for('manage_users'))

@app.route('/admin/users/role/<int:user_id>', methods=['POST'])
@admin_required
def change_role(user_id):
    new_role = request.form.get('role')
    user = User.query.get(user_id)
    if user and new_role in ('Admin', 'Teacher'):
        # Server-side confirmation fallback (PRG)
        if request.form.get('_requires_confirm') and not request.form.get('_confirmed'):
            hidden_items = {'_requires_confirm': '1', 'role': new_role}
            token = create_confirm_session({
                'message': f"Change role for {user.username} to {new_role}?",
                'action': url_for('change_role', user_id=user_id),
                'hidden_items': hidden_items,
                'cancel_url': url_for('manage_users'),
                'items': [f"{user.username} → {new_role}"]
            })
            return redirect(url_for('confirm_view', token=token), 303)

        user.role = new_role
        try:
            commit_with_retry()
            flash('Role updated')
        except OperationalError:
            flash('Could not update role right now (database busy). Please try again.')
    return redirect(url_for('manage_users'))

@app.route('/admin/students')
def manage_students():
    if 'user' not in session:
        return redirect(url_for('login'))
    if session.get('role') not in ('Admin', 'Teacher'):
        flash('Admin or Teacher access required.')
        return redirect(url_for('dashboard'))

    # Query params
    q = (request.args.get('q') or '').strip()
    selected_section = request.args.get('section', 'All')
    selected_subject = request.args.get('subject', 'All')
    selected_risk = request.args.get('risk', 'All')
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    per_page = 10

    # Build list of available risk values for UI
    risk_list = ['High Risk', 'Low Risk']

    # Base query depends on role
    if session.get('role') == 'Admin':
        base_q = Student.query
    else:
        base_q = Student.query.filter_by(added_by=session.get('user'))

    # Apply search by name
    if q:
        base_q = base_q.filter(Student.name.ilike(f"%{q}%"))

    # Apply section filter
    if selected_section and selected_section != 'All':
        if selected_section == 'Unassigned':
            base_q = base_q.filter(or_(Student.section == '', Student.section == None))
        else:
            base_q = base_q.filter(Student.section == selected_section)

    # Apply subject filter
    if selected_subject and selected_subject != 'All':
        if selected_subject == 'Unassigned':
            base_q = base_q.filter(or_(Student.subject == '', Student.subject == None))
        else:
            base_q = base_q.filter(Student.subject == selected_subject)

    # Apply risk filter
    if selected_risk and selected_risk != 'All':
        base_q = base_q.filter(Student.risk == selected_risk)

    total = base_q.count()
    total_pages = max(1, math.ceil(total / per_page))

    students = base_q.order_by(Student.id).offset((page - 1) * per_page).limit(per_page).all()

    # Build list of available sections and subjects for filters (based on current role visibility)
    if session.get('role') == 'Admin':
        raw_sections = db.session.query(Student.section).distinct().all()
        raw_subjects = db.session.query(Student.subject).distinct().all()
    else:
        raw_sections = db.session.query(Student.section).filter(Student.added_by == session.get('user')).distinct().all()
        raw_subjects = db.session.query(Student.subject).filter(Student.added_by == session.get('user')).distinct().all()
    sections_list = []
    for (sec,) in raw_sections:
        if not sec or sec == '':
            sections_list.append('Unassigned')
        else:
            sections_list.append(sec)
    sections_list = sorted(list(set(sections_list)))

    subjects_list = []
    for (subj,) in raw_subjects:
        if not subj or subj == '':
            subjects_list.append('Unassigned')
        else:
            subjects_list.append(subj)
    subjects_list = sorted(list(set(subjects_list)))

    # Remember last area (identifier only) so Back returns to the previous dashboard area
    session['last_area'] = 'manage_students'

    return render_template(
        'admin_students.html',
        students=students,
        q=q,
        selected_section=selected_section,
        selected_subject=selected_subject,
        selected_risk=selected_risk,
        sections_list=sections_list,
        subjects_list=subjects_list,
        risk_list=risk_list,
        page=page,
        total_pages=total_pages,
        total=total,
        per_page=per_page
    )


@app.route('/admin/students/edit/<int:student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    if session.get('role') not in ('Admin', 'Teacher'):
        flash('Admin or Teacher access required.')
        return redirect(url_for('dashboard'))

    student = Student.query.get_or_404(student_id)

    # Only the user who added the student may edit it
    if student.added_by != session.get('user'):
        flash('You can only edit students you added.')
        return redirect(url_for('manage_students'))

    if request.method == 'POST':
        # Save previous for audit
        prev = { 'attendance': student.attendance, 'activities': student.activities, 'quizzes': student.quizzes, 'performance_task': student.performance_task, 'exam': student.exam }

        student.name = request.form.get('name')
        student.attendance = float(request.form.get('attendance') or 0)
        student.activities = float(request.form.get('activities') or 0)
        student.quizzes = float(request.form.get('quizzes') or 0)
        student.notes = request.form.get('notes') or ''
        student.section = request.form.get('section') or ''
        student.subject = request.form.get('subject') or ''
        student.written_works = (student.activities + student.quizzes) / 2 if (student.activities or student.quizzes) else 0
        student.performance_task = float(request.form.get('performance_task') or 0)
        student.exam = float(request.form.get('exam') or 0)
        student.final_grade = round(student.written_works * 0.20 + student.performance_task * 0.50 + student.exam * 0.30, 2)

        # Determine risk based on final_grade threshold: >=76 -> Low Risk
        try:
            student.risk = 'Low Risk' if student.final_grade >= 76 else 'High Risk'
        except Exception:
            # Keep previous value on failure
            student.risk = student.risk

        try:
            commit_with_retry()
        except OperationalError:
            flash('Update failed due to database being busy. Please try again.')
            return redirect(url_for('manage_students'))
        try:
            audit = Audit(action='update', user=session.get('user'), student_id=student.id, details=f'Updated fields from {prev} to {{"attendance":{student.attendance}, "activities":{student.activities}, "quizzes":{student.quizzes}, "performance_task":{student.performance_task}, "exam":{student.exam}}}')
            db.session.add(audit)
            try:
                commit_with_retry()
            except OperationalError:
                pass
        except Exception:
            pass

        flash('Student updated')
        return redirect(url_for('manage_students'))

    return render_template('edit_student.html', student=student)


@app.route('/admin/audit')
@admin_required
def view_audit():
    records = Audit.query.order_by(Audit.timestamp.desc()).limit(100).all()
    return render_template('admin_audit.html', records=records)

@app.route('/admin/students/delete/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    # Allow both Admin and Teacher roles to remove students
    if 'user' not in session:
        return redirect(url_for('login'))
    if session.get('role') not in ('Admin', 'Teacher'):
        flash('Admin or Teacher access required.')
        return redirect(url_for('dashboard'))

    s = Student.query.get(student_id)
    if s:
        # Only the user who added the student may delete it
        if not (session.get('role') == 'Admin' or s.added_by == session.get('user')):
            flash('You can only delete students you added.')
            return redirect(url_for('manage_students'))

        # Server-side confirmation fallback when JavaScript modal is not available (PRG)
        if request.method == 'POST' and request.form.get('_requires_confirm') and not request.form.get('_confirmed'):
            hidden_items = {'_requires_confirm': '1'}
            items = [s.name]
            token = create_confirm_session({
                'message': f"Delete student {s.name}? This cannot be undone.",
                'action': url_for('delete_student', student_id=student_id),
                'hidden_items': hidden_items,
                'cancel_url': url_for('manage_students'),
                'items': items
            })
            return redirect(url_for('confirm_view', token=token), 303)

        db.session.delete(s)
        try:
            commit_with_retry()
            try:
                audit = Audit(action='delete', user=session.get('user'), student_id=student_id, details=f'Deleted student {s.name}')
                db.session.add(audit)
                try:
                    commit_with_retry()
                except OperationalError:
                    pass
            except Exception:
                pass
            flash('Student removed')
        except OperationalError:
            flash('Could not remove student right now (database busy). Please try again.')
    return redirect(url_for('manage_students'))


@app.route('/sections')
def sections():
    if 'user' not in session:
        return redirect(url_for('login'))
    # Query params for filters
    q = (request.args.get('q') or '').strip()
    selected_section = request.args.get('section', None)
    selected_subject = request.args.get('subject', None)
    selected_risk = request.args.get('risk', None)

    # Admins see all students; Teachers see only students they added
    if session.get('role') == 'Admin':
        base_q = Student.query
    else:
        base_q = Student.query.filter_by(added_by=session.get('user'))

    # Apply section filter if requested
    if selected_section:
        if selected_section == 'Unassigned':
            base_q = base_q.filter(or_(Student.section == '', Student.section == None))
        else:
            base_q = base_q.filter(Student.section == selected_section)

    # Apply name filter
    if q:
        base_q = base_q.filter(Student.name.ilike(f"%{q}%"))

    # Apply subject filter
    if selected_subject and selected_subject != 'All':
        if selected_subject == 'Unassigned':
            base_q = base_q.filter(or_(Student.subject == '', Student.subject == None))
        else:
            base_q = base_q.filter(Student.subject == selected_subject)

    # Apply risk filter
    if selected_risk and selected_risk != 'All':
        base_q = base_q.filter(Student.risk == selected_risk)

    students = base_q.all()

    sections = {}
    for s in students:
        key = s.section or 'Unassigned'
        sections.setdefault(key, []).append(s)

    # Build subjects list for filter dropdown
    if session.get('role') == 'Admin':
        raw_subjects = db.session.query(Student.subject).distinct().all()
    else:
        raw_subjects = db.session.query(Student.subject).filter(Student.added_by == session.get('user')).distinct().all()
    subjects_list = []
    for (subj,) in raw_subjects:
        if not subj or subj == '':
            subjects_list.append('Unassigned')
        else:
            subjects_list.append(subj)
    subjects_list = sorted(list(set(subjects_list)))

    # Remember last area (identifier only) so Back returns to the previous dashboard area
    session['last_area'] = 'sections'

    return render_template('sections.html', sections=sections, subjects_list=subjects_list, selected_risk=selected_risk)


@app.route('/sections/delete', methods=['POST'])
def delete_section_students():
    if 'user' not in session:
        return redirect(url_for('login'))
    if session.get('role') not in ('Admin', 'Teacher'):
        flash('Admin or Teacher access required.')
        return redirect(url_for('dashboard'))

    sec = request.form.get('section', '')
    # Map 'Unassigned' to empty string in DB
    if sec == 'Unassigned':
        sec_val = ''
    else:
        sec_val = sec

    # Only delete students in this section that were added by the current user
    q = Student.query.filter(Student.added_by == session.get('user'))
    if sec_val == '':
        q = q.filter(or_(Student.section == '', Student.section == None))
    else:
        q = q.filter(Student.section == sec_val)

    count = q.count()
    if count == 0:
        flash('No students to delete in that section.')
        return redirect(url_for('sections'))

    # Server-side confirmation fallback when JavaScript modal is not available (PRG)
    if request.method == 'POST' and request.form.get('_requires_confirm') and not request.form.get('_confirmed'):
        hidden_items = {'section': sec, '_requires_confirm': '1'}
        students_to_delete = q.all()
        items = [s.name for s in students_to_delete]
        token = create_confirm_session({
            'message': f"Delete my {count} student(s) from {sec}? This cannot be undone.",
            'action': url_for('delete_section_students'),
            'hidden_items': hidden_items,
            'cancel_url': url_for('sections'),
            'items': items
        })
        return redirect(url_for('confirm_view', token=token), 303)

    try:
        students_to_delete = q.all()
        for s in students_to_delete:
            db.session.delete(s)
            try:
                audit = Audit(action='delete', user=session.get('user'), student_id=s.id, details=f'Deleted student {s.name} via section bulk delete')
                db.session.add(audit)
            except Exception:
                pass
        try:
            commit_with_retry()
            flash(f'Deleted {count} student(s) from section {sec}.')
        except OperationalError:
            db.session.rollback()
            flash('Failed to delete students: database busy. Please try again.')
    except Exception as e:
        db.session.rollback()
        flash('Failed to delete students: ' + str(e))

    return redirect(url_for('sections'))




# =========================
# DASHBOARD
# =========================
@app.before_request
def _track_nav_history():
    # Maintain a simple navigation history (endpoints) so the Back button can return to previous dashboard area
    try:
        if 'user' in session:
            hist = session.get('nav_history', [])
            ep = request.endpoint
            if ep and ep != 'static':
                if not hist or hist[-1] != ep:
                    hist.append(ep)
                    session['nav_history'] = hist[-20:]
    except Exception:
        # Keep safe if session or request context not ready
        pass

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    # Admins see all students; Teachers see only students they added
    if session.get('role') == 'Admin':
        students = Student.query.all()
    else:
        students = Student.query.filter_by(added_by=session.get('user')).all()

    total = len(students)
    at_risk = len([s for s in students if s.risk == "High Risk"])

    # Remember last area (identifier only) so Back returns to the previous dashboard area
    session['last_area'] = 'dashboard'

    return render_template(
        'dashboard.html',
        total=total,
        at_risk=at_risk,
        role=session['role']
    )


# Risk reduction dashboard removed per request


# =========================
# PREDICTION
# =========================
@app.route('/predict', methods=['GET', 'POST'])
def predict():
    if 'user' not in session:
        return redirect(url_for('login'))

    risk = None

    if request.method == 'POST':
        # Ensure student columns exist before inserting
        try:
            ensure_student_columns()
        except Exception:
            pass

        name = request.form['name']
        attendance = float(request.form.get('attendance', 0) or 0)

        # Written works components
        activities = float(request.form.get('activities', 0) or 0)
        quizzes = float(request.form.get('quizzes', 0) or 0)
        notes = request.form.get('notes', '')
        written_works = (activities + quizzes) / 2 if (activities or quizzes) else 0

        # Performance Task (PT) components
        performance_task = float(request.form.get('performance_task', 0) or 0)

        # Exam
        exam = float(request.form.get('exam', 0) or 0)

        # Compute final grade using new weights: WW 20%, PT 50%, Exam 30%
        final_grade = round(written_works * 0.20 + performance_task * 0.50 + exam * 0.30, 2)

        # Determine risk using final_grade threshold: >=76 -> Low Risk, <=75 -> High Risk
        try:
            if final_grade >= 76:
                risk = "Low Risk"
            else:
                risk = "High Risk"
        except Exception as e:
            # Fallback if something unexpected occurs
            flash('Risk computation failed: ' + str(e))
            risk = None

        section = request.form.get('section', '')
        subject = request.form.get('subject', '')

        # Server-side confirmation fallback when JavaScript modal is not available (PRG)
        if request.form.get('_requires_confirm') and not request.form.get('_confirmed'):
            # Build hidden items to preserve form data across confirmation
            hidden_items = {k: v for k, v in request.form.items() if k not in ['_requires_confirm', '_confirmed']}
            message = f"Save student {name} (Final Grade: {final_grade})?"
            token = create_confirm_session({
                'message': message,
                'action': url_for('predict'),
                'hidden_items': hidden_items,
                'cancel_url': url_for('predict'),
                'items': [name]
            })
            return redirect(url_for('confirm_view', token=token), 303)

        student = Student(
            name=name,
            attendance=attendance,
            activities=activities,
            quizzes=quizzes,
            notes=notes,
            written_works=written_works,
            performance_task=performance_task,
            exam=exam,
            final_grade=final_grade,
            risk=risk,
            added_by=session['user'],
            section=section,
            subject=subject
        )

        db.session.add(student)
        try:
            commit_with_retry()
        except OperationalError:
            flash('Could not save student right now (database busy). Please try again.')
            return render_template('predict.html', risk=risk)
        try:
            audit = Audit(action='create', user=session.get('user'), student_id=student.id, details=f'Created student {student.name}')
            db.session.add(audit)
            try:
                commit_with_retry()
            except OperationalError:
                pass
        except Exception:
            pass

    return render_template('predict.html', risk=risk)

# =========================
# CSV IMPORT (Preview -> Save -> Download)
# =========================
@app.route('/import_csv', methods=['GET','POST'])
def import_csv():
    if 'user' not in session:
        return redirect(url_for('login'))
    if session.get('role') not in ('Admin','Teacher'):
        flash('Admin or Teacher access required.')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        f = request.files.get('file')
        if not f:
            flash('No file uploaded')
            return redirect(url_for('import_csv'))
        try:
            text = f.read().decode('utf-8')
        except Exception:
            flash('Failed to read file. Ensure it is a CSV encoded in UTF-8.')
            return redirect(url_for('import_csv'))

        reader = csv.DictReader(io.StringIO(text))
        results = []
        errors = []
        for idx, row in enumerate(reader, start=1):
            # Normalize keys to lowercase
            row = {k.strip(): (v.strip() if v is not None else '') for k,v in row.items()}
            name = row.get('name','').strip()
            if not name:
                errors.append({'row': idx, 'errors': ['missing name'], 'raw': row})
                continue
            def asfloat(x):
                try:
                    return float(x or 0)
                except Exception:
                    return None
            activities = asfloat(row.get('activities',0))
            quizzes = asfloat(row.get('quizzes',0))
            performance_task = asfloat(row.get('performance_task',0))
            exam = asfloat(row.get('exam',0))
            attendance = asfloat(row.get('attendance',0))
            if None in (activities, quizzes, performance_task, exam, attendance):
                errors.append({'row': idx, 'errors': ['invalid numeric'], 'raw': row})
                continue
            written_works = (activities + quizzes) / 2
            final_grade = round(written_works * 0.20 + performance_task * 0.50 + exam * 0.30, 2)
            risk = 'Low Risk' if final_grade >= 76 else 'High Risk'
            results.append({
                'name': name,
                'section': row.get('section',''),
                'subject': row.get('subject',''),
                'activities': activities,
                'quizzes': quizzes,
                'performance_task': performance_task,
                'exam': exam,
                'attendance': attendance,
                'notes': row.get('notes',''),
                'written_works': written_works,
                'final_grade': final_grade,
                'risk': risk
            })

        token = str(uuid.uuid4())
        tmpdir = os.path.join(app.instance_path, 'imports')
        os.makedirs(tmpdir, exist_ok=True)
        with open(os.path.join(tmpdir, token + '.json'), 'w', encoding='utf-8') as fh:
            json.dump({'results': results, 'errors': errors}, fh)

        return render_template('import_csv.html', preview=True, results=results, errors=errors, token=token)

    return render_template('import_csv.html')


@app.route('/import_csv/save/<token>', methods=['POST'])
def import_csv_save(token):
    if 'user' not in session:
        return redirect(url_for('login'))
    if session.get('role') not in ('Admin','Teacher'):
        flash('Admin or Teacher access required.')
        return redirect(url_for('dashboard'))

    tmpdir = os.path.join(app.instance_path, 'imports')
    path = os.path.join(tmpdir, token + '.json')
    if not os.path.exists(path):
        flash('Import session expired or invalid.')
        return redirect(url_for('import_csv'))

    with open(path, 'r', encoding='utf-8') as fh:
        payload = json.load(fh)

    results = payload.get('results', [])

    # Server-side confirmation fallback when JavaScript modal is not available
    if request.method == 'POST' and request.form.get('_requires_confirm') and not request.form.get('_confirmed'):
        hidden_items = {'_requires_confirm': '1'}
        items = [r['name'] for r in results[:20]]
        token = create_confirm_session({
            'message': f"Save {len(results)} student(s) to the database? This cannot be undone.",
            'action': url_for('import_csv_save', token=token),
            'hidden_items': hidden_items,
            'cancel_url': url_for('import_csv'),
            'items': items
        })
        return redirect(url_for('confirm_view', token=token), 303)

    saved = 0
    for r in results:
        s = Student(
            name=r['name'],
            section=r.get('section',''),
            subject=r.get('subject',''),
            attendance=r.get('attendance',0),
            activities=r.get('activities',0),
            quizzes=r.get('quizzes',0),
            notes=r.get('notes',''),
            written_works=r.get('written_works',0),
            performance_task=r.get('performance_task',0),
            exam=r.get('exam',0),
            final_grade=r.get('final_grade',0),
            risk=r.get('risk',''),
            added_by=session.get('user')
        )
        db.session.add(s)
        try:
            commit_with_retry()
            saved += 1
            try:
                audit = Audit(action='create', user=session.get('user'), student_id=s.id, details=f'Imported student {s.name} via CSV')
                db.session.add(audit)
                try:
                    commit_with_retry()
                except OperationalError:
                    pass
            except Exception:
                pass
        except Exception as e:
            db.session.rollback()

    flash(f'Saved {saved} student(s)')
    return redirect(url_for('manage_students'))


@app.route('/import_csv/download/<token>')
def import_csv_download(token):
    tmpdir = os.path.join(app.instance_path, 'imports')
    path = os.path.join(tmpdir, token + '.json')
    if not os.path.exists(path):
        flash('Import session expired or invalid.')
        return redirect(url_for('import_csv'))

    with open(path, 'r', encoding='utf-8') as fh:
        payload = json.load(fh)

    results = payload.get('results', [])
    # Build CSV
    si = io.StringIO()
    writer = csv.writer(si)
    header = ['name','section','subject','activities','quizzes','performance_task','exam','attendance','final_grade','risk','notes']
    writer.writerow(header)
    for r in results:
        writer.writerow([r.get(k,'') for k in header])
    out = si.getvalue()
    from flask import Response
    return Response(out, mimetype='text/csv', headers={
        'Content-Disposition': f'attachment; filename=import_results_{token}.csv'
    })

# =========================
# MAIN
# =========================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # --- Migration: ensure 'role' column exists in 'user' table ---
        db_path = os.path.join(os.getcwd(), 'database.db')
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute("PRAGMA table_info('user')")
                cols = [row[1] for row in cur.fetchall()]
                if 'role' not in cols:
                    app.logger.info("Adding 'role' column to 'user' table (default: 'Teacher').")
                    cur.execute("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'Teacher'")
                    conn.commit()
                    # Refresh SQLAlchemy engine/session to pick up schema changes
                    try:
                        db.session.remove()
                        db.engine.dispose()
                    except Exception:
                        pass
            except Exception as e:
                app.logger.exception('User table migration failed during startup')
            finally:
                conn.close()

        # Ensure student assessment columns exist at startup
        ensure_student_columns()

        # Cleanup old confirmation tokens on startup
        try:
            cleanup_confirm_sessions()
        except Exception:
            pass

    app.run(debug=True)
