#!/usr/bin/env python3
"""Drive the repo's own PCSX2 (tools/pcsx2, private data dir, PINE on slot 28111).

PINE (PCSX2's IPC, unix socket $TMPDIR/pcsx2.sock.<slot>): read/write EE memory, save/load states, status.
A savestate (.p2s, a zip) carries Screenshot.png, which is how we take screenshots.

usage:
  pcsx2.py boot ISO [--secs 60] [--shots 10] --out DIR    boot, save a shot every --shots seconds, quit
  pcsx2.py status | read ADDR [N] | write32 ADDR VAL | save SLOT | load SLOT | shot OUT.png | quit
library: Emu(iso).start(); emu.read(addr, n); emu.shot(path); emu.stop()
"""
import io, os, socket, struct, subprocess, sys, time, zipfile, glob, signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'tools', 'pcsx2', 'PCSX2-v2.8.2.app', 'Contents', 'MacOS', 'PCSX2')
DATA = os.path.join(ROOT, 'tools', 'pcsx2', 'data')
SSTATES = os.path.join(DATA, 'PCSX2', 'sstates')
SLOT = 28111
SHOT_SLOT = 9     # savestate slot used for screenshots


def sock_path():
    return os.path.join(os.environ.get('TMPDIR', '/tmp'), f'pcsx2.sock.{SLOT}')


class Pine:
    def __init__(self, timeout=5.0):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); self.s.settimeout(timeout)
        self.s.connect(sock_path())

    def call(self, op, args=b''):
        msg = struct.pack('<IB', 5 + len(args), op) + args
        self.s.sendall(msg)
        hdr = self._recv(4); n = struct.unpack('<I', hdr)[0]
        body = self._recv(n - 4)
        if body[0] != 0: raise RuntimeError(f'PINE op {op:#x} failed')
        return body[1:]

    def _recv(self, n):
        b = b''
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c: raise ConnectionError('PINE closed')
            b += c
        return b

    def read32(self, a): return struct.unpack('<I', self.call(2, struct.pack('<I', a)))[0]
    def read8(self, a): return self.call(0, struct.pack('<I', a))[0]
    def write8(self, a, v): self.call(4, struct.pack('<IB', a, v))
    def write32(self, a, v): self.call(6, struct.pack('<II', a, v & 0xFFFFFFFF))
    def write16(self, a, v): self.call(5, struct.pack('<IH', a, v & 0xFFFF))
    def poke(self, a, v, size=2, tries=20):
        """Write and read back until it sticks. PINE writes made while a savestate is being written can be
        dropped (the movie-skip flag was lost under --shot-every). Not for mailboxes the game clears."""
        w, r = (self.write16, lambda: struct.unpack('<H', self.read(a & ~3, 4)[a & 3:(a & 3) + 2])[0]) if size == 2 \
            else (self.write32, lambda: self.read32(a))
        for _ in range(tries):
            w(a, v)
            if r() == v & (0xFFFF if size == 2 else 0xFFFFFFFF): return
            time.sleep(0.25)
        raise RuntimeError(f'PINE write to {a:#x} did not stick')
    def read(self, a, n):
        out = bytearray()
        for k in range(0, n, 4): out += struct.pack('<I', self.read32(a + k))
        return bytes(out[:n])
    def save(self, slot): self.call(9, bytes([slot]))
    def load(self, slot): self.call(0xA, bytes([slot]))
    def status(self): return struct.unpack('<I', self.call(0xF))[0]   # 0 running 1 paused 2 shutdown
    def title(self):
        b = self.call(0xB); n = struct.unpack('<I', b[:4])[0]; return b[4:4 + n].rstrip(b'\0').decode('utf-8', 'replace')


def latest_state(slot):
    fs = glob.glob(os.path.join(SSTATES, f'*.{slot:02d}.p2s'))
    return max(fs, key=os.path.getmtime) if fs else None


