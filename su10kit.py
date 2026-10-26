#!/usr/bin/env python3
"""
su10kit.py - SU10-Kit: build and read sample kits for the Yamaha SU10.
Python 3, standard library only. https://github.com/harmonicworks/su10-kit

  python3 su10kit.py build   kit.txt          WAV files in -> <kit>_header.syx + <kit>_data.syx out
  python3 su10kit.py build   folder/          every WAV in the folder on its own pad (alphabetical);
                                              writes folder/<folder>.txt first so you can edit it
  python3 su10kit.py info    dump.syx ...     list the pads in a dump
  python3 su10kit.py extract dump.syx ... [outfolder]   save every pad as a WAV
  python3 su10kit.py verify  dump.syx ...     decode and rebuild a dump, check it is byte-identical

A dump can be one file or several (header first), e.g.  info kit_header.syx kit_data.syx

KIT FILE (plain text, one pad per line, # starts a comment):
  channel 10                      optional machine settings stored in the dump
  devnum 1
  record Long mono
  base: some/dump/folder          optional: start from another dump's settings (default: SU10 after Init)
  pad 1: bell.wav    High   mono   one-shot
  pad 2: bass.wav    Long   mono   loop      vol 90
  pad 3: str.wav     High   stereo endloop 1.25  normalize -6  autotrim
Words per pad line, any order after the file name:
  High | Standard | Long | ExtraLong   quality grade (default High)
  mono | stereo                       default mono (stereo uses twice the memory)
  one-shot | loop | endloop SECONDS   endloop: play once, then repeat from SECONDS to the end
  vol N                               0-127 (default 100)
  trim A-B                            seconds in the WAV, e.g. trim 0.25-1.5
  autotrim                            cut silence at start and end (below -50 dB of the peak)
  normalize [dB]                      peak to that level, default -6 (e.g. normalize -3)
  pitch N                             transpose by N semitones (e.g. pitch -12)
WAV files: PCM 8/16/24/32-bit or 32-bit float, any sample rate, mono or stereo.

The SU10 bulk dump format is described in FORMAT.md.
"""
import sys, os, wave, array, struct, math, glob

# --- Sample rates per quality grade (pad entry byte 38), confirmed 2026-10-26 by recording
#     a 220 Hz tone at every grade. Nominal values: High and Long from the MSDS headers,
#     Standard and Extra long estimated from the measurements (the SU10's clock runs ~0.18% slow;
#     measured real rates: 40,027 / 29,067 / 20,014 / 14,533 Hz).
GRADE_RATES = {0: 40090, 1: 29120, 2: 20050, 3: 14560}
GRADE_NAMES = {0: 'High', 1: 'Standard', 2: 'Long', 3: 'ExtraLong'}

MEM_BASE = 0x20000

# ---------------------------------------------------------------- SysEx layer
def read_messages(paths):
    d = b''.join(open(p, 'rb').read() for p in paths)
    out, i = [], 0
    while i < len(d):
        j = d.index(0xF7, i)
        out.append(d[i:j + 1]); i = j + 1
    return out

def unpack78(b):
    out = bytearray()
    for i in range(0, len(b) - len(b) % 8, 8):
        h = b[i]
        for k in range(7):
            out.append(b[i + 1 + k] | (((h >> (6 - k)) & 1) << 7))
    return bytes(out)

def pack87(b):
    out = bytearray()
    for i in range(0, len(b), 7):
        g = b[i:i + 7]; h = 0
        for k, x in enumerate(g):
            h |= ((x >> 7) & 1) << (6 - k)
        out.append(h); out += bytes(x & 0x7F for x in g)
    return bytes(out)

def memory_blocks(paths):
    msgs = read_messages(paths)
    header, data = msgs[0], [m for m in msgs if len(m) > 15]
    if len(header) != 15 or len(data) != 1000:
        sys.exit(f"Unexpected dump: header {len(header)} bytes, {len(data)} data messages (expected 15 / 1000)")
    bad = 0
    for m in data:
        if (-(m[8] + sum(unpack78(m[9:-2])))) & 0x7F != m[-2]:
            bad += 1
    if bad:
        print(f"WARNING: {bad} messages have a wrong checksum")
    blocks = []
    for b in range(50):
        b7 = b''.join(m[9:-2] for m in data[b * 20:(b + 1) * 20])
        blocks.append(unpack78(b7)[:8192])
    return header, blocks

