# Save Garage - Copyright (C) 2026 CoreyLyu76 (gta6-save-editor) and NotHGM - GNU GPL v3; NotHGM's parts also carry
# the additional terms in NOTICE. See LICENSE.
"""Save Garage local service. The web UI only talks to the /api endpoints here; see docs/API.md."""
import json, os, sys, subprocess, threading, time, shutil, struct, zipfile, sqlite3, mimetypes, re, traceback, ipaddress, math, secrets, hashlib
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money, garlic, savedit, updater

FROZEN = getattr(sys, 'frozen', False)
# Desktop mode (packaged builds, or the portable launchers set SAVEGARAGE_DESKTOP=1): per-user data folder,
# a Quit button in the UI and an automatic exit when the page has been closed for a while.
DESKTOP = FROZEN or os.environ.get('SAVEGARAGE_DESKTOP') == '1'
ROOT = Path(getattr(sys, '_MEIPASS', None) or Path(__file__).resolve().parent.parent)
VENDOR, UI = ROOT / 'vendor', ROOT / 'ui'
MAC = sys.platform == 'darwin'
# A packaged build runs from a read-only folder, so runtime data goes to the user's folder.
if MAC:
    APP_SUPPORT = Path.home() / 'Library' / 'Application Support'
elif os.name == 'nt':
    APP_SUPPORT = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
else:
    APP_SUPPORT = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
DATA = APP_SUPPORT / 'SaveGarage' if DESKTOP else ROOT / 'data'
# GarlicTransfer (Electron) user-data folder, used to reuse a pairing it already made.
GT_DIR = Path.home() / 'Library' / 'Application Support' / 'garlic-transfer' if MAC else Path(os.environ.get('APPDATA', '')) / 'garlic-transfer'
VERSION = '1.32.1'
PORT = int(os.environ.get('SAVEGARAGE_PORT', '7283'))          # 7283 spells SAVE on a phone keypad
# The UI listens on this computer only unless SAVEGARAGE_HOST says otherwise. SAVEGARAGE_ALLOW lists the client
# networks that may use the UI and API (default: this computer). The Host and Origin checks below also accept
# the SAVEGARAGE_HOST address.
BIND = os.environ.get('SAVEGARAGE_HOST', '127.0.0.1')
ALLOW_NETS = [ipaddress.ip_network(n.strip(), strict=False) for n in os.environ.get('SAVEGARAGE_ALLOW', '127.0.0.0/8').split(',') if n.strip()]
OK_HOSTS = ['127.0.0.1', 'localhost'] + ([BIND] if BIND not in ('', '0.0.0.0', '127.0.0.1', 'localhost') else [])
GTA_TITLES = ['PPSA01547', 'PPSA38500', 'PPSA29660']   # GTA VI title IDs (regions); PPSA29660: GarlicSaves treats it as GTA VI too
# the World tab's edits: world.py (time, health, armour), player.py (each character and the relationship), levels.py
# (strength, cardio and focus), growth.py (the four capacity bars), fog.py (the map)
WORLD_KEYS = ('time', 'health', 'armour', 'lucia', 'jason', 'relationship', 'levels', 'growth', 'fog')
NOWIN = 0x08000000 if os.name == 'nt' else 0
PY = sys.executable
LAST_SEEN = {'t': time.time()}


def py_cmd(mod, *args):
    """Run a module in a subprocess: through main.py from source, through the executable itself when packaged."""
    head = [PY, '--mod'] if FROZEN else [PY, '-u', str(ROOT / 'engine' / 'main.py'), '--mod']
    return head + [mod, *map(str, args)]
LOCK = threading.RLock()

CFG = {}
try:
    CFG = json.loads((DATA / 'config.json').read_text('utf-8'))
except Exception:
    pass
if not isinstance(CFG, dict):
    CFG = {}

# The GarlicSaves sign-in. GarlicSaves authorises each installation with the user's own account (garlic.Garlic.sign_in,
# docs/API.md). The worker key it gives is kept with the installation ID and the username in config.json in the data
# folder, as "garlicSaves", in a file only its owner can read (mode 600), and is sent nowhere but GarlicSaves: never to
# the page, the job log or an error. The update install and rollback (bootstrap.py) never touch the data folder's
# config.json. A key in SAVEGARAGE_DEV_WORKER_KEY, for development and tests only, takes the stored key's place.
SIGNED_IN = 'garlicSaves'                                   # its entry in config.json
DEV_KEY = os.environ.get(garlic.DEV_KEY_ENV) if garlic.valid_key(os.environ.get(garlic.DEV_KEY_ENV)) else None


def stored_signin(cfg):
    """The sign-in config.json holds, checked: {'key', 'installation', 'username'}, or None."""
    a = cfg.get(SIGNED_IN) if isinstance(cfg, dict) else None
    if not isinstance(a, dict) or not garlic.valid_key(a.get('workerKey')):
        return None
    inst = a.get('installationId')
    return {'key': a['workerKey'], 'installation': inst if isinstance(inst, str) and garlic.INSTALL_RE.fullmatch(inst) else '',
            'username': garlic.clean_username(a.get('username'))}


ACCOUNT = {'signin': stored_signin(CFG)}                     # the stored sign-in, or None
G = garlic.Garlic(CFG.get('serverUrl'), DEV_KEY or (ACCOUNT['signin'] or {}).get('key'), CFG.get('proxy'))


def write_private(path, text):
    """Write a file so a reader never sees half of it and it survives a power cut once this returns, readable and
    writable by its owner only (mode 600; on Windows the per-user data folder keeps it to the user)."""
    path = Path(path)
    tmp = path.with_name('%s.%s.tmp' % (path.name, secrets.token_hex(4)))
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
            f.flush()
            os.fsync(f.fileno())
        if os.name != 'nt':
            os.chmod(str(tmp), 0o600)           # whatever the umask
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            os.unlink(str(tmp))
        except OSError:
            pass
        raise
    if os.name != 'nt':                         # the rename itself, too
        try:
            d = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(d)
            finally:
                os.close(d)
        except OSError:
            pass


def save_config(remove=(), **changes):
    """Save settings to config.json in the data folder (written by write_private, mode 600: it can hold the sign-in),
    keeping what else it holds (serverUrl, proxy, autoUpdate, garlicSaves, ...). remove: entries to take out."""
    path = DATA / 'config.json'
    with LOCK:
        try:
            cur = json.loads(path.read_text('utf-8'))
        except FileNotFoundError:
            cur = {}
        except ValueError:
            raise Fail('internal', 'data/config.json is not valid JSON, so it was left as it is')
        if not isinstance(cur, dict):
            raise Fail('internal', 'data/config.json is not a JSON object, so it was left as it is')
        if not changes and not any(k in cur for k in remove):
            return                              # nothing to change: the file is left as it is
        cur.update(changes)
        for k in remove:
            cur.pop(k, None)
        DATA.mkdir(parents=True, exist_ok=True)
        write_private(path, json.dumps(cur, indent=2))
        CFG.update(changes)
        for k in remove:
            CFG.pop(k, None)


def load_signin():
    """Read the sign-in from config.json in the data folder again and use its key (the development key, when one is
    set, still comes first). A config.json holding a sign-in that others may read is made private (mode 600)."""
    path = DATA / 'config.json'
    try:
        cfg = json.loads(path.read_text('utf-8'))
    except (OSError, ValueError):
        cfg = {}
    a = stored_signin(cfg)
    if a and os.name != 'nt':
        try:
            if path.stat().st_mode & 0o077:
                os.chmod(str(path), 0o600)
        except OSError:
            pass
    with LOCK:
        ACCOUNT['signin'] = a
        G.key = DEV_KEY or (a or {}).get('key')
    return a


# Updates (engine/updater.py): a check at start-up and every 6 hours while autoUpdate is on (the default). A release
# build downloads and stages a newer signed version, installed on the next start; a source checkout or any other
# layout only shows that one is out.
UPDATER = updater.Updater(VERSION, updater.detect(ROOT, VERSION, DESKTOP), proxy=G.proxy,
                          busy=lambda: JOB['status'] == 'running', auto=CFG.get('autoUpdate', True) is not False)
RESTART = threading.Event()                                 # set by /api/update/restart: main() starts Save Garage again
SRV = {'s': None}

STATE = {'console': None, 'paired': False, 'session': None, 'user': None, 'entryId': None, 'title': None, 'fileCount': 0,
         'slots': [], 'skipped': [], 'users': [], 'readyToUpload': False, 'network': None}
JOB = {'id': 0, 'kind': None, 'status': 'idle', 'stage': None, 'needPower': False, 'progress': None, 'error': None, 'hint': None, 'accounts': None,
       'wait': None, 'log': []}
CHOICE = {'event': threading.Event(), 'owner': None}      # the PS5 account picked on the download page
CANCEL = threading.Event()                                  # set by /api/cancel, so a job waiting between tries stops
PROC = {'p': None}
RELAY = {'r': None}


HOME = os.path.expanduser('~')
CONSOLE_DIR_RE = re.compile(r'(consoles[\\/])[0-9A-Fa-f]{12}(?![0-9A-Fa-f])')


def scrub(msg):
    """Text for the details, which people paste into bug reports: the data folder becomes <data>, the home folder (it
    holds the computer's user name) ~, and a PS5's ID in a consoles/ path <console>."""
    s = str(msg)
    for path, short in ((str(DATA), '<data>'), (HOME, '~')):
        if len(path) > 3:
            s = s.replace(path, short)
    return CONSOLE_DIR_RE.sub(r'\1<console>', s)


