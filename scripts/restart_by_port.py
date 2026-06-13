import os, subprocess, sys, time
from pathlib import Path

OD_DIR = Path(r'C:/Users/13464/odysseus')
LOG = OD_DIR / 'logs' / 'restart.log'

def kill_by_port(port: int):
    try:
        import psutil  # type: ignore
    except Exception:
        psutil = None
    if psutil is None:
        return False
    killed = 0
    for conn in psutil.net_connections(kind='inet'):
        if getattr(conn, 'laddr', None) and getattr(conn, 'pid', None):
            if getattr(conn.laddr, 'port', None) == port:
                try:
                    p = psutil.Process(conn.pid)
                    if 'python' in (p.name() or '').lower() and OD_DIR.as_posix() in ' '.join(p.cmdline()):
                        p.kill()
                        killed += 1
                        time.sleep(0.5)
                except Exception:
                    pass
    return killed > 0

if __name__ == '__main__':
    print('Killing existing Odysseus listeners on :7000 ...')
    ok = kill_by_port(7000)
    print('killed=', ok)
    time.sleep(1)
    print('Starting fresh Odysseus process ...')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, 'app.py'],
        cwd=str(OD_DIR),
        stdout=open(LOG, 'a', encoding='utf-8', errors='replace'),
        stderr=subprocess.STDOUT,
        env={**os.environ, 'OD_LOG_LEVEL': 'info'},
    )
    print('started pid=', proc.pid)
