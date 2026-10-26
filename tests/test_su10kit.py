"""Run:  python3 tests/test_su10kit.py   (standard library only)"""
import os, sys, math, wave, struct, tempfile, array, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import su10kit as k

INIT = [os.path.join(HERE, 'data', 'init_header.syx'), os.path.join(HERE, 'data', 'init_data.syx')]

def write_wav(path, chans, rate=44100):
    n = len(chans[0]); a = array.array('h', (int(max(-1, min(1, chans[c][i])) * 32767) for i in range(n) for c in range(len(chans))))
    with wave.open(path, 'wb') as w:
        w.setnchannels(len(chans)); w.setsampwidth(2); w.setframerate(rate); w.writeframes(a.tobytes())

def peak_freq(x, rate):
    # zero-crossing count is enough for a clean sine
    z = sum(1 for i in range(1, len(x)) if x[i - 1] < 0 <= x[i])
    return z * rate / len(x)

def test_init_matches_real_su10():
    header, blocks = k.memory_blocks(INIT)
    b0, b1 = k.init_blocks()
    assert header == k.INIT_HEADER and blocks[0] == b0 and blocks[1] == b1

def test_roundtrip_real_dump():
    header, blocks = k.memory_blocks(INIT)
    orig = b''.join(open(f, 'rb').read() for f in INIT)
    assert k.rebuild(header, blocks) == orig

def test_build_and_decode():
    d = tempfile.mkdtemp()
    try:
        r = 44100
        write_wav(os.path.join(d, 'a.wav'), [[0.5 * math.sin(2 * math.pi * 220 * i / r) for i in range(r)]])
        write_wav(os.path.join(d, 'st.wav'), [[0.4 * math.sin(2 * math.pi * 220 * i / r) for i in range(r)],
                                             [0.4 * math.sin(2 * math.pi * 330 * i / r) for i in range(r)]])
        open(os.path.join(d, 'kit.txt'), 'w').write(
            "channel 10\nrecord Long mono\n"
            "pad 1: a.wav High mono one-shot\n"
            "pad 2: a.wav ExtraLong mono loop pitch 12\n"
            "pad 3: st.wav Standard stereo endloop 0.5\n")
        k.cmd_build(os.path.join(d, 'kit.txt'))
        files = [os.path.join(d, 'kit_header.syx'), os.path.join(d, 'kit_data.syx')]
        header, blocks = k.memory_blocks(files)
        assert k.rebuild(header, blocks) == b''.join(open(f, 'rb').read() for f in files)
        pads = k.pad_table(blocks)
        assert blocks[0][k.SETTINGS + 6] == 9                       # channel 10
        p1, p2, p3 = pads[0], pads[1], pads[2]
        assert (p1['grade'], p1['flag'], p1['channels']) == (0, 0, 1)
        assert abs(peak_freq(k.pad_audio(blocks, p1), 40090) - 220) < 2
        assert (p2['grade'], p2['flag']) == (3, 1)
        assert abs(peak_freq(k.pad_audio(blocks, p2), 14560) - 440) < 4   # one octave up
        assert (p3['grade'], p3['flag'], p3['channels']) == (1, 2, 2)
        assert int.from_bytes(p3['raw'][22:26], 'big') == round(0.5 * 29120)
        st = k.pad_audio(blocks, p3)
        assert abs(peak_freq(st[0::2], 29120) - 220) < 2 and abs(peak_freq(st[1::2], 29120) - 330) < 3
    finally:
        shutil.rmtree(d)

if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn(); print('ok ', name)
    print('all tests passed')