def log(msg):
    with LOCK:
        JOB['log'].append({'t': round(time.time(), 1), 'm': scrub(msg)[:300]})
        del JOB['log'][:-200]


def relay():
    if RELAY['r'] is None:
        RELAY['r'] = garlic.OracleRelay(G, log, wait=KEY_WAIT)
    return RELAY['r']


def vendor_env(extra=None):
    e = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    e.pop(garlic.DEV_KEY_ENV, None)             # the tools get their keys from the relay, never a worker key
    e.update(extra or {})
    return e


def console_dir():
    return DATA / 'consoles' / STATE['console']['hostId']


def prefix_path():
    c = STATE['console']
    return console_dir() / ('pairing-%s.bin' % c['firmware'])


def refresh_paired():
    c = STATE['console']
    if not c:
        STATE['paired'] = False; return
    p = prefix_path()
    if not p.is_file():                      # reuse a pairing GarlicTransfer already made on this computer
        old = GT_DIR / 'pairings' / ('%s-%s' % (c['hostId'].upper(), c['firmware'].upper())) / 'pairing-prefix.bin'
        if old.is_file() and old.stat().st_size == 32:
            p.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(old, p)
    STATE['paired'] = p.is_file() and p.stat().st_size == 32


# ---------------- background jobs ----------------
class Fail(Exception):
    def __init__(self, code, detail=''):
        super().__init__(code); self.code, self.detail = code, detail


# A decrypt or encrypt job GarlicSaves turned down (garlic.GarlicRefused) ends with these codes; an invalid request is 'internal'.
GARLIC_REFUSED = {'rate_limited': 'garlic_rate_limited', 'key_disabled': 'garlic_key_disabled'}


def start_job(kind, fn):
    with LOCK:
        if JOB['status'] == 'running' or RESTART.is_set():      # nothing new starts while Save Garage restarts
            raise Fail('busy')
        JOB.update(id=JOB['id'] + 1, kind=kind, status='running', stage='starting', needPower=False, progress=None, error=None, hint=None, accounts=None,
                   wait=None, log=[])
        CANCEL.clear()

    def failed(code, detail):
        log('FAIL %s %s' % (code, detail))
        with LOCK:
            JOB.update(status='error', error={'code': code, 'detail': scrub(detail)[:300]}, needPower=False, accounts=None, wait=None)

    def run():
        try:
            fn()
            with LOCK:
                JOB.update(status='done', needPower=False, accounts=None)
        except Fail as e:
            failed(e.code, e.detail)
        except garlic.NotSignedIn:              # a backstop: no job that needs the key starts without one, and Sign out waits
            failed('not_signed_in', '')
        except garlic.GarlicRefused as e:       # its text is the HTTP status and the wait, never GarlicSaves' words
            failed(GARLIC_REFUSED.get(e.reason, 'internal'), e)
        except Exception as e:
            log(traceback.format_exc()[-600:])
            with LOCK:
                JOB.update(status='error', error={'code': 'internal', 'detail': scrub(repr(e))[:300]}, needPower=False, accounts=None)
        finally:
            kill_proc()
    threading.Thread(target=run, daemon=True).start()
    return JOB['id']


def stage(s, **kw):
    with LOCK:
        JOB.update(stage=s, **kw)
    log('stage: ' + s)


def kill_proc():
    p = PROC['p']; PROC['p'] = None
    if p and p.poll() is None:
        try:
            subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], capture_output=True, creationflags=NOWIN) if os.name == 'nt' else p.kill()
        except Exception:
            pass


def spawn(args, env=None, stdin_text=None):
    p = subprocess.Popen(py_cmd(*args), cwd=str(DATA), env=vendor_env(env), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', creationflags=NOWIN)
    PROC['p'] = p
    if stdin_text is not None:
        p.stdin.write(stdin_text); p.stdin.flush()
    return p


def run_tool(args, timeout=120):
    r = subprocess.run(py_cmd(*args), cwd=str(DATA), env=vendor_env(), capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, creationflags=NOWIN)
    if r.returncode != 0:
        raise Fail('tool_failed', (r.stdout + r.stderr)[-300:])
    return r.stdout


# ---------------- GarlicSaves sign-in (docs/API.md, "Signing in to GarlicSaves")
# One sign-in at a time, in a thread: status idle, starting (asking for a code), waiting (the code is shown until the
# user approves it on GarlicSaves), done or error (with the reason and HTTP status). Each run has a number, so a run that
# was cancelled or replaced changes nothing when it ends.
SIGNIN = {'run': 0, 'status': 'idle', 'code': None, 'link': None, 'until': None, 'error': None, 'http': None, 'stop': None}
# the jobs that go through GarlicSaves (the key relay, decrypt, encrypt): refused with not_signed_in without a key
NEEDS_SIGNIN = ('/api/pair', '/api/download', '/api/patch', '/api/upload')


def signin_start():
    """Start signing in to GarlicSaves, unless a sign-in is already under way."""
    with LOCK:
        if SIGNIN['status'] in ('starting', 'waiting'):
            return
        stop = threading.Event()
        SIGNIN.update(run=SIGNIN['run'] + 1, status='starting', code=None, link=None, until=None, error=None, http=None, stop=stop)
        run = SIGNIN['run']
    threading.Thread(target=signin_run, args=(run, stop), daemon=True).start()


def signin_end(run, status, error=None, http=None):
    with LOCK:
        if SIGNIN['run'] == run:
            SIGNIN.update(status=status, code=None, link=None, until=None, error=error, http=http)


def signin_run(run, stop):
    def mine():
        return SIGNIN['run'] == run and not stop.is_set()

    def on_code(code, link, seconds):
        with LOCK:
            if mine():
                SIGNIN.update(status='waiting', code=code, link=link, until=time.monotonic() + seconds)
    try:
        got = G.sign_in(on_code, stop)
    except garlic.SignInError as e:             # the reason and the HTTP status only, never GarlicSaves' words
        if e.code == 'cancelled':
            signin_end(run, 'idle')
        else:
            signin_end(run, 'error', e.code, e.status)
        return
    except Exception:
        signin_end(run, 'error', 'internal')
        return
    with LOCK:
        if not mine():
            return                              # cancelled while the last answer came: its key isn't kept
        try:
            keep_signin(got)
        except (Fail, OSError):                 # config.json couldn't be written: nothing is kept
            signin_end(run, 'error', 'not_saved')
            return
        SIGNIN.update(status='done', code=None, link=None, until=None, error=None, http=None)


def keep_signin(got):
    """Store a new sign-in in config.json (mode 600) and use its key from now on."""
    with LOCK:
        save_config(**{SIGNED_IN: {'workerKey': got['worker_key'], 'installationId': got['installation_id'],
                                   'username': got['username']}})
        ACCOUNT['signin'] = {'key': got['worker_key'], 'installation': got['installation_id'], 'username': got['username']}
        G.key = DEV_KEY or got['worker_key']


def signin_cancel():
    with LOCK:
        if SIGNIN['status'] in ('starting', 'waiting'):
            SIGNIN['stop'].set()
            SIGNIN.update(run=SIGNIN['run'] + 1, status='idle', code=None, link=None, until=None, error=None, http=None)


def sign_out():
    """Forget the GarlicSaves sign-in on this computer: its entry in config.json and its key. Refused while a job runs,
    which may still need the key."""
    with LOCK:
        if JOB['status'] == 'running':
            raise Fail('busy')
        signin_cancel()
        save_config(remove=(SIGNED_IN,))
        ACCOUNT['signin'] = None
        G.key = DEV_KEY
        SIGNIN.update(status='idle', error=None, http=None)


def garlic_state():
    """state.garlic for the page (docs/API.md): whether Save Garage is signed in to GarlicSaves, and how a sign-in is
    going. Never the key."""
    with LOCK:
        a, s = ACCOUNT['signin'], dict(SIGNIN)
    waiting = s['status'] == 'waiting'
    return {'signedIn': bool(G.key), 'username': (a['username'] or None) if a and not DEV_KEY else None, 'stored': bool(a),
            'devKey': bool(DEV_KEY), 'refused': G.refused(),
            'signin': {'status': s['status'], 'code': s['code'] if waiting else None, 'link': s['link'] if waiting else None,
                       'expiresIn': max(0, math.ceil(s['until'] - time.monotonic())) if waiting and s['until'] else None,
                       'error': s['error'], 'http': s['http']}}


# ---------------- steps ----------------
def local_ipv4s():
    """(IP, broadcast) for each local interface. On macOS gethostbyname_ex often returns only 127.0.0.1, so read ifconfig."""
    if MAC:
        txt = subprocess.run(['/sbin/ifconfig'], capture_output=True, text=True, timeout=5).stdout
        return re.findall(r'inet (\d+\.\d+\.\d+\.\d+) netmask \S+ broadcast (\d+\.\d+\.\d+\.\d+)', txt)
    import socket
    return [(ip, ip.rsplit('.', 1)[0] + '.255') for ip in set(socket.gethostbyname_ex(socket.gethostname())[2])]


def sweep(timeout=2.5):
    """If nobody answers the broadcast, unicast SRCH to every address in this computer's /24. Some routers don't pass broadcasts on (seen with a Mac on Wi-Fi)."""
    import socket, select
    from poc.dt_discovery import SRCH, parse_response
    found, socks = {}, []
    try:
        for ip, _ in local_ipv4s():
            if ip.startswith(('127.', '169.254.', '198.18.')):
                continue
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); socks.append(s)
            s.bind((ip, 0)); s.setblocking(False)
            for n in range(1, 255):
                host = ip.rsplit('.', 1)[0] + '.%d' % n
                if host != ip:
                    try:
                        s.sendto(SRCH, (host, 1006))
                    except OSError:
                        pass
        end = time.time() + timeout
        while socks and time.time() < end:
            for s in select.select(socks, [], [], 0.2)[0]:
                try:
                    d, a = s.recvfrom(4096)
                except OSError:
                    continue
                if d.startswith(b'HTTP/1.1'):
                    found[a[0]] = parse_response(d, a)
    finally:
        for s in socks:
            s.close()
    return list(found.values())


