"""
Stage 1: Vocal / instrumental separation using Demucs.

Splits an input song into stems and writes out the isolated vocal
(and optionally the instrumental) as wav files.

Usage:
    python separate.py input.mp3 --outdir out/
    python separate.py input.mp3 --outdir out/ --model htdemucs --keep-instrumental
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def separate(
    input_path: Path,
    outdir: Path,
    model: str = "htdemucs",
    keep_instrumental: bool = False,
) -> tuple[Path, Path | None]:
    """Run Demucs on input_path, return (vocal_path, instrumental_path_or_None)."""
    outdir.mkdir(parents=True, exist_ok=True)

    # Demucs writes to <demucs_out>/<model>/<track_name>/{vocals,no_vocals}.wav
    demucs_out = outdir / "_demucs"

    cmd = [
        sys.executable, "-m", "demucs",
        "-n", model,
        "-o", str(demucs_out),
        "--two-stems", "vocals",
        str(input_path),
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    track_name = input_path.stem
    stem_dir = demucs_out / model / track_name

    vocal_src = stem_dir / "vocals.wav"
    if not vocal_src.exists():
        raise FileNotFoundError(f"Expected Demucs output not found: {vocal_src}")

    vocal_dst = outdir / f"{track_name}_vocals.wav"
    shutil.copy(vocal_src, vocal_dst)

    instrumental_dst = None
    if keep_instrumental:
        no_vocals_src = stem_dir / "no_vocals.wav"
        instrumental_dst = outdir / f"{track_name}_instrumental.wav"
        shutil.copy(no_vocals_src, instrumental_dst)

    return vocal_dst, instrumental_dst


def main():
    parser = argparse.ArgumentParser(description="Stage 1: isolate vocals with Demucs")
    parser.add_argument("input", type=Path, help="Path to input song (mp3/wav)")
    parser.add_argument("--outdir", type=Path, default=Path("out"), help="Output directory")
    parser.add_argument("--model", default="htdemucs", help="Demucs model name")
    parser.add_argument(
        "--keep-instrumental",
        action="store_true",
        help="Also save the instrumental (no-vocals) stem",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    vocal_path, instrumental_path = separate(
        args.input, args.outdir, args.model, args.keep_instrumental
    )
    print(f"Vocal stem: {vocal_path}")
    if instrumental_path:
        print(f"Instrumental stem: {instrumental_path}")


if __name__ == "__main__":
    main()