class Emu:
    def __init__(self, iso, log=None):
        self.iso = os.path.abspath(iso); self.proc = None
        self.log = log or os.path.join(ROOT, 'work', 'pcsx2_run.log')

    def start(self, wait=60):
        if os.path.exists(sock_path()):
            try: Pine(1).status(); raise SystemExit('another PCSX2 already serves our PINE slot')
            except (ConnectionError, OSError): os.remove(sock_path())
        self.proc = subprocess.Popen([APP, '-datapath', DATA, '-batch', '-fastboot', '--', self.iso],
                                     stdout=open(self.log, 'w'), stderr=subprocess.STDOUT)
        print(f'PCSX2 pid {self.proc.pid}', flush=True)
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                self.pine = Pine()
                if self.pine.status() == 0:
                    self.pine.title(); return self
            except (OSError, ConnectionError, RuntimeError):
                pass
            time.sleep(0.5)
            if self.proc.poll() is not None: raise SystemExit(f'PCSX2 exited ({self.proc.returncode}), see {self.log}')
        raise SystemExit('PINE never came up')

    def shot(self, out):
        before = latest_state(SHOT_SLOT); bt = os.path.getmtime(before) if before else 0
        self.pine.save(SHOT_SLOT)
        t0 = time.time()
        while time.time() - t0 < 20:
            p = latest_state(SHOT_SLOT)
            if p and os.path.getmtime(p) > bt:
                s0 = -1
                while os.path.getsize(p) != s0: s0 = os.path.getsize(p); time.sleep(0.4)
                try:
                    with zipfile.ZipFile(p) as z:
                        png = z.read('Screenshot.png')     # raises on a bad CRC
                    open(out, 'wb').write(png); return out
                except (zipfile.BadZipFile, KeyError, OSError, EOFError): pass
            time.sleep(0.3)
        raise RuntimeError('no savestate screenshot')

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try: self.proc.wait(10)
            except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait()


def hold(pine, buttons):
    """Set the held buttons ('' releases all) via the debug-build pad mailbox."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import debugpatch
    mask = 0
    for b in filter(None, buttons.split('+')): mask |= debugpatch.BUTTONS[b]
    pine.write32(debugpatch.MAILBOX, mask)


def press(pine, buttons, secs=0.15):
    """Hold buttons via the debug-build pad mailbox (build.py --debug), then release."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import debugpatch
    mask = 0
    for b in buttons.split('+'): mask |= debugpatch.BUTTONS[b]
    pine.write32(debugpatch.MAILBOX, mask); time.sleep(secs); pine.write32(debugpatch.MAILBOX, 0)


REGION, AREA = 0x795F9A, 0x795F98      # party map region / area (PartyMapRegionSet @ 0x145c68)


def warp(pine, region):
    """Set the party's map region (and its area, from tools/debug/regions.tsv). Do it at the title screen,
    before New Game: the boot-time PlayerWorkInit has set 0x819 (shrine, opening) by then."""
    tsv = os.path.join(ROOT, 'tools', 'debug', 'regions.tsv')
    area = {int(l.split('\t')[0], 16): int(l.split('\t')[1]) for l in open(tsv, encoding='utf-8').read().splitlines()[1:]}
    if region not in area: raise SystemExit(f'region {region:#x} not in {tsv}')
    pine.poke(REGION, region); pine.poke(AREA, area[region])
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import debugpatch
    pine.poke(debugpatch.SKIP, 1)             # skip the opening movie after New Game


def battle(pine, formation=0):
    """Force a battle with formation N of the current world's encounter table (field, free roam; debug build)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import debugpatch
    pine.write16(debugpatch.ENC, formation + 1)


def window(pine, kind, arg=0):
    """Open a DLL screen via EvWindowCall(kind, arg) from the field (debug build; kinds in debugpatch.py)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import debugpatch
    pine.write16(debugpatch.WIN_ARG, arg); pine.write16(debugpatch.WIN, kind + 1)


EV_MODULES = 0x7932E8    # loaded event modules: node+0 next, +8 id, +0x2c string ptrs, +0x30 class count, +0x34 classes
                         # class: 16 B (name idx, ?, method count, methods); method: 12 B (name idx, ?, entry)