def discover():
    routes = [{'bind': '', 'target': '255.255.255.255'}]
    try:                                        # one broadcast per interface; the global broadcast often leaves through the wrong interface with VPNs or virtual adapters
        for ip, bc in local_ipv4s():
            if not ip.startswith(('127.', '169.254.', '198.18.')):
                routes.append({'bind': ip, 'target': bc})
    except (OSError, subprocess.SubprocessError):
        pass
    out = run_tool(['poc.dt_discovery', '--timeout', '3', '--routes', json.dumps(routes)], timeout=30)
    cons = json.loads(out.strip().splitlines()[-1])['consoles']
    try:                                        # probe the last console used directly (a broadcast cannot reach it from another subnet)
        last = json.loads((DATA / 'last_console.json').read_text('utf-8'))['host']
        if not any(c['host'] == last for c in cons):
            c = probe_host(last)
            if c:
                cons.append(c)
    except Exception:
        pass
    if not cons:
        try:
            cons = sweep()
        except (OSError, subprocess.SubprocessError):
            pass
    # drop transfer processes on this computer that pose as a console (hostId 02000000xxxx)
    return [{'host': c['host'], 'name': c['name'], 'hostId': c['hostId'], 'firmware': c['firmware']} for c in cons
            if c.get('hostId') and not c['hostId'].startswith('0200000000') and not c['host'].startswith('127.')]


def probe_host(host):
    out = run_tool(['poc.dt_discovery', '--broadcast', host, '--timeout', '3'], timeout=30)
    cons = json.loads(out.strip().splitlines()[-1])['consoles']
    return cons[0] if cons else None


def refused_key_request(t0):
    """Pairing and sending back can't go on without the keys of a transfer-key request either: when one GarlicSaves
    turned down (KEY_REFUSED) has ended since t0, a time.monotonic() value, raise its code, with its line as the detail."""
    for d in relay().derivations.since(t0):
        why = d.reason()
        if d.answered is False and why in KEY_REFUSED:
            raise Fail(KEY_REFUSED[why], d.summary())


def job_pair():
    c = STATE['console']; prefix_path().parent.mkdir(parents=True, exist_ok=True)
    opts = {'ps5Ip': c['host'], 'hostId': c['hostId'], 'systemVersion': c['firmware'], 'oracleHost': '127.0.0.1', 'oraclePort': relay().port,
            'prefixPath': str(prefix_path()), 'duration': 300}
    t0 = time.monotonic()
    p = spawn(['poc.dt_pair', '-'], stdin_text=json.dumps(opts) + '\n')
    stage('pair_waiting_console')
    ok = False
    for line in p.stdout:
        line = line.strip(); log(line)
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get('type') == 'status' and 'connected' in ev.get('message', ''):
            stage('pair_reading')
        if ev.get('type') == 'paired':
            ok = True
        if ev.get('type') == 'error':
            refused_key_request(t0)             # GarlicSaves turned the sign-in down: say so, not just "pairing failed"
            raise Fail('pair_failed', ev.get('message'))
    p.wait()
    if not ok:
        refused_key_request(t0)
        raise Fail('pair_failed')
    refresh_paired(); stage('paired')


def sfo_fields(path):
    p = Path(path).read_bytes(); out = {}
    magic, ver, kt, dt, n = struct.unpack_from('<4sIIII', p, 0)
    for i in range(n):
        ko, fmt, ln, mx, do = struct.unpack_from('<HHIII', p, 20 + 16 * i)
        k = p[kt + ko:p.index(b'\0', kt + ko)].decode()
        d = p[dt + do:dt + do + ln]
        out[k] = d.rstrip(b'\0').decode('utf-8', 'replace') if fmt == 0x204 else d
    acct = b''
    for off in (0x1b8, 0x15c):
        v = p[off:off + 8]
        if any(v):
            acct = v; break
    out['_account'] = acct.hex()
    return out


DECRYPT_TRIES = 3                       # decrypts of one slot, in all, before it is left out as unreadable


class Unreadable(Exception):
    """A story slot that can't be read: why is 'damaged' (GarlicSaves kept sending back a copy that isn't a save) or
    'layout' (a save, but not laid out the way Save Garage knows)."""

    def __init__(self, name, why, detail=''):
        super().__init__('%s: %s %s' % (name, why, detail))
        self.why = why


def inner_name(name):
    return 'memory.dat' if name == 'sdimg_sce_sdmemory' else name.replace('sdimg_SAVEDATA', '')


def damaged(name, top):
    """Why a decrypted slot folder isn't a readable save copy, or None. GarlicSaves has sent back a damaged copy now and
    then (issue #11: the slot's save file replaced by a 450 KB file starting with ASAV and its chives.dat missing), while
    the same image decrypted fine before and after."""
    f = top / inner_name(name)
    if not f.is_file():
        return 'no %s in it' % inner_name(name)
    if not (top / 'sce_sys' / 'param.sfo').is_file():
        return 'no param.sfo in it'
    with open(f, 'rb') as fh:
        head = fh.read(4)
    if head != b'JSAV':
        return 'its save file starts with %r, not JSAV' % head
    return None


def load_slot(sess, name, enc_path):
    """Decrypt one save slot and read its balances. A damaged copy is asked for again, up to DECRYPT_TRIES decrypts in all;
    raises Unreadable when the slot still can't be read."""
    dec_root = sess / 'dec'
    for n in range(1, DECRYPT_TRIES + 1):
        top = Path(G.decrypt(str(enc_path), str(dec_root), on_status=lambda s: log('decrypt %s: %s' % (name, s))))
        problem = damaged(name, top)
        if not problem:
            try:
                return read_slot(name, top)
            except Exception as e:              # a JSAV copy laid out in a way the reader doesn't know
                raise Unreadable(name, 'layout', repr(e))
        log('decrypt %s: GarlicSaves sent back a damaged copy (%s)%s' % (name, problem, '; asking again' if n < DECRYPT_TRIES else ''))
        if top.parent == dec_root and top.is_dir():
            shutil.rmtree(top)              # so the next copy isn't mixed with this one's files
    raise Unreadable(name, 'damaged')


def skipped_slot(sess, name, why):
    """How the page lists a slot left out: its file, and its title when the copy's param.sfo can be read."""
    try:
        subtitle = sfo_fields(sess / 'dec' / name / 'sce_sys' / 'param.sfo').get('SUBTITLE', '')
    except Exception:
        subtitle = ''
    return {'file': name, 'subtitle': subtitle if isinstance(subtitle, str) else '', 'why': why}



# ---------------- sending to another account on the same PS5 ----------------
def ps5_users(lib):
    """The users of the PS5 the session came from (its transfer data): [{'id': 8-hex user ID, 'name'}]. No account IDs."""
    try:
        db = sqlite3.connect((Path(lib) / 'Transfer-Metadata' / 'metadata.db').as_uri() + '?mode=ro', uri=True)
        try:
            rows = db.execute('SELECT user_id, user_name, login_id, online_id FROM user_info_tbl ORDER BY user_id').fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return []
    return [{'id': '%08x' % u, 'name': n or l or o or 'user'} for u, n, l, o in rows if isinstance(u, int)]


def sfo_account_of(metadata, user_id):
    """The PSN account ID of a PS5 user, in the byte order param.sfo stores it (what GarlicSaves' encrypt and resign take).
    The transfer data holds it as a 64-bit number whose hex digits run the other way."""
    db = sqlite3.connect(Path(metadata).as_uri() + '?mode=ro', uri=True)
    try:
        row = db.execute('SELECT account_id FROM user_info_tbl WHERE user_id = ?', (int(user_id, 16),)).fetchone()
    finally:
        db.close()
    if not row or not isinstance(row[0], int) or not row[0]:
        raise Fail('resign_failed', 'no account ID for that user')
    return (row[0] & 0xffffffffffffffff).to_bytes(8, 'big')[::-1].hex()


RESIGN_TRIES = 3                        # a resign job GarlicSaves rate-limits is sent again after its wait, this many times


