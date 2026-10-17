"""Keep the managed runtime current before starting the local dashboard."""
import hashlib
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    requirements = root / 'requirements.txt'
    marker = root / '.runtime/requirements.sha256'
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not marker.exists() or marker.read_text().strip().lower() != digest:
        print('Preparing Flow2API requirements. The first installation may take a few minutes…', flush=True)
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(requirements)], check=True)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(digest, encoding='utf-8')
    from start_local import main as start
    start()


if __name__ == '__main__':
    main()
