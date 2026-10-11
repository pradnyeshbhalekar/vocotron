"""
Orchestrates the full Vocotron pipeline end-to-end:
    (1. separate vocals -- optional, skipped by default)
    2. robotize the vocal
    3. generate a guitar backing track from a chord progression
    4. mix vocal + guitar into a final track

By default the input is treated as an already-isolated vocal (e.g. an
acapella) and separation is skipped. Pass --separate to run Demucs first
on a full song.

Usage:
    # Input is already a clean vocal/acapella -- skip separation (default):
    python pipeline.py --input vocal.mp3 --chords "C,G,Am,F" --key C \
        --tempo 90 --time-sig 4/4 --out out/final.wav

    # Input is a full song with instrumentation -- run separation first:
    python pipeline.py --input song.mp3 --separate --chords "C,G,Am,F" \
        --key C --tempo 90 --out out/final.wav
"""
import argparse
from pathlib import Path

import guitar_backing
import mix as mix_stage
import robotize
import separate as separate_stage


def run_pipeline(args: argparse.Namespace) -> Path:
    work_dir = args.out.parent / "_pipeline"
    work_dir.mkdir(parents=True, exist_ok=True)

    if args.separate:
        print("== Stage 1: separating vocals with Demucs ==")
        vocal_path, _ = separate_stage.separate(
            args.input, work_dir, model=args.demucs_model, keep_instrumental=False
        )
    else:
        print("== Stage 1: skipped (--separate not set; treating input as vocal) ==")
        vocal_path = args.input

    print("== Stage 2: applying robotic voice effect ==")
    robo_vocal_path = work_dir / "robo_vocal.wav"
    if args.effect == "ring_mod":
        effect_params = {"freq": args.ring_mod_freq, "mix": args.effect_mix if args.effect_mix is not None else 1.0}
    else:
        effect_params = {
            "n_bands": args.n_bands,
            "carrier": args.carrier,
            "mix": args.effect_mix if args.effect_mix is not None else 0.85,
            "octave_shift": args.octave_shift,
        }
    robotize.robotize(vocal_path, robo_vocal_path, args.effect, effect_params)

    print("== Stage 3: generating guitar backing track ==")
    guitar_path = work_dir / "guitar.wav"
    pm = guitar_backing.generate_guitar_midi(
        chords=[c.strip() for c in args.chords.replace("-", ",").split(",") if c.strip()],
        tempo=args.tempo,
        time_sig=args.time_sig,
        pattern=args.pattern,
        bars_per_chord=args.bars_per_chord,
    )
    midi_path = work_dir / "guitar.mid"
    pm.write(str(midi_path))
    guitar_backing.render_with_fluidsynth(midi_path, args.soundfont, guitar_path)

    print("== Stage 4: mixing vocal + guitar ==")
    final_path = mix_stage.mix(
        robo_vocal_path, guitar_path, args.out,
        vocal_gain_db=args.vocal_gain, guitar_gain_db=args.guitar_gain,
        loop_guitar=args.loop_guitar,
    )
    print(f"Final mix written to: {final_path}")
    return final_path


def main():
    parser = argparse.ArgumentParser(description="Vocotron: full vocal-robotizer + guitar-backing pipeline")

    parser.add_argument("--input", type=Path, required=True, help="Input audio: a song (with --separate) or an isolated vocal/acapella")
    parser.add_argument("--separate", action="store_true", help="Run Demucs separation on --input first (use for full songs, not needed for a clean vocal/acapella)")
    parser.add_argument("--demucs-model", default="htdemucs", help="Demucs model name (only used with --separate)")

    parser.add_argument("--effect", default="vocoder", choices=["ring_mod", "vocoder"], help="Robotic voice effect")
    parser.add_argument("--ring-mod-freq", type=float, default=40.0, help="ring_mod: carrier frequency in Hz")
    parser.add_argument("--effect-mix", type=float, default=None, help="Robot effect dry/wet mix (0-1); defaults per-effect")
    parser.add_argument("--n-bands", type=int, default=18, help="vocoder: number of frequency bands")
    parser.add_argument("--carrier", default="sawtooth", choices=["sawtooth", "square"], help="vocoder: carrier waveform")
    parser.add_argument("--octave-shift", type=int, default=-1, help="vocoder: carrier octave shift")

    parser.add_argument("--chords", required=True, help="Chord progression, e.g. 'C,G,Am,F'")
    parser.add_argument("--key", default=None, help="Song key (informational)")
    parser.add_argument("--tempo", type=float, required=True, help="Tempo in BPM")
    parser.add_argument("--time-sig", default="4/4", help="Time signature, e.g. '4/4'")
    parser.add_argument("--pattern", default="D-DU-UDU", help="Strum pattern (D/U/-, one char per eighth note)")
    parser.add_argument("--bars-per-chord", type=int, default=1, help="Bars to hold each chord")
    parser.add_argument("--soundfont", type=Path, default=guitar_backing.DEFAULT_SOUNDFONT, help="Path to guitar .sf2 soundfont")

    parser.add_argument("--vocal-gain", type=float, default=0.0, help="Vocal gain in dB for final mix")
    parser.add_argument("--guitar-gain", type=float, default=-3.0, help="Guitar gain in dB for final mix")
    parser.add_argument("--loop-guitar", action="store_true", help="Loop the guitar backing track to cover the full vocal length instead of going silent partway through")
    parser.add_argument("--out", type=Path, default=Path("out/final_mix.wav"), help="Final output audio path")

    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    run_pipeline(args)


if __name__ == "__main__":
    main()