def copy_to_user(sess, lib, entry_id, target):
    """The library entry's saves as another PS5 user's: every file re-signed for that user's account by GarlicSaves (one
    resign job a file), registered as a new entry under /user/home/<target>/savedata_prospero/<title>/. Each file keeps
    the PS5's own GFP5 header with only the entry ID and the user in its path changed. Before anything is sent, one
    re-signed file is decrypted again to check it carries the new account. Returns (new entry ID, {'id', 'name'}). A copy
    already made in this session from the same files is used again."""
    users = {u['id']: u for u in ps5_users(lib)}
    if target not in users:
        raise Fail('bad_request')
    meta = Path(lib) / 'Transfer-Metadata' / 'metadata.db'
    account = sfo_account_of(meta, target)
    root_manifest = Path(lib) / 'Transfer-Metadata' / 'manifest.json'
    doc = json.loads(root_manifest.read_text('utf-8'))
    entry = doc[str(entry_id)]
    owner, title = STATE['user']['id'], STATE['title']
    src_dir = Path(lib) / 'Saves' / owner / title
    sources = [src_dir / it['file'] for it in entry['files']]
    if not sources or not all(s.is_file() for s in sources):
        raise Fail('resign_failed', 'a save file of the entry is missing')
    digests = [hashlib.sha256(s.read_bytes()).hexdigest() for s in sources]
    work = sess / 'copies' / target
    marker = work / 'copy.json'
    if marker.is_file():
        try:
            m = json.loads(marker.read_text('utf-8'))
            if m.get('source') == digests and str(m.get('entry')) in json.loads(root_manifest.read_text('utf-8')):
                log('copy for %s: using the one made earlier in this session' % users[target]['name'])
                entry_row(meta, int(m['entry']), target, title, int(m.get('size') or 0))
                return int(m['entry']), dict(users[target])
        except (ValueError, KeyError, TypeError):
            pass
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    out = []
    for i, src in enumerate(sources):
        with LOCK:
            JOB['progress'] = {'files': i, 'total': len(sources)}
        stage('resigning')
        dest = work / src.name
        for attempt in range(RESIGN_TRIES + 1):
            try:
                G.resign(str(src), account, str(dest), on_status=lambda s, n=src.name: log('resign %s: %s' % (n, s)))
                break
            except garlic.RateLimited as e:
                if attempt == RESIGN_TRIES:
                    raise
                wait = min(e.retry_after or 60, 75)
                log('resign %s: GarlicSaves is limiting requests, trying again in %d s' % (src.name, wait))
                if pause(wait):
                    raise Fail('cancelled')
            except garlic.GarlicRefused:
                raise
            except garlic.GarlicError as e:
                raise Fail('resign_failed', '%s: %s' % (src.name, e))
        out.append(dest)
    with LOCK:
        JOB['progress'] = {'files': len(sources), 'total': len(sources)}
    # check one copy: decrypted again, it must carry the new account (the smallest story slot, else the first file)
    probe = min((d for d in out if SLOT_RE.fullmatch(d.name)), key=lambda d: d.stat().st_size, default=out[0])
    stage('resign_check')
    top = Path(G.decrypt(str(probe), str(work / 'check'), on_status=lambda s: log('check %s: %s' % (probe.name, s))))
    got = sfo_fields(top / 'sce_sys' / 'param.sfo').get('_account')
    if got != account:
        raise Fail('resign_failed', 'the copy is still signed for another account')
    new_id = register_copy(lib, entry_id, entry, target, title, out)
    marker.write_text(json.dumps({'source': digests, 'entry': new_id, 'size': sum(f.stat().st_size for f in out)}), 'utf-8')
    log('copy for %s: %d files re-signed and checked, entry %d' % (users[target]['name'], len(out), new_id))
    return new_id, dict(users[target])


def register_copy(lib, entry_id, entry, target, title, files):
    """Add the re-signed files as a library entry of user target: payloads under Saves/<target>/<title>/, the entry in
    both manifests (as dt_metadata.persist_manifest_entry writes them) and its row in the transfer data. Returns its ID."""
    lib = Path(lib)
    meta = lib / 'Transfer-Metadata' / 'metadata.db'
    root_manifest = lib / 'Transfer-Metadata' / 'manifest.json'
    doc = json.loads(root_manifest.read_text('utf-8'))
    db = sqlite3.connect(str(meta))
    try:
        used = {int(k) for k in doc if k.isdigit()} | {r[0] for r in db.execute('SELECT id FROM dir_entry_info_tbl')}
        new_id = max(used | {99999}) + 1       # above any ID a console browse gives
        dest = lib / 'Saves' / target / title
        dest.mkdir(parents=True, exist_ok=True)
        items, total = [], 0
        for it, f in zip(entry['files'], files):
            data = f.read_bytes()
            (dest / it['file']).write_bytes(data)
            path = '/user/home/%s/savedata_prospero/%s/%s' % (target, title, it['file'])
            header = bytearray.fromhex(it['header'])
            if len(header) != 1304 or header[276:1300].split(b'\0', 1)[0].decode() != it['path']:
                raise Fail('resign_failed', 'unexpected transfer header for ' + it['file'])
            struct.pack_into('<I', header, 4, new_id)
            header[276:1300] = bytes(1024)
            header[276:276 + len(path)] = path.encode()
            struct.pack_into('<Q', header, 0x20, len(data))
            struct.pack_into('<Q', header, 0xF0, len(data))
            items.append({'path': path, 'file': it['file'], 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                          'header': header.hex()})
            total += len(data)
        final = bytearray.fromhex(entry['final_header'])
        struct.pack_into('<I', final, 4, new_id)
        new_entry = {'files': items, 'final_header': final.hex()}
        doc[str(new_id)] = new_entry
        tmp = root_manifest.with_name(root_manifest.name + '.copy.tmp')
        tmp.write_text(json.dumps(doc, indent=2) + '\n', 'utf-8')
        os.replace(tmp, root_manifest)
        em = lib / 'Transfer-Metadata' / str(new_id)
        em.mkdir(parents=True, exist_ok=True)
        (em / 'manifest.json').write_text(json.dumps({'entry_id': new_id, 'files': items, str(new_id): new_entry}, indent=2) + '\n', 'utf-8')
    finally:
        db.close()
    entry_row(meta, new_id, target, title, total)
    return new_id


def entry_row(meta, new_id, target, title, total):
    """Make the transfer data hold exactly one row for the target user's save folder of this title: dt_metadata's upload
    builder matches the copy to that row and sends it under the PS5's own entry ID. When the PS5 already listed the folder
    (the account had a save of this title when the saves were downloaded), its row is the one, and a row of ours for the
    same folder is taken out again; otherwise the copy gets a row of its own."""
    path = '/user/home/%s/savedata_prospero/%s/' % (target, title)
    db = sqlite3.connect(str(meta))
    try:
        rows = [r[0] for r in db.execute('SELECT id FROM dir_entry_info_tbl WHERE target_type = 3 AND lower(path) = lower(?)', (path,))]
        console = [r for r in rows if r != new_id]
        if console:
            db.execute('DELETE FROM dir_entry_info_tbl WHERE id = ?', (new_id,))
        elif not rows:
            db.execute('INSERT INTO dir_entry_info_tbl (id, path, partition, target_type, target_subtype, title_id, content_id, actual_size, '
                       'transfer_size, required_size, required_zone_size) VALUES (?, ?, 1, 3, 0, \'\', \'\', ?, ?, ?, 0)',
                       (new_id, path, total, total, total))
        db.commit()
    finally:
        db.close()


# sce_sdmemory is the game's autosave (what Continue loads); its memory.dat has the same format as manual saves
SLOT_RE = re.compile(r'sdimg_(SAVEDATASARC\d+|sce_sdmemory)')


def read_slot(name, top):
    """Read a save slot's balances from its decrypted folder."""
    inner = inner_name(name)
    f = top / inner
    if not f.is_file():
        raise Fail('unexpected_save_layout', name)
    sfo = sfo_fields(top / 'sce_sys' / 'param.sfo')
    data = f.read_bytes()
    info = money.scan(data)
    try:                                        # ammo each protagonist carries
        ammo = savedit.ammo(savedit.section(data, money.SEC_INV))
    except Exception:
        ammo = []
    return {'file': name, 'inner': inner, 'subtitle': sfo.get('SUBTITLE', ''), 'revision': sfo.get('SAVEDATA_REVISION', b'').hex() if isinstance(sfo.get('SAVEDATA_REVISION'), bytes) else '',
            'dir': str(top), 'account': sfo['_account'], 'items': info['items'], 'ledger': info['ledger'], 'ammo': ammo,
            'modified': False, 'changes': [], 'applied': None}


# ---------------- detail data for the editor ----------------
CACHE = {}


def slot_by_file(name):
    return next((s for s in STATE['slots'] if s['file'] == name), None)


def slot_bytes(slot):
    return (Path(slot['dir']) / slot['inner']).read_bytes()


def cached(key, fn):
    k = (STATE['session'],) + key
    if k not in CACHE:
        CACHE[k] = fn()
    return CACHE[k]


def completion_readers(b):
    """(key, reader) for every part of the Completion tab."""
    import compendium, discovery, challenges, gyms, activities, checklist, tasks, gangs, robberies, fencing, activities2, hoops, vehicles_compendium
    import collectibles2 as collectibles
    return [('stunts', lambda: savedit.stunts(savedit.section(b, money.SEC_STAT))), ('compendium', lambda: compendium.read(b)),
            ('discovery', lambda: discovery.read(b)), ('challenges', lambda: challenges.read(b)), ('gyms', lambda: gyms.read(b)),
            ('activities', lambda: activities.read(b)), ('checklist', lambda: checklist.read(b)), ('tasks', lambda: tasks.read(b)),
            ('gangs', lambda: gangs.read(b)), ('robberies', lambda: robberies.read(b)), ('fencing', lambda: fencing.read(b)),
            ('activities2', lambda: activities2.read(b)), ('hoops', lambda: hoops.read(b)), ('vehicles', lambda: vehicles_compendium.read(b)),
            ('collectibles', lambda: collectibles.read(b)), ('cheats', lambda: challenges.read_cheats(b))]