def rebuild(header, blocks):
    out = bytearray(header); idx = 1
    for blk in blocks:
        b7 = pack87(blk + b'\0' * 5); pos = 0
        for n in range(20):
            ln = 480 if n < 19 else 248
            d7 = b7[pos:pos + ln]; pos += ln
            ck = (-(idx + sum(unpack78(d7)))) & 0x7F
            cnt = ln + 1
            out += bytes([0xF0, 0x43, header[2], 0x7F, 0x36, 0x00, cnt >> 7, cnt & 0x7F, idx & 0x7F]) + d7 + bytes([ck, 0xF7])
            idx += 1
    return bytes(out)

# ---------------------------------------------------------------- pads + audio
def pad_table(blocks):
    t = blocks[0]; pads = []
    for i in range(48):
        e = t[i * 42:(i + 1) * 42]
        pads.append(dict(pad=i + 1,
                         bank='ABCD'[i // 12], num=i % 12 + 1,
                         start=int.from_bytes(e[0:4], 'big'),
                         nbytes=int.from_bytes(e[12:16], 'big'),
                         nsamp=int.from_bytes(e[26:30], 'big'),
                         flag=e[30], volume=e[32], channels=e[34], note=e[36], grade=e[38], raw=e))
    return pads

IMA = [7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,
       157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,
       1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,
       10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767]
IMA_ADJ = [-1, -1, -1, -1, 2, 4, 6, 8]

def ima_nibbles(nibbles):
    out = array.array('h'); acc = 0; idx = 0
    for v in nibbles:
        if True:
            st = IMA[idx]; d = st >> 3
            if v & 4: d += st
            if v & 2: d += st >> 1
            if v & 1: d += st >> 2
            acc = acc - d if v & 8 else acc + d
            acc = max(-32768, min(32767, acc))
            idx = max(0, min(88, idx + IMA_ADJ[v & 7]))
            out.append(acc)
    return out

def ima_decode(data, nsamp):
    return ima_nibbles(n for byte in data for n in (byte & 15, byte >> 4))[:nsamp]

def ima_decode_stereo(data, nsamp):
    # stereo: one byte per frame, low nibble = left, high nibble = right
    left = ima_nibbles(byte & 15 for byte in data)[:nsamp]
    right = ima_nibbles(byte >> 4 for byte in data)[:nsamp]
    out = array.array('h')
    for l, r in zip(left, right):
        out.append(l); out.append(r)
    return out

def pad_audio(blocks, p):
    mem = b''.join(blocks[2:])
    o = p['start'] - MEM_BASE
    if p['channels'] == 2:
        return ima_decode_stereo(mem[o:o + p['nbytes']], p['nsamp'])
    return ima_decode(mem[o:o + p['nbytes']], p['nsamp'])

def write_wav(path, samples, rate, channels=1):
    if sys.byteorder == 'big':
        samples = array.array('h', samples); samples.byteswap()
    with wave.open(path, 'wb') as w:
        w.setnchannels(channels); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(samples.tobytes())


# ---------------------------------------------------------------- import (build)
GRADE_BY_NAME = {'high': 0, 'standard': 1, 'long': 2, 'extralong': 3, 'extra-long': 3, 'xlong': 3}
SETTINGS = 2016

def read_wav_any(path):
    """Return (channels: list of float lists in -1..1, rate). PCM int or float, incl. WAVE_FORMAT_EXTENSIBLE."""
    d = open(path, 'rb').read()
    if d[:4] != b'RIFF' or d[8:12] != b'WAVE':
        sys.exit(f"{path}: not a WAV file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(d):
        cid, size = d[pos:pos + 4], struct.unpack('<I', d[pos + 4:pos + 8])[0]
        body = d[pos + 8:pos + 8 + size]
        if cid == b'fmt ': fmt = body
        elif cid == b'data': data = body
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        sys.exit(f"{path}: missing fmt or data chunk")
    tag, ch, rate, _, align, bits = struct.unpack('<HHIIHH', fmt[:16])
    if tag == 0xFFFE and len(fmt) >= 26:
        tag = struct.unpack('<H', fmt[24:26])[0]
    n = len(data) // align
    if tag == 3 and bits == 32:
        vals = array.array('f', data[:n * align])
        if sys.byteorder == 'big': vals.byteswap()
        flat = list(vals)
    elif tag == 1:
        w = bits // 8
        if w == 1:
            flat = [(b - 128) / 128 for b in data[:n * align]]
        else:
            scale = float(1 << (bits - 1))
            flat = [int.from_bytes(data[i:i + w], 'little', signed=True) / scale for i in range(0, n * align, w)]
    else:
        sys.exit(f"{path}: unsupported WAV format (tag {tag}, {bits}-bit)")
    return [flat[c::ch] for c in range(ch)], rate

def resample(x, src, dst, taps=16, phases=512):
    """Windowed-sinc resampler (pure Python, good enough for samples)."""
    if src == dst:
        return list(x)
    ratio = src / dst
    cut = min(1.0, dst / src)
    half = int(math.ceil(taps / cut))
    table = []
    for ph in range(phases + 1):
        frac = ph / phases; row = []
        for k in range(-half + 1, half + 1):
            t = k - frac
            arg = math.pi * t * cut
            sinc = 1.0 if t == 0 else math.sin(arg) / arg
            win = 0.5 + 0.5 * math.cos(math.pi * t / half) if abs(t) < half else 0.0
            row.append(cut * sinc * win)
        table.append(row)
    n_out = int(len(x) / ratio); out = [0.0] * n_out; L = len(x)
    for n in range(n_out):
        t = n * ratio; i = int(t); row = table[int((t - i) * phases + 0.5)]
        acc = 0.0; j0 = i - half + 1
        for k, c in enumerate(row):
            j = j0 + k
            if 0 <= j < L: acc += c * x[j]
        out[n] = acc
    return out

def ima_encode(samples):
    acc = 0; idx = 0; out = []
    for s in samples:
        st = IMA[idx]; diff = s - acc; v = 0
        if diff < 0: v = 8; diff = -diff
        d = st >> 3
        if diff >= st: v |= 4; diff -= st; d += st
        if diff >= st >> 1: v |= 2; diff -= st >> 1; d += st >> 1
        if diff >= st >> 2: v |= 1; d += st >> 2
        acc = acc - d if v & 8 else acc + d
        acc = max(-32768, min(32767, acc)); idx = max(0, min(88, idx + IMA_ADJ[v & 7]))
        out.append(v)
    return out

def parse_kit(path):
    kit = dict(base=None, settings={}, pads=[])
    for raw in open(path, encoding='utf-8'):
        line = raw.split('#')[0].strip()
        if not line: continue
        low = line.lower()
        if low.startswith('base:'):
            kit['base'] = line.split(':', 1)[1].strip(); continue
        if low.startswith('channel'):
            kit['settings']['channel'] = int(low.split()[1]); continue
        if low.startswith('devnum'):
            kit['settings']['devnum'] = int(low.split()[1]); continue
        if low.startswith('record'):
            for w in low.split()[1:]:
                if w in GRADE_BY_NAME: kit['settings']['grade'] = GRADE_BY_NAME[w]
                if w in ('mono', 'stereo'): kit['settings']['stereo'] = (w == 'stereo')
            continue
        if low.startswith('pad'):
            head, rest = line.split(':', 1)
            num = int(head.split()[1])
            words = rest.split()
            # file name may contain spaces: take words up to and including the one ending in .wav
            k = next(i for i, w in enumerate(words) if w.lower().endswith('.wav'))
            pad = dict(pad=num, file=' '.join(words[:k + 1]), grade=0, stereo=False, mode=0,
                       vol=100, trim=None, normalize=False, autotrim=False, pitch=0, loop_at=None)
            ws = [w.lower() for w in words[k + 1:]]; i = 0
            while i < len(ws):
                w = ws[i]
                if w in GRADE_BY_NAME: pad['grade'] = GRADE_BY_NAME[w]
                elif w == 'stereo': pad['stereo'] = True
                elif w == 'mono': pad['stereo'] = False
                elif w in ('one-shot', 'oneshot'): pad['mode'] = 0
                elif w == 'loop': pad['mode'] = 1
                elif w in ('endloop', 'end-loop'): i += 1; pad['mode'] = 2; pad['loop_at'] = float(ws[i])
                elif w == 'pitch': i += 1; pad['pitch'] = float(ws[i])
                elif w in ('normalize', 'normalise'):
                    pad['normalize'] = -6.0
                    if i + 1 < len(ws) and ws[i + 1].lstrip('-+').replace('.', '', 1).isdigit():
                        i += 1; pad['normalize'] = -abs(float(ws[i])) + 0.0
                elif w in ('autotrim', 'auto-trim'): pad['autotrim'] = True
                elif w in ('vol', 'volume'): i += 1; pad['vol'] = max(0, min(127, int(ws[i])))
                elif w == 'trim': i += 1; a, b = ws[i].split('-'); pad['trim'] = (float(a), float(b))
                else: sys.exit(f"kit file: don't understand '{w}' on pad {num}")
                i += 1
            if not 1 <= num <= 48: sys.exit(f"pad {num}: pads go from 1 to 48")
            kit['pads'].append(pad); continue
        sys.exit(f"kit file: don't understand line: {line}")
    return kit

def init_blocks():
    """Block 0 and 1 exactly as an SU10 sends them right after Init (no samples)."""
    b0 = bytearray(b'\xff' * 8192); b1 = bytearray(b'\xff' * 8192)
    for i in range(48):
        b0[i * 42:i * 42 + 42] = bytes(42); b0[i * 42 + 36] = 36 + i
    b0[SETTINGS:SETTINGS + 28] = bytes([2,20,1,0,0,1,0,0,0,255,0,0,127,102,0,0,0,0,0,0,1,1,1,1,63,0,0,63])
    b0[2080:2128] = bytes(range(48))
    b1[0:42] = bytes(42); b1[42] = b1[43] = 0x40
    return bytes(b0), bytes(b1)

INIT_HEADER = bytes([0xF0,0x43,0x00,0x7F,0x36,0x00,0x00,0x05,0x00,0x00,0x01,0x00,0x00,0x7F,0xF7])

def find_base(kitdir, base):
    folder = os.path.join(kitdir, base) if base else None
    if not folder:
        return None
    if os.path.isdir(folder):
        files = sorted(glob.glob(os.path.join(folder, '*.syx')), key=lambda f: ('header' not in f.lower(), f))
        if files: return files
    if os.path.isfile(folder): return [folder]
    sys.exit(f"base: no .syx files found at {folder}")

def natural_key(name):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]

def kit_from_folder(folder):
    folder = os.path.abspath(folder)
    name = os.path.basename(folder.rstrip(os.sep))
    kitpath = os.path.join(folder, name + '.txt')
    if os.path.exists(kitpath):
        print(f"using existing kit list: {name}.txt (delete it to start fresh)")
        return kitpath
    wavs = sorted((f for f in os.listdir(folder) if f.lower().endswith('.wav')), key=natural_key)
    if not wavs: sys.exit(f"no WAV files in {folder}")
    if len(wavs) > 48: sys.exit("more than 48 WAVs; the SU10 has 48 pads")
    lines = [f"# Made automatically from the WAVs in '{name}'. Edit it and run build again.",
             "# Machine settings (remove the # to use):", "# channel 10", "# record Long mono", ""]
    w = max(len(f) for f in wavs)
    lines += [f"pad {i + 1}: {f.ljust(w)}  High  mono  one-shot  autotrim  normalize" for i, f in enumerate(wavs)]
    open(kitpath, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(f"wrote kit list {name}.txt ({len(wavs)} pads)")
    return kitpath

def cmd_build(kitpath):
    if os.path.isdir(kitpath):
        kitpath = kit_from_folder(kitpath)
    kitdir = os.path.dirname(os.path.abspath(kitpath))
    kitname = os.path.splitext(os.path.basename(kitpath))[0]
    kit = parse_kit(kitpath)
    base = find_base(kitdir, kit['base'])
    if base:
        header, blocks = memory_blocks(base)
    else:
        header, b01 = INIT_HEADER, init_blocks(); blocks = list(b01) + [b'\xff' * 8192] * 48
    table = bytearray(blocks[0]); header = bytearray(header)
    st = kit['settings']
    if 'grade' in st: table[SETTINGS + 0] = st['grade']
    if 'stereo' in st: table[SETTINGS + 5] = 1 if st['stereo'] else 0
    if 'channel' in st: table[SETTINGS + 6] = st['channel'] - 1
    if 'devnum' in st: table[SETTINGS + 8] = st['devnum'] - 1; header[2] = st['devnum'] - 1
    # empty every pad (keep its note number), then fill the kit pads
    for i in range(48):
        e = i * 42; note = table[e + 36]
        table[e:e + 42] = bytes(42); table[e + 36] = note
    mem = bytearray(b'\xff' * (48 * 8192)); addr = MEM_BASE
    previews = os.path.join(kitdir, kitname + ' preview'); os.makedirs(previews, exist_ok=True)
    seen = set()
    for p in sorted(kit['pads'], key=lambda p: p['pad']):
        if p['pad'] in seen: sys.exit(f"pad {p['pad']} is listed twice")
        seen.add(p['pad'])
        chans, rate = read_wav_any(os.path.join(kitdir, p['file']))
        if p['trim']:
            a, b = int(p['trim'][0] * rate), int(p['trim'][1] * rate)
            chans = [c[a:b] for c in chans]
        if p['autotrim']:
            peak = max((abs(v) for c in chans for v in c), default=0)
            thr = peak * 10 ** (-50 / 20)
            loud = [i for i in range(len(chans[0])) if any(abs(c[i]) > thr for c in chans)]
            if loud:
                a = max(0, loud[0] - int(0.005 * rate)); b = min(len(chans[0]), loud[-1] + int(0.02 * rate))
                before = len(chans[0])
                chans = [c[a:b] for c in chans]
                p['trimmed'] = (before - len(chans[0])) / rate
        if not p['stereo'] and len(chans) > 1:
            chans = [[sum(v) / len(chans) for v in zip(*chans)]]
        if p['stereo'] and len(chans) == 1:
            chans = [chans[0], chans[0]]
        chans = chans[:2]
        dst = GRADE_RATES[p['grade']]
        chans = [resample(c, rate * 2 ** (p['pitch'] / 12), dst) for c in chans]
        peak = max((abs(v) for c in chans for v in c), default=0) or 1.0
        gain = (10 ** (p['normalize'] / 20)) / peak if p['normalize'] is not False else 1.0
        ints = [[max(-32768, min(32767, int(round(v * gain * 32767)))) for v in c] for c in chans]
        n = len(ints[0])
        if p['stereo']:
            L = ima_encode(ints[0] + [0]); R = ima_encode(ints[1] + [0])
            data = bytes(l | (r << 4) for l, r in zip(L, R))            # n + 1 bytes, like the SU10
        else:
            m = ints[0] + [0] * (4 + (n & 1))                             # n/2 + 2 bytes, like the SU10
            nib = ima_encode(m)
            data = bytes(nib[i] | (nib[i + 1] << 4) for i in range(0, len(nib), 2))
        if addr - MEM_BASE + len(data) > len(mem):
            used = (addr - MEM_BASE) / 1024
            sys.exit(f"Kit doesn't fit: pad {p['pad']} needs {len(data)/1024:.0f} KB, "
                     f"only {384 - used:.0f} KB left. Use a lower grade, mono, or trim.")
        mem[addr - MEM_BASE:addr - MEM_BASE + len(data)] = data
        e = (p['pad'] - 1) * 42
        table[e:e + 4] = addr.to_bytes(4, 'big')
        table[e + 12:e + 16] = len(data).to_bytes(4, 'big')
        table[e + 26:e + 30] = n.to_bytes(4, 'big')
        table[e + 30] = p['mode']; table[e + 32] = p['vol']; table[e + 33] = 0x40
        table[e + 34] = 2 if p['stereo'] else 1; table[e + 38] = p['grade']; table[e + 39] = 0x14
        if p['mode'] == 2:   # end-loop: loop start in samples, bytes 22-25
            table[e + 22:e + 26] = max(1, min(n - 2, int(round(p['loop_at'] * dst)))).to_bytes(4, 'big')
        addr += len(data)
        print(f"pad {p['pad']:2d}: {p['file']}  {GRADE_NAMES[p['grade']]} {'stereo' if p['stereo'] else 'mono'} "
              f"{['one-shot', 'loop', 'endloop %.2f s' % (p['loop_at'] or 0)][p['mode']]}  {n/dst:.2f} s  {len(data)/1024:.1f} KB"
              + (f"  normalized to {p['normalize'] + 0:.0f} dB ({20*math.log10(gain):+.1f} dB)" if p['normalize'] is not False else "")
              + (f"  silence cut {p['trimmed']:.2f} s" if p.get('trimmed') else ""))
    new_blocks = [bytes(table), blocks[1]] + [bytes(mem[k * 8192:(k + 1) * 8192]) for k in range(48)]
    out = rebuild(bytes(header), new_blocks)
    hp = os.path.join(kitdir, kitname + '_header.syx'); dp = os.path.join(kitdir, kitname + '_data.syx')
    open(hp, 'wb').write(out[:15]); open(dp, 'wb').write(out[15:])
    # previews = exactly what the SU10 will play, decoded back from the new dump
    _, check = memory_blocks([hp, dp])
    for p in pad_table(check):
        if p['nbytes']:
            r = GRADE_RATES[p['grade']]
            write_wav(os.path.join(previews, f"pad{p['pad']:02d}_{GRADE_NAMES[p['grade']]}.wav"),
                      pad_audio(check, p), r, 2 if p['channels'] == 2 else 1)
    used = addr - MEM_BASE
    print(f"memory used: {used/1024:.0f} of 384 KB ({100*used/(48*8192):.0f}%)")
    print(f"wrote {os.path.basename(hp)} + {os.path.basename(dp)}  (previews in '{os.path.basename(previews)}')")

# ---------------------------------------------------------------- commands
def cmd_info(paths):
    _, blocks = memory_blocks(paths)
    used = 0
    print("pad  bank  note  vol  mode  grade      rate   samples   seconds  start")
    for p in pad_table(blocks):
        if not p['nbytes']:
            continue
        used += p['nbytes']; r = GRADE_RATES.get(p['grade'], 20050)
        print(f"{p['pad']:3d}  {p['bank']}{p['num']:<3d}  {p['note']:4d}  {p['volume']:3d}  {p['flag']:4d}  {GRADE_NAMES.get(p['grade'],'?'):9s}  {r:5d}  {p['nsamp']:8d}  {p['nsamp']/r:7.2f}  0x{p['start']:06X}")
    print(f"sample memory used: {used} of {48*8192} bytes ({100*used/(48*8192):.1f}%)")

def cmd_extract(paths, outdir):
    _, blocks = memory_blocks(paths)
    os.makedirs(outdir, exist_ok=True)
    for p in pad_table(blocks):
        if not p['nbytes']:
            continue
        r = GRADE_RATES.get(p['grade'], 20050)
        name = f"pad{p['pad']:02d}_{p['bank']}{p['num']:02d}_{GRADE_NAMES.get(p['grade'],'grade'+str(p['grade']))}_{'stereo' if p['channels'] == 2 else 'mono'}_{r}Hz.wav"
        write_wav(os.path.join(outdir, name), pad_audio(blocks, p), r, 2 if p['channels'] == 2 else 1)
        print("wrote", name)

def cmd_verify(paths):
    header, blocks = memory_blocks(paths)
    orig = b''.join(open(p, 'rb').read() for p in paths)
    print("rebuild byte-identical:", rebuild(header, blocks) == orig)

if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] in ('-h', '--help'):
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    syx = [a for a in args if a.lower().endswith('.syx')]
    rest = [a for a in args if not a.lower().endswith('.syx')]
    if cmd == 'info': cmd_info(syx)
    elif cmd == 'extract': cmd_extract(syx, rest[0] if rest else os.path.splitext(os.path.basename(syx[0]))[0] + '_wav')
    elif cmd == 'verify': cmd_verify(syx)
    elif cmd == 'build': cmd_build(args[0])
    else: sys.exit(__doc__)
