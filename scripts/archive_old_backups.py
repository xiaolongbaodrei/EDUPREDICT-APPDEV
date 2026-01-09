import os, tarfile, time
from datetime import timedelta, datetime

bakdir = os.path.join('instance','backups')
if not os.path.exists(bakdir):
    print('No backups directory; exiting')
    raise SystemExit(0)

now = time.time()
threshold = now - 7*24*3600  # 7 days
old_files = [os.path.join(bakdir,f) for f in os.listdir(bakdir) if os.path.isfile(os.path.join(bakdir,f)) and os.path.getmtime(os.path.join(bakdir,f)) < threshold]
if not old_files:
    print('No old backup files to archive')
    raise SystemExit(0)

archive_name = os.path.join(bakdir, 'archive-' + datetime.now().strftime('%Y%m%d%H%M%S') + '.tar.gz')
print('Archiving', len(old_files), 'files to', archive_name)
with tarfile.open(archive_name, 'w:gz') as tar:
    for f in old_files:
        tar.add(f, arcname=os.path.basename(f))

# remove originals
for f in old_files:
    try:
        os.remove(f)
    except Exception as e:
        print('Failed to remove', f, e)

print('Done')