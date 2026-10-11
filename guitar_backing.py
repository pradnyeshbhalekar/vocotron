"""
Stage 3: Generate a strummed acoustic guitar backing track from a chord
progression, key, tempo, and time signature.

Pipeline: chord progression -> strum-pattern MIDI -> fluidsynth render (wav),
using a free acoustic guitar soundfont.

Usage:
    python guitar_backing.py --chords "C,G,Am,F" --key C --tempo 90 \
        --time-sig 4/4 --out out/guitar.wav

    python guitar_backing.py --chords "C,G,Am,F" --tempo 120 \
        --pattern "D-DU-UDU" --bars-per-chord 2 --out out/guitar.wav
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import pretty_midi

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_ALIASES = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

# Interval sets (semitones from root) for supported chord qualities.
CHORD_QUALITIES = {
    "":     [0, 4, 7],       # major
    "maj":  [0, 4, 7],
    "m":    [0, 3, 7],       # minor
    "min":  [0, 3, 7],
    "7":    [0, 4, 7, 10],   # dominant 7
    "maj7": [0, 4, 7, 11],
    "m7":   [0, 3, 7, 10],
    "min7": [0, 3, 7, 10],
    "dim":  [0, 3, 6],
    "aug":  [0, 4, 8],
    "sus2": [0, 2, 7],
    "sus4": [0, 5, 7],
}

DEFAULT_SOUNDFONT = Path("soundfonts/AcousticGuitar.sf2")
GM_PROGRAM = 25  # this soundfont's only preset: bank 0, program 25 (Acoustic Guitar)

CHORD_RE = re.compile(r"^([A-G])([#b]?)(.*)$")


def parse_chord(symbol: str) -> tuple[int, list[int]]:
    """Parse a chord symbol like 'Am7' -> (root pitch class, interval list)."""
    symbol = symbol.strip()
    m = CHORD_RE.match(symbol)
    if not m:
        raise ValueError(f"Could not parse chord symbol: '{symbol}'")
    letter, accidental, quality = m.groups()
    root_name = letter + accidental
    root_name = NOTE_ALIASES.get(root_name, root_name)
    if root_name not in NOTE_NAMES:
        raise ValueError(f"Unknown root note in chord: '{symbol}'")
    root_pc = NOTE_NAMES.index(root_name)

    quality = quality.strip()
    if quality not in CHORD_QUALITIES:
        raise ValueError(
            f"Unknown chord quality '{quality}' in '{symbol}'. "
            f"Supported: {sorted(CHORD_QUALITIES)}"
        )
    return root_pc, CHORD_QUALITIES[quality]


def chord_voicing(root_pc: int, intervals: list[int], base_octave: int = 3, n_notes: int = 5) -> list[int]:
    """Spread a chord's tones across ~2 octaves to approximate an open guitar voicing."""
    notes = []
    for i in range(n_notes):
        interval = intervals[i % len(intervals)]
        octave_add = 12 * (i // len(intervals))
        midi_note = 12 * (base_octave + 1) + root_pc + interval + octave_add
        notes.append(midi_note)
    return notes


def parse_time_sig(time_sig: str) -> tuple[int, int]:
    num, den = time_sig.split("/")
    return int(num), int(den)


def build_strum_pattern(pattern: str, eighths_per_bar: int) -> str:
    """Tile or truncate a D/U/- pattern string to fill a bar's eighth-note grid."""
    if not pattern:
        raise ValueError("Strum pattern must not be empty")
    tiled = (pattern * (eighths_per_bar // len(pattern) + 1))[:eighths_per_bar]
    return tiled


def generate_guitar_midi(
    chords: list[str],
    tempo: float,
    time_sig: str,
    pattern: str,
    bars_per_chord: int,
    strum_spread: float = 0.02,
) -> pretty_midi.PrettyMIDI:
    numerator, denominator = parse_time_sig(time_sig)
    quarter_len = 60.0 / tempo
    eighth_len = quarter_len / 2
    eighths_per_bar = numerator * 8 // denominator
    strum_events = build_strum_pattern(pattern, eighths_per_bar)

    pm = pretty_midi.PrettyMIDI(initial_tempo=tempo)
    guitar = pretty_midi.Instrument(program=GM_PROGRAM, name="Acoustic Guitar")

    t = 0.0
    for chord_symbol in chords:
        root_pc, intervals = parse_chord(chord_symbol)
        voicing = sorted(chord_voicing(root_pc, intervals))

        for _bar in range(bars_per_chord):
            bar_start = t
            for i, direction in enumerate(strum_events):
                if direction == "-":
                    continue
                event_start = bar_start + i * eighth_len
                # Notes ring until the next strum hit (or bar end), for a natural sustain.
                next_start = bar_start + (i + 1) * eighth_len
                note_end = next_start + eighth_len  # let it ring a bit past the next hit

                strum_order = voicing if direction == "D" else list(reversed(voicing))
                for s, pitch in enumerate(strum_order):
                    onset = event_start + s * (strum_spread / len(strum_order))
                    velocity = 95 if direction == "D" else 75
                    note = pretty_midi.Note(
                        velocity=velocity, pitch=pitch, start=onset, end=note_end
                    )
                    guitar.notes.append(note)
            t = bar_start + numerator * quarter_len * (4 / denominator)

    pm.instruments.append(guitar)
    return pm


def render_with_fluidsynth(midi_path: Path, soundfont: Path, out_wav: Path, sample_rate: int = 44100) -> None:
    if not soundfont.exists():
        raise FileNotFoundError(f"Soundfont not found: {soundfont}")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "fluidsynth", "-ni",
        "-F", str(out_wav),
        "-r", str(sample_rate),
        str(soundfont), str(midi_path),
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main():
    parser = argparse.ArgumentParser(description="Stage 3: generate a strummed acoustic guitar backing track")
    parser.add_argument("--chords", required=True, help="Comma or dash separated chord progression, e.g. 'C,G,Am,F'")
    parser.add_argument("--key", default=None, help="Song key (e.g. 'C'); informational, not used to alter chords")
    parser.add_argument("--tempo", type=float, required=True, help="Tempo in BPM")
    parser.add_argument("--time-sig", default="4/4", help="Time signature, e.g. '4/4', '3/4', '6/8'")
    parser.add_argument("--pattern", default="D-DU-UDU", help="Strum pattern per bar: D=down, U=up, -=rest, one char per eighth note")
    parser.add_argument("--bars-per-chord", type=int, default=1, help="How many bars to hold each chord")
    parser.add_argument("--soundfont", type=Path, default=DEFAULT_SOUNDFONT, help="Path to .sf2 soundfont")
    parser.add_argument("--out", type=Path, default=Path("out/guitar.wav"), help="Output wav path")
    parser.add_argument("--midi-out", type=Path, default=None, help="Optional: also save the intermediate MIDI file")
    args = parser.parse_args()

    chords = [c.strip() for c in re.split(r"[,\-]", args.chords) if c.strip()]
    if not chords:
        print("No chords parsed from --chords", file=sys.stderr)
        sys.exit(1)

    pm = generate_guitar_midi(
        chords=chords,
        tempo=args.tempo,
        time_sig=args.time_sig,
        pattern=args.pattern,
        bars_per_chord=args.bars_per_chord,
    )

    midi_path = args.midi_out or Path("out/_guitar_tmp.mid")
    midi_path.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(midi_path))
    print(f"MIDI written to: {midi_path}")

    render_with_fluidsynth(midi_path, args.soundfont, args.out)
    print(f"Guitar backing track written to: {args.out}")

    if args.midi_out is None:
        midi_path.unlink()


if __name__ == "__main__":
    main()