def _cstr(pine, a):
    b = pine.read(a, 64)
    return b.split(b'\0')[0].decode('cp932', 'replace')


def event_lookup(pine, cls, method):
    """-> (class string ptr, method string ptr) in the loaded event modules, or SystemExit with what exists."""
    node = pine.read32(EV_MODULES)
    while node:
        w = struct.unpack('<16I', pine.read(node, 64))
        strtab, ncls, table = w[11], w[12], w[13]
        for c in range(ncls):
            name_i, _, nmeth, meths = struct.unpack('<4I', pine.read(table + 16 * c, 16))
            cp = pine.read32(strtab + 4 * name_i)
            if _cstr(pine, cp) != cls: continue
            names = []
            for m in range(nmeth):
                mi = pine.read32(meths + 12 * m); mp = pine.read32(strtab + 4 * mi)
                names.append(_cstr(pine, mp))
                if names[-1] == method: return cp, mp
            raise SystemExit(f'{cls} has no method {method!r}: {" / ".join(names)}')
        node = w[0]
    raise SystemExit(f'class {cls} is not loaded (it lives in another map\'s event module)')


def event(pine, cls, method):
    """Start an event-script process at CLASS.METHOD (field; debug build; class must be in a loaded module)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import debugpatch
    cp, mp = event_lookup(pine, cls, method)
    pine.write32(debugpatch.EV_METHOD, mp); pine.write32(debugpatch.EV_CLASS, cp)


def call(pine, fn, *args):
    """Call FN(args...) from the field update (debug build). FN: address or a name from work/symbols.txt."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import debugpatch
    try: a = int(fn, 0)
    except ValueError:
        syms = dict(l.split() for l in open(os.path.join(ROOT, 'work', 'symbols.txt')) if len(l.split()) == 2)
        a = int(syms[fn], 16)
    for k, v in enumerate((list(args) + [0] * 4)[:4]): pine.write32(debugpatch.CALL_ARGS + 4 * k, v)
    pine.write32(debugpatch.CALL_FN, a)


PARTY_FLAGS = 0x793600               # PartyFlagSet @ 0x1447d0: flag n = bit n&31 of the u32 at +(n>>5)*4


def flag(pine, n, on=True):
    """Set or clear party (story) flag n."""
    a = PARTY_FLAGS + (n >> 5) * 4; v = pine.read32(a); bit = 1 << (n & 31)
    pine.poke(a, v | bit if on else v & ~bit, 4)