def completion_preview(slot, body):
    """The game's 100% checklist as it would be after these stat, gun and Completion edits (the guns add weapons to the
    compendium, which the checklist counts). Nothing is written."""
    import checklist
    c = body.get('completion') or {}
    if not isinstance(c, dict) or not isinstance(body.get('stats') or [], list) or not isinstance(body.get('guns') or {}, dict):
        raise ValueError('completion and guns must be objects and stats a list')
    edits = {'stats': body.get('stats') or [], 'completion': {k: c[k] for k in savedit.COMPLETION_KEYS if c.get(k)}}
    if body.get('guns'):
        edits['guns'] = body['guns']
    b = slot_bytes(slot)
    try:
        nb, _ = savedit.apply(b, edits)
    except Exception as e:                      # find which parts fail on their own, so the page can say which
        failed = []
        for k, v in edits['completion'].items():
            try:
                savedit.apply(b, {'completion': {k: v}})
            except Exception:
                failed.append(k)
        if edits.get('guns'):
            try:
                savedit.apply(b, {'guns': edits['guns']})
            except Exception:
                failed.append('guns')
        if edits['stats']:
            try:
                savedit.apply(b, {'stats': edits['stats']})
            except Exception:
                failed.append('stats')
        return {'ok': False, 'failed': failed, 'detail': repr(e)[:200]}
    r = checklist.read(nb)
    return {'ok': True, 'overall': r['overall'],
            'lines': [{'key': l['key'], 'value': l.get('value'), 'of': l.get('of'), 'percent': l.get('percent'), 'done': l.get('done')} for l in r['lines']]}


def slot_featured(slot):
    return cached(('featured', slot['file']), lambda: savedit.featured(savedit.section(slot_bytes(slot), money.SEC_STAT)))


def varying_keys():
    """Stat keys whose value differs between the slots of this download (a sign the game actually uses them)."""
    def build():
        vals = {}
        for s in STATE['slots']:
            groups, _ = savedit.stat_rows(savedit.section(slot_bytes(s), money.SEC_STAT))
            for g, G in groups.items():
                for r in range(len(G['value'])):
                    vals.setdefault((g, G['base'][r], G['qual'][r], G['owner'][r]), set()).add(json.dumps(G['value'][r]))
        return {k for k, v in vals.items() if len(v) > 1}
    return cached(('varies',), build)


def slot_weapons(slot):
    return cached(('weapons', slot['file']), lambda: savedit.weapons(savedit.section(slot_bytes(slot), money.SEC_INV)))


def slot_guns(slot):
    """The guns each character can be given (guns.py), or None with the reason when the save can't show them."""
    def build():
        import guns
        try:
            return guns.read(slot_bytes(slot)), None
        except Exception as e:                  # a save this can't read leaves the rest of the Ammo tab working
            return None, repr(e)[:200]
    return cached(('guns', slot['file']), build)


def slot_detail(slot):
    guns, err = slot_guns(slot)
    return {'file': slot['file'], 'featured': slot_featured(slot), 'ammo': slot.get('ammo') or [], 'weapons': slot_weapons(slot),
            'guns': guns, 'errors': {'guns': err} if err else {}, 'applied': slot.get('applied'), 'modified': slot['modified']}


def slot_stats(slot):
    def build():
        t = savedit.stats_table(savedit.section(slot_bytes(slot), money.SEC_STAT))
        vk = varying_keys()
        for G in t['groups']:
            G['varies'] = [r for r in range(len(G['value'])) if (G['key'], G['base'][r], G['qual'][r], G['owner'][r]) in vk]
        return json.dumps(t, ensure_ascii=False).encode('utf-8')
    return cached(('stats', slot['file']), build)


def _completion_label(x):
    """A readable line for a Completion feature's log entry that has no label of its own."""
    if x.get('gym'):
        return 'Gym membership added'
    if x.get('title') or x.get('category') and x.get('n'):
        return 'Challenge completed: ' + str(x.get('category', '')).capitalize()
    if 'added' in x and x.get('group'):
        return 'Compendium: %s added' % x['group']
    if 'score' in str(x.get('step', '')):
        return 'Challenge progress kept in step'
    return str(x.get('category') or x.get('feature') or 'Change')


def summarize(plog):
    out = []
    for x in plog:
        w = x.get('what')
        if w == 'money':
            out.append({'kind': x.get('kind'), 'from': x.get('from'), 'to': x.get('to')})
        elif w == 'ammo':
            out.append({'kind': 'ammo', 'label': '%s (%s)' % (x.get('label') or x['type'] + ' ammo', 'Lucia' if x['inv'] == 0 else 'Jason'),
                        'from': x['from'], 'to': x['to']})
        elif w in ('world', 'raw', 'completion', 'guns'):
            label = str(x.get('label') or _completion_label(x))
            same = next((c for c in out if c.get('kind') == 'stat' and c['label'] == label), None)
            if same and w == 'completion':
                same['count'] = same.get('count', 1) + 1
            else:
                to = x.get('to', ('%s added' % x['added']) if 'added' in x else 'done')
                out.append({'kind': 'stat', 'label': label, 'from': x.get('from', ''), 'to': to})
        elif w == 'stat':
            label = x.get('label') or 'Stat'
            same = next((c for c in out if c.get('kind') == 'stat' and c['label'] == label), None)
            if same:                                   # bulk edits (such as every stunt) collapse into one line
                same['count'] = same.get('count', 1) + 1
            else:
                out.append({'kind': 'stat', 'label': label, 'from': x['from'], 'to': x['to']})
    return out


RESTORE_HOURS = float(os.environ.get('SAVEGARAGE_RESTORE_HOURS', 6))


def restore_session():
    """After a restart, pick up the latest download so the power button doesn't have to be pressed again. Reads local files only.
    Skips downloads already sent back or older than RESTORE_HOURS: the player may have saved new progress since."""
    sessions = sorted(p for p in (console_dir() / 'sessions').glob('*') if p.is_dir())
    if not sessions:
        return
    sess = sessions[-1]
    try:
        age = time.time() - time.mktime(time.strptime(sess.name, '%Y%m%d-%H%M%S'))
    except ValueError:
        return
    if age > RESTORE_HOURS * 3600 or (sess / 'uploaded').exists():
        return
    lib = sess / 'lib'
    db = sqlite3.connect((lib / 'Transfer-Metadata' / 'metadata.db').as_uri() + '?mode=ro', uri=True)
    try:
        rows = db.execute('SELECT id, path FROM dir_entry_info_tbl ORDER BY id').fetchall()
        names = {'%08x' % u: n or l or o for u, n, l, o in db.execute('SELECT user_id, user_name, login_id, online_id FROM user_info_tbl')}
    finally:
        db.close()
    for entry_id, path in rows:                 # same as job_download: the first GTA save entry
        parts = path.strip('/').split('/')
        if len(parts) > 2 and parts[-1] in GTA_TITLES and (lib / 'Saves' / parts[2] / parts[-1]).is_dir():
            owner, title = parts[2], parts[-1]
            break
    else:
        return
    slots, skipped = [], []
    for f in sorted((lib / 'Saves' / owner / title).glob('sdimg_*')):
        top = sess / 'dec' / f.name
        if SLOT_RE.fullmatch(f.name) and top.is_dir():
            why = 'damaged' if damaged(f.name, top) else None
            if not why:
                try:
                    s = read_slot(f.name, top)
                except Exception:
                    why = 'layout'
            if why:                             # left out when it was downloaded, as job_download does
                skipped.append(skipped_slot(sess, f.name, why))
                continue
            orig = sess / 'orig' / f.name
            s['modified'] = orig.is_file() and orig.read_bytes() != f.read_bytes()   # the transfer library already holds an edited save
            ed = sess / 'mod' / (f.name + '.edits.json')                  # edits applied before a restart
            if s['modified'] and ed.is_file():
                try:
                    s['applied'] = json.loads(ed.read_text('utf-8'))
                except ValueError:
                    pass
            slots.append(s)
    if not slots:
        return
    with LOCK:
        STATE.update(session=str(sess), user={'id': owner, 'name': names.get(owner.lower(), 'user')}, entryId=entry_id, title=title,
                     slots=slots, skipped=skipped, users=ps5_users(lib), readyToUpload=any(s['modified'] for s in slots),
                     fileCount=len(list((lib / 'Saves' / owner / title).glob('sdimg_*'))))
    log('restored session ' + sess.name)


# The transfer code waits 30 s for each set of keys from the relay (derive_with_oracle in vendor/poc/dt_ppr_client.py),
# so a derivation that hasn't answered by then has failed it. How long the PS5 itself waits in that handshake isn't
# known, so these waits stay as they are.
KEY_WAIT = 30
KEY_RETRY_WAIT = 5                      # seconds before the one automatic second try when the key service was too slow
# ... and when GarlicSaves rate limited a key request: until its Retry-After is over (60 s when it gave none), at most 75 s
KEY_LIMIT_WAIT, KEY_LIMIT_MAX = garlic.RATE_WINDOW, 75
# A key request GarlicSaves refused ends the download with the code for its reason. A refused invalid request has none:
# the transfer code's own error gives the code then.
KEY_REFUSED = {'key_disabled': 'key_disabled', 'rate_limited': 'key_rate_limited'}


