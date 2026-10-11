"""
Stage 4: Mix the robotized vocal with the generated guitar backing track
into a single final audio file.

Handles level balancing (via gain in dB) and length alignment. By default
the shorter track is padded with silence to match the longer one; with
loop_guitar=True the guitar backing is looped (repeated, then trimmed) to
cover the full vocal length instead of going silent partway through.

Usage:
    python mix.py --vocal robo_vocal.wav --guitar guitar.wav --out final_mix.wav
    python mix.py --vocal robo_vocal.wav --guitar guitar.wav --out final_mix.mp3 \
        --vocal-gain 0 --guitar-gain -4 --loop-guitar
"""
import argparse
from pathlib import Path

from pydub import AudioSegment


def mix(
    vocal_path: Path,
    guitar_path: Path,
    out_path: Path,
    vocal_gain_db: float = 0.0,
    guitar_gain_db: float = -3.0,
    loop_guitar: bool = False,
) -> Path:
    vocal = AudioSegment.from_file(vocal_path)
    guitar = AudioSegment.from_file(guitar_path)

    vocal = vocal.apply_gain(vocal_gain_db)
    guitar = guitar.apply_gain(guitar_gain_db)

    length = max(len(vocal), len(guitar))
    if len(vocal) < length:
        vocal = vocal + AudioSegment.silent(duration=length - len(vocal), frame_rate=vocal.frame_rate)

    if len(guitar) < length:
        if loop_guitar and len(guitar) > 0:
            repeats = length // len(guitar) + 1
            guitar = (guitar * repeats)[:length]
        else:
            guitar = guitar + AudioSegment.silent(duration=length - len(guitar), frame_rate=guitar.frame_rate)

    mixed = guitar.overlay(vocal)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_format = out_path.suffix.lstrip(".") or "wav"
    mixed.export(out_path, format=export_format)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Stage 4: mix robotized vocal + guitar backing into final track")
    parser.add_argument("--vocal", type=Path, required=True, help="Path to robotized vocal audio")
    parser.add_argument("--guitar", type=Path, required=True, help="Path to guitar backing track audio")
    parser.add_argument("--out", type=Path, default=Path("out/final_mix.wav"), help="Output mixed audio path (.wav or .mp3)")
    parser.add_argument("--vocal-gain", type=float, default=0.0, help="Vocal gain adjustment in dB")
    parser.add_argument("--guitar-gain", type=float, default=-3.0, help="Guitar gain adjustment in dB")
    parser.add_argument("--loop-guitar", action="store_true", help="Loop the guitar backing track to cover the full vocal length instead of going silent partway through")
    args = parser.parse_args()

    for p in (args.vocal, args.guitar):
        if not p.exists():
            raise SystemExit(f"Input file not found: {p}")

    out_path = mix(args.vocal, args.guitar, args.out, args.vocal_gain, args.guitar_gain, args.loop_guitar)
    print(f"Final mix written to: {out_path}")


if __name__ == "__main__":
    main()