def run_route(emu, route, out, shot_every=0):
    """Route lines: wait S | press BTN[+BTN] [S] | repeat N press BTN [gap S] | shot NAME | save SLOT |
    load SLOT | poke16 ADDR VAL | warp REGION (title screen, before New Game) | battle [FORMATION] (field) |
    window KIND [ARG] (field: EvWindowCall) | flag N [N...] | unflag N [N...] (party/story flags) |
    event CLASS METHOD (field: start an event-script method, e.g. `event ev0503 デバッグ`) |
    call FN [A0 A1 A2 A3] (field: call an engine function by name or address, e.g. `call PartyItemAdd 718 5`) |
    every S (periodic shots from here on; 0 = off) | # comment
    Periodic shots during boot can break the movie skip (savestates written every second around New Game):
    routes that warp turn them on with `every` after arriving instead of using --shot-every."""
    os.makedirs(out, exist_ok=True); t0 = time.time(); nxt = 0.0
    def shot(name=None):
        p = os.path.join(out, name + '.png' if name else f'f{int((time.time() - t0) * 60):06d}.png')
        try: emu.shot(p); print(p, flush=True)
        except RuntimeError as ex: print('shot failed', p, ex, flush=True)

    def tick():
        nonlocal nxt
        if shot_every and time.time() >= nxt:
            nxt = time.time() + shot_every; shot()
    for line in open(route, encoding='utf-8'):
        w = line.split('#')[0].split()
        if not w: continue
        if w[0] == 'wait':
            end = time.time() + float(w[1])
            while time.time() < end:
                tick(); time.sleep(min(0.25, max(0, end - time.time())))
        elif w[0] == 'press':
            # with --shot-every, a savestate write can stall the game through a 0.15 s press (New Game lost,
            # the title idled into the attract movie): hold longer
            secs = float(w[2]) if len(w) > 2 else (0.4 if shot_every else 0.15)
            if secs <= 0.5: press(emu.pine, w[1], secs)
            else:                                   # long hold: keep the shot ticker running
                hold(emu.pine, w[1]); end = time.time() + secs
                while time.time() < end: tick(); time.sleep(0.1)
                hold(emu.pine, '')
            time.sleep(0.1)
        elif w[0] == 'repeat':
            gap = float(w[w.index('gap') + 1]) if 'gap' in w else 0.5
            for _ in range(int(w[1])):
                press(emu.pine, w[3], 0.4 if shot_every else 0.15); end = time.time() + gap
                while time.time() < end: tick(); time.sleep(0.1)
        elif w[0] == 'shot': shot(w[1] if len(w) > 1 else None)
        elif w[0] == 'every': shot_every = float(w[1]); nxt = 0.0
        elif w[0] == 'save': emu.pine.save(int(w[1])); time.sleep(2)
        elif w[0] == 'load': emu.pine.load(int(w[1])); time.sleep(3)
        elif w[0] == 'poke16': emu.pine.poke(int(w[1], 0), int(w[2], 0))
        elif w[0] == 'warp': warp(emu.pine, int(w[1], 0))
        elif w[0] == 'battle': battle(emu.pine, int(w[1], 0) if len(w) > 1 else 0)
        elif w[0] in ('flag', 'unflag'):
            for n in w[1:]: flag(emu.pine, int(n, 0), w[0] == 'flag')
        elif w[0] == 'event': event(emu.pine, w[1], w[2])
        elif w[0] == 'call': call(emu.pine, w[1], *[int(x, 0) for x in w[2:]]); time.sleep(0.3)
        elif w[0] == 'window': window(emu.pine, int(w[1], 0), int(w[2], 0) if len(w) > 2 else 0)
        else: raise SystemExit(f'bad route line: {line!r}')


def main():
    a = sys.argv[1:]
    if a[0] in ('run', 'smoke'):
        out = a[a.index('--out') + 1]
        route = a[a.index('--route') + 1] if '--route' in a else os.path.join(ROOT, 'tools', 'routes', 'title.txt')
        every = float(a[a.index('--shot-every') + 1]) if '--shot-every' in a else 0
        e = Emu(a[1]).start()
        try: run_route(e, route, out, every)
        finally: e.stop()
        if a[0] == 'smoke':   # pass = the title menu frame is not black
            from PIL import Image, ImageStat
            p = os.path.join(out, 'title_menu.png')
            m = sum(ImageStat.Stat(Image.open(p).convert('L')).mean) if os.path.isfile(p) else 0
            print(f'smoke {"PASS" if m > 40 else "FAIL"}: title frame mean {m:.0f}')
            sys.exit(0 if m > 40 else 3)
        return
    if a[0] == 'boot':
        secs = int(a[a.index('--secs') + 1]) if '--secs' in a else 60
        every = int(a[a.index('--shots') + 1]) if '--shots' in a else 10
        out = a[a.index('--out') + 1]; os.makedirs(out, exist_ok=True)
        e = Emu(a[1]).start()
        try:
            print('title:', e.pine.title())
            t0 = time.time(); k = 0
            while time.time() - t0 < secs:
                time.sleep(every)
                k += 1
                print(e.shot(os.path.join(out, f'f{k * every * 60:06d}.png')), flush=True)
        finally:
            e.stop()
        return
    p = Pine()
    if a[0] == 'status': print(p.status(), p.title())
    elif a[0] == 'read': print(p.read(int(a[1], 0), int(a[2], 0) if len(a) > 2 else 4).hex())
    elif a[0] == 'write32': p.write32(int(a[1], 0), int(a[2], 0))
    elif a[0] == 'save': p.save(int(a[1]))
    elif a[0] == 'load': p.load(int(a[1]))


if __name__ == '__main__':
    main()
