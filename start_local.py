"""Start a private local server and open its dashboard without manual admin setup."""
import os
from pathlib import Path
import re
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser


def ensure_configuration(root):
    destination = root / 'config/setting.toml'
    if not destination.exists():
        text = (root / 'config/setting_example.toml').read_text(encoding='utf-8')
        values = {'api_key': secrets.token_hex(32), 'admin_username': 'admin', 'admin_password': secrets.token_urlsafe(32), 'host': '127.0.0.1', 'captcha_method': 'personal'}
        for name, value in values.items():
            text = re.sub(r'(?m)^' + name + r'\s*=.*$', name + ' = "' + value + '"', text)
        destination.write_text(text, encoding='utf-8')


def choose_port():
    for port in range(8000, 8011):
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
                return port
            except OSError:
                pass
    raise RuntimeError('Ports 8000–8010 are busy. Close another Flow2API server and start again.')


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    ensure_configuration(root)
    port = choose_port()
    ticket = secrets.token_urlsafe(36)
    os.environ['FLOW_LOCAL_DASHBOARD_TICKET'] = ticket
    os.environ['PYTHONUTF8'] = '1'
    from src.core.config import config
    from src.core.database import Database
    config.get_raw_config()['server'].update(host='127.0.0.1', port=port)
    original_reload = Database.reload_config_to_memory
    async def local_reload(self):
        await original_reload(self)
        config.get_raw_config()['server'].update(host='127.0.0.1', port=port)
    Database.reload_config_to_memory = local_reload
    from src.main import app
    import uvicorn
    base = f'http://127.0.0.1:{port}'
    def open_dashboard():
        for _ in range(180):
            try:
                with urllib.request.urlopen(base + '/login', timeout=1) as response:
                    if response.status == 200:
                        webbrowser.open(base + '/login#local=' + ticket)
                        return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.5)
        print('Dashboard startup is taking longer than expected. Close this window and run START - WIN again.')
    threading.Thread(target=open_dashboard, daemon=True).start()
    print('Preparing Flow2API. The dashboard will open automatically.')
    print('Keep this window open while using Flow2API. Press Ctrl+C to stop.')
    uvicorn.run(app, host='127.0.0.1', port=port, proxy_headers=False, log_level='warning', access_log=False)


if __name__ == '__main__':
    main()
