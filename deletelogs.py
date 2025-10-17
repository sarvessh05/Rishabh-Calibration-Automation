# deletelogs.py
# Utility to clear all files from Logs Sarveh folder

import os
import shutil

# Path to the log directory
LOGS_DIR = r"C:\Users\rishabhd4\Desktop\Logs Sarvesh"

def delete_logs():
    """
    Delete all files and subfolders inside Logs Sarveh.
    The folder itself is preserved.
    """
    if not os.path.exists(LOGS_DIR):
        print(f"❌ Folder does not exist: {LOGS_DIR}")
        return

    deleted = []
    failed = []

    for item in os.listdir(LOGS_DIR):
        path = os.path.join(LOGS_DIR, item)
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.unlink(path)  # remove file or symlink
            elif os.path.isdir(path):
                shutil.rmtree(path)  # remove subdirectory
            deleted.append(path)
        except Exception as e:
            failed.append((path, str(e)))

    print(f"✅ Deleted {len(deleted)} items from {LOGS_DIR}")
    if failed:
        print("⚠ Failed to delete:")
        for path, err in failed:
            print(f"  - {path}: {err}")

if __name__ == "__main__":
    delete_logs()