def download_try(opts):
    """Run the download worker once. Returns what it reported, with the last stage it reached."""
    p = spawn(['dl_worker', json.dumps(opts)])
    r = {'entries': [], 'users': [], 'nosave': False, 'err': None, 'files': 0, 'chosen': None, 'stage': None}

    def at(s, **kw):
        r['stage'] = s; stage(s, **kw)
    at('connecting')
    for line in p.stdout:
        line = line.rstrip()
        if line.startswith('[file] saved'):
            r['files'] += 1
            with LOCK:
                JOB['progress'] = {'files': r['files']}
            log('saved file %d' % r['files']); continue
        try:
            ev = json.loads(line)
        except ValueError:
            if line and not line.startswith(('[ddp]', 'host-', 'device-', 'system-', '[file]')):   # [file] paths hold the PS5 user ID
                log(line)
            continue
        t = ev.get('type')
        if t == 'powerRequired':
            at('need_power', needPower=True)
        elif t == 'status' and ev.get('step') == 3:
            at('reading_list', needPower=False)
        elif t == 'status' and ev.get('step') == 4:
            at('downloading', needPower=False)
        elif t == 'entries':
            r['entries'], r['users'] = ev['entries'], ev.get('users') or []
        elif t == 'accounts':                   # several PS5 accounts have a save: ask which one, then tell the worker
            CHOICE['owner'] = None; CHOICE['event'].clear()
            at('choose_account', accounts=ev.get('accounts') or [])
            while not CHOICE['event'].wait(0.5):
                if p.poll() is not None:        # cancelled or the worker died
                    break
            if p.poll() is not None or not CHOICE['owner']:
                raise Fail('download_failed', 'cancelled while choosing the account')
            p.stdin.write(json.dumps({'owner': CHOICE['owner']}) + '\n'); p.stdin.flush()
            at('downloading', accounts=None)
        elif t == 'owner':
            r['chosen'] = ev.get('owner')
        elif t == 'nosave':
            r['nosave'] = True
        elif t == 'error':
            r['err'] = ev.get('message')
        elif t == 'log':
            msg = ev.get('message') or ''
            log('Encrypted channel: open' if msg.startswith('Encrypted channel:') else msg)    # not the PS5's address: details get shared in bug reports
    p.wait()
    return r


def download_error(err, reached, late, refused=None):
    """The error code for a failed download try. A key request GarlicSaves refused decides it (refused: that derivation's
    reason, see KEY_REFUSED): the transfer code can't go on without those keys. Otherwise a timeout while the power prompt
    is up is the power button's; any other timeout is the key service's when a derivation of this try gave the transfer
    code no keys in time (late), else the PS5's, which didn't answer."""
    if refused in KEY_REFUSED:
        return KEY_REFUSED[refused]
    m = err.lower()
    if 'timed out' not in m and 'timeout' not in m:
        return 'console_rejected' if 'rejected' in m else 'download_failed'
    if reached == 'need_power':
        return 'power_timeout'
    return 'key_timeout' if late else 'console_timeout'


def pause(seconds):
    """Wait before the automatic second try, with the seconds left in job.wait for the page. True when Cancel ended it."""
    end = time.monotonic() + seconds
    try:
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return False
            with LOCK:
                JOB['wait'] = math.ceil(left)
            if CANCEL.wait(min(1.0, left)):
                return True
    finally:
        with LOCK:
            JOB['wait'] = None


def job_download():
    c = STATE['console']
    if not STATE['paired']:
        raise Fail('not_paired')
    if not G.reachable():
        raise Fail('garlic_unreachable')
    sess = console_dir() / 'sessions' / time.strftime('%Y%m%d-%H%M%S'); lib = sess / 'lib'; lib.mkdir(parents=True)
    keys = relay()
    opts = {'oracleHost': '127.0.0.1', 'oraclePort': keys.port, 'clientHost': c['host'], 'output': str(lib), 'interface': '',
            'hostId': c['hostId'], 'systemVersion': c['firmware'], 'hardware': 0, 'approvalPrefixPath': str(prefix_path()),
            'waitForSelection': True, 'titles': GTA_TITLES}
    for first in (True, False):
        t0 = time.monotonic()
        r = download_try(opts)
        if not r['err']:
            break
        tried = keys.derivations.since(t0)
        late = [d for d in tried if d.late(KEY_WAIT)]
        for d in late:                          # the worker stopped waiting for these: say so in the details
            line = d.report_unanswered()
            if line:
                log(line)
        refused = why = None; detail = r['err']
        for d in tried:                         # a key request GarlicSaves refused: the detail says why, not the closed connection it led to
            w = d.reason()
            if w in KEY_REFUSED:
                refused, why, detail = d, w, d.summary()
                break
        code = download_error(r['err'], r['stage'], late, why)
        # before the power prompt with nothing downloaded yet, one more try: 5 s later when the key service was too slow,
        # once the rate limit is over when GarlicSaves limited the requests
        again = first and r['stage'] == 'connecting' and not (r['files'] or r['entries'])
        if again and code == 'key_timeout':
            log('The key service was slow, trying again')
            stage('key_retry')
            wait = KEY_RETRY_WAIT
        elif again and code == 'key_rate_limited':
            left = refused.limit_left(KEY_LIMIT_WAIT)
            wait = min(KEY_LIMIT_WAIT if left is None else left, KEY_LIMIT_MAX)
            log('GarlicSaves is limiting requests, trying again in %d s' % math.ceil(wait))
            stage('key_rate_wait')
        else:
            raise Fail(code, detail)
        if pause(wait):
            raise Fail(code, detail)
    entries, users, chosen = r['entries'], r['users'], r['chosen']
    if r['nosave'] or not entries:
        raise Fail('no_gta_save')
    e = next((x for x in entries if chosen and x['owner'].lower() == chosen.lower()), entries[0]); owner = e['owner']
    uname = next((u['name'] for u in users if u['id'].lower() == owner.lower()), 'user')
    save_dir = lib / 'Saves' / owner / e['title']
    imgs = sorted(save_dir.glob('sdimg_*'))
    if not imgs:
        raise Fail('download_failed', 'no files')
    (sess / 'orig').mkdir()
    for f in imgs:
        shutil.copyfile(f, sess / 'orig' / f.name)
    stage('decrypting')
    slots, skipped = [], []
    for f in imgs:
        if SLOT_RE.fullmatch(f.name):
            try:
                slots.append(load_slot(sess, f.name, f))
            except Unreadable as u:             # left as it is: the PS5 gets its own copy back unchanged
                log('%s: left out, it can\'t be read (%s)' % (f.name, u))
                skipped.append(skipped_slot(sess, f.name, u.why))
    if not slots:
        if skipped:
            raise Fail('decrypt_bad' if any(s['why'] == 'damaged' for s in skipped) else 'save_layout_changed',
                       ', '.join(s['file'] for s in skipped))
        raise Fail('no_story_slot')
    slots.sort(key=lambda s: s['file'])
    with LOCK:
        STATE.update(session=str(sess), user={'id': owner, 'name': uname}, entryId=e['id'], title=e['title'], slots=slots, skipped=skipped,
                     users=ps5_users(lib), readyToUpload=False, fileCount=len(imgs))
    stage('ready')


def choose_account(owner):
    """Called when the user picks a PS5 account during a download; unblocks job_download."""
    with LOCK:
        if JOB['status'] != 'running' or JOB['stage'] != 'choose_account':
            raise Fail('bad_request')
        if str(owner or '').lower() not in [str(a['id']).lower() for a in JOB['accounts'] or []]:
            raise Fail('bad_request')
        CHOICE['owner'] = str(owner)
    CHOICE['event'].set()


def job_patch(slot_file, edits):
    """edits: what savedit.apply takes (money, ammo, stats, guns, completion, world, raw), always applied to the original slot."""
    sess = Path(STATE['session'])
    slot = slot_by_file(slot_file)
    if not slot:
        raise Fail('bad_slot')
    stage('patching')
    src = Path(slot['dir']) / slot['inner']
    try:
        data, plog = savedit.apply(src.read_bytes(), edits)
    except money.SaveError as e:
        raise Fail('save_' + str(e))
    if not plog:
        raise Fail('no_change')
    mod = sess / 'mod' / Path(slot['dir']).name
    if mod.exists():
        shutil.rmtree(mod)
    shutil.copytree(slot['dir'], mod)
    (mod / slot['inner']).write_bytes(data)
    z = sess / 'mod' / (slot['file'] + '.zip')
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, ds, fs in os.walk(mod):
            ds.sort()
            for f in sorted(fs):
                fp = Path(root) / f
                zf.write(fp, fp.relative_to(mod.parent).as_posix())
    stage('encrypting')
    enc = sess / 'enc'; enc.mkdir(exist_ok=True)
    out = G.encrypt(str(z), slot['account'], str(enc / slot['file']), on_status=lambda s: log('encrypt: ' + s))
    stage('importing')
    run_tool(['poc.dt_local_saves', 'import', str(sess / 'lib'), str(STATE['entryId']), slot['file'], out])
    (sess / 'mod' / (slot['file'] + '.edits.json')).write_text(json.dumps(edits), 'utf-8')
    with LOCK:
        slot['modified'] = True; slot['applied'] = edits; slot['changes'] = summarize(plog)
        STATE['readyToUpload'] = True
    stage('ready_to_upload')


def job_restore():
    """Put the original saves back into the transfer library (then send as usual to restore)."""
    sess = Path(STATE['session']); stage('importing')
    for s in STATE['slots']:
        if s['modified']:
            run_tool(['poc.dt_local_saves', 'import', str(sess / 'lib'), str(STATE['entryId']), s['file'], str(sess / 'orig' / s['file'])])
            (sess / 'mod' / (s['file'] + '.edits.json')).unlink(missing_ok=True)
            with LOCK:
                s['modified'] = False; s['changes'] = []; s['applied'] = None
    with LOCK:
        STATE['readyToUpload'] = True
    stage('ready_to_upload')


