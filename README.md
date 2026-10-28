# SU10-Kit

**Build sample kits for the Yamaha SU10 on your computer, and load them into the sampler over MIDI.**

The SU10 is a small 1990s phrase sampler with 384 KB of memory and no official way to get sounds in, other than recording them. SU10-Kit lets you put your own WAV files on its pads, choose quality, loop and volume per pad, and save a bulk dump that the SU10 loads like one of its own backups. It also works the other way: open a dump and get every pad back as a WAV.

- **[Open SU10-Kit-Builder in your browser](https://harmonicworks.org/SU10-kit/)**: nothing to install
- **`su10kit.py`**: the same engine as a command-line tool (Python 3, no extra packages)

> Not affiliated with Yamaha. Tested on one SU10 so far, so please share how it works on yours.

## What you need

- A Yamaha SU10
- A MIDI interface (tested with a Yamaha UX16 and an M-Audio MIDISport)
- A program that sends SysEx files: [SysEx Librarian](https://www.snoize.com/sysexlibrarian/) on Mac, MIDI-OX on Windows

**Back up your SU10 first.** A failed transfer leaves it empty.

## Building a kit in the browser

1. Open [SU10-Kit-Builder](https://harmonicworks.org/SU10-kit/). It starts with an example kit you can play.
2. Drop WAV files on the pads. Drop several at once to fill the empty pads in order.
3. Per pad, choose:
   - **Quality**: High, Standard, Long or Extra long (more quality = less sampling time)
   - **Mono or stereo**: stereo uses twice the memory
   - **Play mode**: one-shot, loop, or end-loop (plays once, then repeats the last part), with snap to zero crossing
   - **Volume, normalize, pitch**, start and end points, and *cut silence*
4. Watch the memory meter: everything has to fit in 384 KB.
5. Press **Play** to hear exactly what the SU10 will play.
6. Set the machine settings (MIDI channel, device number) and press **Save kit**.

You get a zip with `<kit>_header.syx`, `<kit>_data.syx` and a short pad list.

## Sending the kit to the SU10

1. Send `<kit>_header.syx`.
2. Wait until the MIDI indicator on the SU10 goes off.
3. Send `<kit>_data.syx`, with a pause of **110–150 ms** between messages (in SysEx Librarian: *Pause between messages*).

Below about 100 ms the SU10 says *Wrong Data*. At 150 ms a full kit takes about 5 minutes.

If nothing happens at all, check the **device number**: the SU10 ignores dumps made for another DevNum.

## Backing up the SU10

1. In SysEx Librarian, press **Record One**.
2. On the SU10: Utility → Bulk → send. The 15-byte header arrives and Record One stops.
3. Immediately press **Record Many**. At each "Next OK" on the SU10 (4 %, 36 %, 68 %), press OK.
4. Click **Done** when the SU10 has finished.

Keep both files together: they are one backup.

## The command-line tool

```
python3 su10kit.py build  "My Kit/"                         # every WAV in the folder on its own pad
python3 su10kit.py build  "My Kit/My Kit.txt"               # a kit list with settings per pad
python3 su10kit.py info    backup_header.syx backup_data.syx
python3 su10kit.py extract backup_header.syx backup_data.syx wavs/
```

A kit list looks like this (see `examples/example-kit.txt`):

```
channel 10
record Long mono
pad 1: bell.wav     High   mono   one-shot  autotrim  normalize
pad 2: bass.wav     Long   mono   loop      vol 90
pad 3: strings.wav  High   stereo endloop 1.25
```

Run `python3 su10kit.py` for all options, and `python3 tests/test_su10kit.py` to check it works on your machine.

## Good to know

- **Memory per second**: High ≈ 20 KB/s mono, Standard ≈ 14.5, Long ≈ 10, Extra long ≈ 7. Stereo doubles it.
- **Normalize to −6 dB** (the default) leaves headroom; 0 dB can sound crushed on the SU10.
- All 48 pads (banks A–D) respond over MIDI whatever bank is selected: pad A1 is C1 (note 36), pad D12 is note 83.
- Pitch, filter amount and crossfader are live controls and are not stored in a kit.

## How it works

The SU10 stores its samples as 4-bit IMA ADPCM, a common audio format, packed into Yamaha's SysEx messages. The full format is in **[FORMAT.md](FORMAT.md)**.

## Credits

Made by Maurice Hissink ([harmonicworks.org](https://harmonicworks.org)).

The format was decoded and the tool written together with Claude, an AI model by Anthropic: the AI did the decoding and the code, the testing on the real SU10 was done by hand. The full story is on the blog.

## Licence

MIT, see [LICENSE](LICENSE).
