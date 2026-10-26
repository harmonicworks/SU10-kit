# The Yamaha SU10 bulk dump format

Everything here was worked out by testing on a real SU10 in October 2026: dumping, changing one thing, dumping again, and sending self-built dumps back to the sampler. Each claim is marked **confirmed** (tested on the hardware) or **likely** (seen in the data, not proven).

## Messages

A full bulk dump is always **1,001 SysEx messages, 479,415 bytes**, however full the memory is. It is a complete memory image.

| Part | Size | Content |
|---|---|---|
| Header | 15 bytes | `F0 43 0d 7F 36 00 00 05 00 00 01 00 00 7F F7` |
| Data | 1,000 messages | `F0 43 0d 7F 36 00 <count hi> <count lo> <index> <data…> <checksum> F7` |

- `0d` = **DevNum − 1** (0 for DevNum 1). An SU10 ignores dumps with a different device number. **Confirmed.**
- `<count>` = number of data bytes + 1 (the index byte), as two 7-bit bytes. 19 messages of 480 data bytes, then 1 of 248, repeated 50 times.
- `<index>` counts 1, 2, 3 … (wrapping at 127).
- **Checksum** = `-(index + sum of the unpacked 8-bit data bytes) & 0x7F`. **Confirmed** (all 1,000 messages, and the SU10 accepts rebuilt dumps).

### 7-in-8 packing

MIDI data bytes are 7-bit, so every 8 bytes carry 7 real bytes: the first byte holds the top bits of the next seven (bit 6 belongs to the first byte, bit 0 to the seventh). **Confirmed.**

## Memory map

Every 20 messages unpack to one **8,192-byte block** (plus 5 padding bytes). 50 blocks = 400 KB:

| Block | Content |
|---|---|
| 0 | Pad table, settings, key map |
| 1 | Unused (FF, except 44 fixed bytes) |
| 2–49 | **384 KB sample memory**. Address `0x20000` = start of block 2 |

## Pad table (block 0, 48 entries of 42 bytes)

Pads are numbered A1–A12, B1–B12, C1–C12, D1–D12 (entry 0–47).

| Bytes | Meaning | Status |
|---|---|---|
| 0–3 | Start address in sample memory (big-endian) | confirmed |
| 4–11 | Small signed values; equal pairs on mono pads, different per channel on stereo pads. Can be 0 | unknown |
| 12–15 | Length in bytes | confirmed |
| 22–25 | End-loop start point, in samples | likely |
| 26–29 | Length in samples | confirmed |
| 30 | Play mode: 0 one-shot, 1 loop, 2 end-loop | confirmed (0, 1), likely (2) |
| 32 | Volume 0–127 (default 100) | confirmed |
| 33 | 0x40 on every used pad | unknown (pan?) |
| 34 | Channels: 1 mono, 2 stereo | confirmed |
| 36 | MIDI note the pad responds to (255 = none). After Init: pad 1 = 36 (C1) … pad 48 = 83 | confirmed |
| 38 | Quality grade, see below | confirmed |
| 39 | 0x14 on every used pad | unknown |

Empty pads are all zero except the note byte.

## Settings (block 0, from offset 2016)

| Offset | Meaning | After Init | Status |
|---|---|---|---|
| +0 | Recording grade (0–3) | 2 (Long) | confirmed |
| +5 | Stereo recording (1 stereo, 0 mono) | 1 | confirmed |
| +6 | MIDI channel − 1 | 0 | confirmed |
| +7 | Local or ribbon setting | 0 | unknown |
| +8 | DevNum − 1 | 0 | confirmed |
| +10 | Unknown (seen as 4) | 0 | unknown |
| +14 | Filter on | 0 | likely |

**Key map** (offset 2080–2127): for each MIDI note 36–83, the pad that plays it (0–47, 255 = none). It mirrors byte 36 of the pad entries; the SU10 keeps both in sync. **Confirmed.**

Not stored in the dump: pitch (ribbon), filter amount, crossfader position, scale mode.

## Audio

Samples are **IMA ADPCM, 4 bits per sample**, the common "DVI" variant: 89-step table, index adjust `-1 -1 -1 -1 2 4 6 8`, decoder starts at 0 / index 0. **Confirmed.**

- **Mono:** two samples per byte, **low nibble first**. Length in bytes ≈ samples / 2 + 2.
- **Stereo:** one byte per sample frame, **low nibble = left, high nibble = right**, each channel its own ADPCM stream. Twice the memory. **Confirmed.**

### Quality grades (pad byte 38)

| Value | Grade | Nominal rate | Measured playback |
|---|---|---|---|
| 0 | High | 40,090 Hz | 40,027 Hz |
| 1 | Standard | ~29,120 Hz | 29,067 Hz |
| 2 | Long | 20,050 Hz | 20,014 Hz |
| 3 | Extra long | ~14,560 Hz | 14,533 Hz |

High and Long rates come from the SU10's own MIDI Sample Dump headers; Standard and Extra long are estimated from measurements. The measured playback is about 0.18 % (3 cents) slow on the test unit. The SU10's tempo display uses the nominal rates.

## Sending a dump back

1. Send the 15-byte header on its own.
2. Wait until the SU10's MIDI indicator goes off.
3. Send the 1,000 data messages with a pause of **110–150 ms** between messages. Below ~100 ms the SU10 reports *Wrong Data*.

A failed restore leaves the SU10 empty, so keep a backup. A dump sent and dumped straight back is byte-for-byte identical: the SU10 stores exactly what it receives.

Transfer prompts ("Next OK") appear at 4 %, 36 % and 68 % of a dump.
