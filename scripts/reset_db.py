import sys, os
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, db, User, Student, Audit, add_role_column_if_missing, ensure_student_columns
from werkzeug.security import generate_password_hash

parser = argparse.ArgumentParser(description='Reset the application database (destructive).')
parser.add_argument('--yes', action='store_true', help='Confirm destructive action')
parser.add_argument('--admin-username', type=str, help='Admin username to create after reset')
parser.add_argument('--admin-password', type=str, help='Admin password to create after reset')
args = parser.parse_args()

if not args.yes:
    logging.warning('This script is destructive. Re-run with --yes to proceed.')
    sys.exit(1)

with app.app_context():
    # Ensure schema exists and migrations applied
    db.create_all()
    add_role_column_if_missing()
    ensure_student_columns()

    u_count = User.query.count()
    s_count = Student.query.count()
    a_count = Audit.query.count()

    logging.warning(f'About to delete all data: Users={u_count}, Students={s_count}, Audits={a_count}')

    # Delete all rows
    try:
        Audit.query.delete()
        Student.query.delete()
        User.query.delete()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.exception('Failed to delete rows during reset_db')
        sys.exit(2)

    logging.info('All tables cleared.')

    # Recreate admin if requested
    if args.admin_username and args.admin_password is not None:
        pwd_hash = generate_password_hash(args.admin_password)
        admin = User(username=args.admin_username, password=pwd_hash, role='Admin')
        db.session.add(admin)
        db.session.commit()
        logging.info(f'Admin user created: {args.admin_username}')
    else:
        logging.info('No admin created (no credentials provided).')

    logging.info('Reset complete.')
