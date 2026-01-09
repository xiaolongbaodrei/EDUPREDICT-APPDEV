import os, shutil

root = '.'
removed = 0
for dirpath, dirnames, filenames in os.walk(root):
    if os.path.basename(dirpath) == '__pycache__':
        try:
            shutil.rmtree(dirpath)
            print('Removed', dirpath)
            removed += 1
        except Exception as e:
            print('Failed to remove', dirpath, e)
print('Done. Removed', removed, '__pycache__ folders')