def upload_network_hint(line):
    """job.hint for a [network] line of the transfer code: a PS5 asked for IPv6 data (issue #7) and the adapter carrying
    its connection has no link-local IPv6 address. The upload keeps waiting, so the player can turn IPv6 on and pick Save
    Garage on the PS5 again; the next connection clears the hint."""
    if not line.startswith('[network] '):
        return None
    try:
        event = json.loads(line[len('[network] '):])
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get('issue') != 'local_ipv6':
        return None
    adapter = event.get('adapter')
    return {'code': 'local_ipv6', 'adapter': adapter if isinstance(adapter, str) else '',
            'platform': sys.platform}


def job_upload(target=None):
    """Send the session's saves back to the PS5: to the account they came from, or, with target (another user on this PS5,
    an 8-hex user ID), as that account's saves, signed for it first (copy_to_user)."""
    c = STATE['console']; sess = Path(STATE['session']); lib = sess / 'lib'; up = sess / 'upload'; up.mkdir(exist_ok=True)
    stage('preparing')
    user, entry_id = STATE['user'], STATE['entryId']
    if target and target.lower() != str(user['id']).lower():
        entry_id, user = copy_to_user(sess, lib, entry_id, target.lower())
    run_tool(['poc.dt_metadata', '--output', str(up / 'generated-metadata.db'), '--user-id', user['id'], '--assets', str(lib),
              '--user-name', user['name'], '--manifest-output', str(up / 'generated-upload-manifest.json'),
              '--source', str(lib / 'Transfer-Metadata' / 'metadata.db'), '--entry-id', str(entry_id)])
    total = len(list((lib / 'Saves' / user['id'] / STATE['title']).glob('sdimg_*')))
    env = {'DT_METADATA': str(up / 'generated-metadata.db'), 'DT_ASSETS': str(lib), 'DT_MANIFEST': str(up / 'generated-upload-manifest.json'),
           'DT_UPLOAD_KIND': 'save', 'DT_LOG': str(up / 'dt-source.log'), 'DT_PAIRING_PREFIX': str(prefix_path()), 'DT_EXPECTED_HOST_ID': c['hostId'],
           'DT_AUTO_POWER': '1', 'DT_PORT': '1004', 'DT_DATA_PORT': '1005', 'DT_DISCOVERY_PORT': '1006', "DT_HOST_NAME": "Save Garage",
           'DT_ORACLE_HOST': '127.0.0.1', 'DT_ORACLE_PORT': str(relay().port), 'DT_SYSTEM_VERSION': c['firmware']}
    if MAC:     # a Mac on Wi-Fi often misses the console's search broadcast, so the source announces itself
        env['DT_CONSOLE_IP'] = c['host']
    t0 = time.monotonic()
    p = spawn(['poc.dt_source'], env=env)
    stage('waiting_console')
    files = 0; finished = False
    for line in p.stdout:
        line = line.rstrip(); low = line.lower()
        hint = upload_network_hint(line)
        if hint:
            stage('waiting_console', hint=hint)
            log('The console connection needs a local IPv6 address. Waiting for reconnection.')
            continue
        if 'srch' in low or not line:
            continue
        if 'session ended' in low or 'connection ended' in low or 'traceback' in low or 'error' in low:
            refused_key_request(t0)             # a channel closed because GarlicSaves turned its key request down
        if 'could not read windows network adapters' in low:
            raise Fail('adapter_query_failed', line)
        if 'psutil package is missing' in low:
            raise Fail('tool_failed', line)     # a source checkout that predates the psutil requirement
        if '[tcp] connection from' in low:
            stage('console_connected', hint=None)
        elif 'gfp5 id=' in low and files == 0:
            stage('transferring')
        elif 'gfp5 file complete' in low:
            files += 1
            with LOCK:
                JOB['progress'] = {'files': files, 'total': total}
        elif 'response complete cmd=0xb3' in low:
            finished = True
        elif 'response complete cmd=0x94' in low:
            if finished and files:
                break
            if files == 0:
                # the console read the list and left: usually a save with the same name is still on it
                with LOCK:
                    JOB['hint'] = 'console_has_save'
                stage('waiting_console')
        elif 'address already in use' in low or 'winerror 10048' in low:
            raise Fail('port_in_use', line)
        elif 'traceback' in low or 'error' in low:
            log(line)
    if not (finished and files):
        refused_key_request(t0)
        raise Fail('upload_failed', 'process ended')
    time.sleep(3)
    (sess / 'uploaded').touch()                 # a download that was sent back is not picked up again
    stage('uploaded')
    with LOCK:
        STATE['readyToUpload'] = False


# ---------------- HTTP ----------------
def same_subnet(host):
    """Whether this computer and the console share a /24. If not, downloads work but the console can't find the computer when sending back."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as r:
            r.connect((host, 1006)); mine = r.getsockname()[0]
        return mine.rsplit('.', 1)[0] == host.rsplit('.', 1)[0]
    except OSError:
        return None


def public_state():
    with LOCK:
        s = json.loads(json.dumps({k: v for k, v in STATE.items()}))
        for sl in s['slots']:
            sl.pop('dir', None); sl.pop('account', None)
            for it in sl['items']:
                it.pop('type', None)
        s.pop('session', None)
        s['hasSession'] = bool(STATE['session'])
        if s['console']:
            s['console']['sameSubnet'] = same_subnet(s['console']['host'])
        s['job'] = json.loads(json.dumps(JOB)); s['job']['log'] = s['job']['log'][-40:]
        s['titles'] = GTA_TITLES
        s['canQuit'] = DESKTOP
        s['version'] = VERSION
        s['update'] = update_state()
        s['garlic'] = garlic_state()
        return s


def update_state():
    """state.update for the page (docs/API.md): the updater's status, plus whether Restart now can be used."""
    u = UPDATER.public()
    u['canRestart'] = u['status'] == 'ready' and JOB['status'] != 'running' and not RESTART.is_set()
    u['restarting'] = RESTART.is_set()
    return u


