import shutil, os, datetime, sys

src = os.path.join('instance','database.db')
if not os.path.exists(src):
    print('No instance/database.db found; nothing to back up.')
    sys.exit(0)

bakdir = os.path.join('instance','backups')
os.makedirs(bakdir, exist_ok=True)

timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
dst = os.path.join(bakdir, f'database.db.{timestamp}')

print('Backing up', src, '->', dst)
shutil.copy2(src, dst)

try:
    s1 = os.path.getsize(src)
    s2 = os.path.getsize(dst)
    print('Size source:', s1, 'Size dest:', s2)
    if s1 == s2:
        os.remove(src)
        print('Backup verified; original removed:', src)
    else:
        print('Size mismatch; not removing original.')
        sys.exit(2)
except Exception as e:
    print('Error verifying or removing:', e)
    sys.exit(3)

print('Done')