class H(BaseHTTPRequestHandler):
    server_version = "SaveGarage"

    def log_message(self, *a):
        pass

    def _send(self, code, obj=None, raw=None, ctype='application/json; charset=utf-8'):
        body = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(body)

    def _local_only(self):
        try:                                    # only clients from SAVEGARAGE_ALLOW networks
            client = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        if not any(client in net for net in ALLOW_NETS):
            return False
        host = (self.headers.get('Host') or '').split(':')[0]
        if host not in OK_HOSTS:
            return False
        o = self.headers.get('Origin')
        return not o or re.fullmatch(r'https?://(%s)(:\d+)?' % '|'.join(re.escape(h) for h in OK_HOSTS), o) is not None

    def do_GET(self):
        if not self._local_only():
            return self._send(403, {'error': 'forbidden'})
        url = urlsplit(self.path)
        path = url.path
        if path == '/api/state':
            LAST_SEEN['t'] = time.time()
            return self._send(200, public_state())
        if path == '/api/savedata':                     # browse any section of the save
            q = parse_qs(url.query)
            slot = slot_by_file((q.get('file') or [''])[0]) if STATE['session'] else None
            if not slot:
                return self._send(404, {'error': 'no_slot'})
            try:
                import savebrowse
                b = slot_bytes(slot)
                if not q.get('section'):
                    return self._send(200, {'sections': savebrowse.sections(b)})
                p = json.loads((q.get('path') or ['[]'])[0])
                if not isinstance(p, list) or not all(isinstance(x, (str, int)) for x in p):
                    raise ValueError('bad path')
                return self._send(200, savebrowse.node(b, int(q['section'][0], 16), p, int((q.get('offset') or ['0'])[0]), 200))
            except Exception as e:
                return self._send(400, {'error': 'bad_request', 'detail': repr(e)[:300]})
        if path == '/api/world':                        # time of day, health and armour, the characters, levels, capacities and the map
            slot = slot_by_file((parse_qs(url.query).get('file') or [''])[0]) if STATE['session'] else None
            if not slot:
                return self._send(404, {'error': 'no_slot'})
            try:
                import world, player, levels, growth, fog
                b = slot_bytes(slot)
                out = world.read(b)
            except Exception as e:
                return self._send(500, {'error': 'internal', 'detail': repr(e)[:300]})
            out['errors'] = {}
            for key, mod in (('player', player), ('levels', levels), ('growth', growth), ('fog', fog)):   # each on its own: one that can't be read leaves the rest working
                try:
                    out[key] = mod.read(b)
                except Exception as e:
                    out[key], out['errors'][key] = None, repr(e)[:200]
            return self._send(200, out)
        if path == '/api/completion':                   # the Completion tab: stunts and their counters
            slot = slot_by_file((parse_qs(url.query).get('file') or [''])[0]) if STATE['session'] else None
            if not slot:
                return self._send(404, {'error': 'no_slot'})
            try:
                b = slot_bytes(slot)
            except Exception as e:
                return self._send(500, {'error': 'internal', 'detail': repr(e)[:300]})
            # each part on its own: one a save can't show yet (an early save lacks some records) leaves the rest working
            out, errors = {}, {}
            for key, fn in completion_readers(b):
                try:
                    out[key] = fn()
                except Exception as e:
                    out[key], errors[key] = None, repr(e)[:200]
            out['errors'] = errors
            return self._send(200, out)
        if path in ('/api/slot', '/api/stats'):       # detail data for the editor
            slot = slot_by_file((parse_qs(url.query).get('file') or [''])[0]) if STATE['session'] else None
            if not slot:
                return self._send(404, {'error': 'no_slot'})
            try:
                if path == '/api/slot':
                    return self._send(200, slot_detail(slot))
                return self._send(200, raw=slot_stats(slot))
            except Exception as e:
                return self._send(500, {'error': 'internal', 'detail': repr(e)[:300]})
        base, rel = UI, path.lstrip('/')
        f = (base / (rel or 'index.html')).resolve()
        if base.resolve() not in f.parents or not f.is_file():
            return self._send(404, {'error': 'not_found'})
        self._send(200, raw=f.read_bytes(), ctype=(mimetypes.guess_type(str(f))[0] or 'application/octet-stream') + ('; charset=utf-8' if f.suffix in ('.html', '.js', '.css') else ''))

    def do_POST(self):
        if not self._local_only():
            return self._send(403, {'error': 'forbidden'})
        try:
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}') if n else {}
            path = self.path.split('?')[0]
            if path == '/api/discover':
                cons = discover()
                return self._send(200, {'consoles': cons})
            if path == '/api/console':
                c = probe_host(body['host'])
                if not c:
                    raise Fail('console_not_found')
                with LOCK:
                    STATE['console'] = {'host': c['host'], 'name': c['name'], 'hostId': c['hostId'], 'firmware': c['firmware']}
                    STATE.update(session=None, slots=[], skipped=[], users=[], readyToUpload=False, user=None, entryId=None)
                    refresh_paired()
                    try:
                        restore_session()
                    except Exception as e:
                        log('restore skipped: %r' % e)
                    (DATA / 'last_console.json').write_text(json.dumps({'host': c['host']}), 'utf-8')
                return self._send(200, public_state())
            if path == '/api/network':
                ok = G.reachable()
                with LOCK:
                    STATE['network'] = {'ok': ok, 'proxy': bool(G.proxy)}
                return self._send(200, STATE['network'])
            if path == '/api/cancel':
                CANCEL.set(); kill_proc()
                return self._send(200, {'ok': True})
            if path == '/api/quit':
                if JOB['status'] == 'running' and JOB['stage'] in ('console_connected', 'transferring'):
                    raise Fail('busy')
                self._send(200, {'ok': True})
                threading.Thread(target=lambda: (time.sleep(0.3), kill_proc(), os._exit(0)), daemon=True).start()
                return
            if path == '/api/update/check':            # check GitHub for a new version now
                UPDATER.check_now()
                return self._send(200, update_state())
            if path == '/api/update/settings':         # {"auto": false} turns automatic updates off
                auto = body.get('auto')
                if not isinstance(auto, bool):
                    raise ValueError('auto must be true or false')
                save_config(autoUpdate=auto)
                UPDATER.set_auto(auto)
                return self._send(200, update_state())
            if path == '/api/update/restart':          # start again, so the staged update installs
                with LOCK:
                    if JOB['status'] == 'running' or RESTART.is_set():
                        raise Fail('busy')
                    if not UPDATER.ready() or not SRV['s']:
                        raise Fail('no_update')
                    RESTART.set()
                self._send(200, {'ok': True})
                threading.Thread(target=lambda: (time.sleep(0.3), SRV['s'].shutdown()), daemon=True).start()
                return
            if path == '/api/signin':                  # sign in to GarlicSaves (or go on with the sign-in under way)
                signin_start()
                return self._send(200, garlic_state())
            if path == '/api/signin/cancel':
                signin_cancel()
                return self._send(200, garlic_state())
            if path == '/api/signout':                 # forget the GarlicSaves sign-in on this computer
                sign_out()
                return self._send(200, garlic_state())
            if not STATE['console']:
                raise Fail('no_console')
            if path in NEEDS_SIGNIN and not G.key:
                raise Fail('not_signed_in')
            if path == '/api/pair':
                return self._send(200, {'job': start_job('pair', job_pair)})
            if path == '/api/download':
                return self._send(200, {'job': start_job('download', job_download)})
            if path == '/api/choose-account':
                choose_account(body.get('owner'))
                return self._send(200, {'ok': True})
            if not STATE['session']:
                raise Fail('no_session')
            if path == '/api/stunt-edits':             # stat edits that mark whole stunt types done
                slot = slot_by_file(body.get('file') or '') if STATE['session'] else None
                if not slot:
                    raise Fail('no_slot')
                ids = [i for i in (body.get('groups') or []) if i in {g[0] for g in savedit.STUNT_GROUPS}]
                return self._send(200, {'edits': savedit.stunt_edits(savedit.section(slot_bytes(slot), money.SEC_STAT), ids)})
            if path == '/api/preview':                 # the 100% checklist after the edits picked so far (nothing is written)
                slot = slot_by_file(body.get('file') or '')
                if not slot:
                    raise Fail('no_slot')
                return self._send(200, completion_preview(slot, body))
            if path == '/api/patch':                   # every edit for one save in one request
                slot = body['slot']
                edits = {'money': body.get('money', body.get('changes')) or [], 'ammo': body.get('ammo') or [], 'stats': body.get('stats') or []}
                if not all(isinstance(v, list) for v in edits.values()):
                    raise ValueError('edits must be lists')
                if any(isinstance(c, dict) and not isinstance(c.get('stacks', False), bool) for c in edits['money']):
                    raise ValueError('stacks must be true or false')    # the bank's opt-in to its extra 85,000 stacks
                if body.get('completion'):
                    c = body['completion']
                    if not isinstance(c, dict):
                        raise ValueError('completion must be an object')
                    edits['completion'] = {k: c[k] for k in savedit.COMPLETION_KEYS if c.get(k)}
                if body.get('guns'):
                    if not isinstance(body['guns'], dict):
                        raise ValueError('guns must be an object')
                    edits['guns'] = body['guns']
                if body.get('raw'):
                    if not isinstance(body['raw'], list):
                        raise ValueError('raw must be a list')
                    edits['raw'] = body['raw']
                if body.get('world'):
                    if not isinstance(body['world'], dict):
                        raise ValueError('world must be an object')
                    edits['world'] = {k: body['world'][k] for k in WORLD_KEYS if body['world'].get(k) is not None}
                return self._send(200, {'job': start_job('patch', lambda: job_patch(slot, edits))})
            if path == '/api/restore':
                return self._send(200, {'job': start_job('restore', job_restore)})
            if path == '/api/upload':
                to = body.get('to') if isinstance(body, dict) else None
                if to is not None:              # another account on this PS5: the copy itself is the change
                    if not isinstance(to, str) or not re.fullmatch(r'[0-9a-fA-F]{8}', to) or \
                            to.lower() not in [u['id'] for u in STATE.get('users') or []]:
                        raise Fail('bad_request')
                    if not STATE['session'] or to.lower() == str((STATE['user'] or {}).get('id', '')).lower():
                        to = None
                if not to and not STATE['readyToUpload']:
                    raise Fail('nothing_to_upload')
                return self._send(200, {'job': start_job('upload', lambda: job_upload(to))})
            self._send(404, {'error': 'not_found'})
        except Fail as e:
            self._send(409, {'error': e.code, 'detail': str(e.detail)})
        except (KeyError, ValueError) as e:
            self._send(400, {'error': 'bad_request', 'detail': repr(e)})
        except Exception as e:
            self._send(500, {'error': 'internal', 'detail': repr(e)})


def already_running():
    import urllib.request
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open('http://127.0.0.1:%d/api/state' % PORT, timeout=2) as r:
            return 'titles' in json.loads(r.read().decode('utf-8'))
    except Exception:
        return False


def idle_watch():
    """Exit when the page has been closed for 10 minutes and no job is running, so nothing lingers in the background."""
    while True:
        time.sleep(30)
        if JOB['status'] != 'running' and time.time() - LAST_SEEN['t'] > 600:
            kill_proc(); os._exit(0)


def main():
    import webbrowser
    url = 'http://%s:%d' % (BIND if BIND not in ('', '0.0.0.0') else '127.0.0.1', PORT)
    open_ui = (DESKTOP or '--open' in sys.argv) and not os.environ.get('SAVEGARAGE_NO_BROWSER')
    if already_running():                       # already running: just open the page again
        if open_ui:
            webbrowser.open(url)
        return
    DATA.mkdir(parents=True, exist_ok=True)
    load_signin()                               # and a config.json holding a sign-in that others could read is made private
    srv = ThreadingHTTPServer((BIND, PORT), H)
    SRV['s'] = srv
    print('Save Garage running: ' + url, flush=True)
    if DEV_KEY:
        print('Using the worker key in %s (development and tests only).' % garlic.DEV_KEY_ENV, flush=True)
    if DESKTOP and (MAC or os.name == 'nt'):       # desktop builds: quit when the page has been gone a while
        threading.Thread(target=idle_watch, daemon=True).start()
    if open_ui:
        webbrowser.open(url)
    UPDATER.start()
    srv.serve_forever()
    if RESTART.is_set():                           # Restart now: free the port, then start again (installs the update)
        srv.server_close()
        kill_proc()
        print('Save Garage is restarting to install %s' % (UPDATER.public().get('latest') or 'the update'), flush=True)
        updater.restart_process()


if __name__ == '__main__':
    main()
