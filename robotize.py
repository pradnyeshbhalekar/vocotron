"""
Stage 2: Apply a robotic voice effect to a vocal stem.

Effects are implemented as plain functions of (signal, sr, **params) -> signal,
registered in EFFECTS so new ones (vocoder, pitch quantization, ...) can be
added later as alternate --effect options.

Usage:
    python robotize.py vocal.wav --out robo_vocal.wav
    python robotize.py vocal.wav --out robo_vocal.wav --effect ring_mod --freq 40
"""
import argparse
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt


def effect_ring_mod(signal: np.ndarray, sr: int, freq: float = 40.0, mix: float = 1.0) -> np.ndarray:
    """Ring modulation: multiply the signal by a fixed-frequency carrier sine.

    freq: carrier frequency in Hz. ~30-50 Hz gives a subtle robotic buzz,
          higher values (150+) give a harsher, more metallic/Dalek tone.
    mix:  0.0 = dry signal only, 1.0 = fully ring-modulated.
    """
    n_samples = signal.shape[0]
    t = np.arange(n_samples) / sr
    carrier = np.sin(2 * np.pi * freq * t)
    if signal.ndim == 2:
        carrier = carrier[:, np.newaxis]
    modulated = signal * carrier
    return (1 - mix) * signal + mix * modulated


def _bandpass_sos(low: float, high: float, sr: int, order: int = 4):
    nyq = sr / 2
    low = max(low / nyq, 1e-5)
    high = min(high / nyq, 0.999)
    return butter(order, [low, high], btype="band", output="sos")


def _envelope(x: np.ndarray, sr: int, smooth_hz: float = 20.0) -> np.ndarray:
    rectified = np.abs(x)
    sos = butter(2, smooth_hz / (sr / 2), btype="low", output="sos")
    return sosfiltfilt(sos, rectified)


def _pitch_track_carrier(
    mono: np.ndarray, sr: int, n: int, carrier: str, min_freq: float, max_freq: float,
    octave_shift: int = 0,
) -> np.ndarray:
    """Build a harmonically-rich carrier that tracks the vocal's own pitch.

    Estimates f0 per frame with librosa.pyin, fills unvoiced gaps by holding
    the last pitch, upsamples to the sample rate, and integrates instantaneous
    frequency into a continuous phase so the carrier stays in tune with the
    singer's melody instead of droning on one flat note.
    """
    frame_length = 2048
    hop_length = 512
    f0, voiced_flag, _ = librosa.pyin(
        mono, fmin=min_freq, fmax=max_freq, sr=sr,
        frame_length=frame_length, hop_length=hop_length,
    )

    # Hold last voiced pitch through unvoiced/silent gaps instead of dropping to 0.
    f0 = np.where(voiced_flag, f0, np.nan)
    valid = ~np.isnan(f0)
    if valid.any():
        first_valid = np.argmax(valid)
        f0[:first_valid] = f0[first_valid]
        idx = np.where(valid, np.arange(len(f0)), 0)
        np.maximum.accumulate(idx, out=idx)
        f0 = f0[idx]
    else:
        f0 = np.full(len(f0), (min_freq + max_freq) / 2)

    frame_times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length)
    sample_times = np.arange(n) / sr
    f0_samples = np.interp(sample_times, frame_times, f0)
    f0_samples = f0_samples * (2.0 ** octave_shift)

    phase = 2 * np.pi * np.cumsum(f0_samples) / sr
    cycle_pos = (phase / (2 * np.pi)) % 1.0

    if carrier == "sawtooth":
        return 2.0 * cycle_pos - 1.0
    elif carrier == "square":
        return np.where(cycle_pos < 0.5, 1.0, -1.0)
    else:
        raise ValueError(f"Unknown carrier waveform '{carrier}'")


def effect_vocoder(
    signal: np.ndarray,
    sr: int,
    n_bands: int = 18,
    carrier: str = "sawtooth",
    mix: float = 0.85,
    min_freq: float = 65.0,
    max_freq: float = 1000.0,
    octave_shift: int = -1,
) -> np.ndarray:
    """Classic mechanical robot-voice vocoder.

    Splits the vocal into frequency bands, extracts each band's amplitude
    envelope, and uses it to modulate the matching band of a buzzy synth
    carrier tone (sawtooth/square). The carrier tracks the vocal's own pitch
    (see _pitch_track_carrier) so the melody is preserved -- this is what
    makes it sound like a proper music-production vocoder (Daft Punk /
    Kraftwerk / talkbox style) rather than a flat monotone drone.

    n_bands:  number of vocoder bands; more bands = clearer intelligibility,
              fewer bands = more robotic/buzzy.
    carrier:  "sawtooth" or "square" -- square is thicker/hollower and more
              buzzy than sawtooth.
    min_freq/max_freq: pitch-tracking search range in Hz (defaults cover
              typical vocal range).
    octave_shift: shift the tracked carrier pitch by whole octaves (e.g. -1
              drops it an octave for a deeper/thicker robotic tone) while
              still following the vocal's melodic contour.
    """
    mono = signal.mean(axis=1) if signal.ndim == 2 else signal
    n = len(mono)

    carrier_wave = _pitch_track_carrier(mono, sr, n, carrier, min_freq, max_freq, octave_shift)

    band_edges = np.geomspace(80, min(8000, sr / 2 - 100), n_bands + 1)
    out = np.zeros(n)
    for lo, hi in zip(band_edges[:-1], band_edges[1:]):
        sos_band = _bandpass_sos(lo, hi, sr)
        vocal_band = sosfiltfilt(sos_band, mono)
        env = _envelope(vocal_band, sr)
        carrier_band = sosfiltfilt(sos_band, carrier_wave)
        out += env * carrier_band

    if signal.ndim == 2:
        out = np.repeat(out[:, np.newaxis], signal.shape[1], axis=1)

    return (1 - mix) * signal + mix * out


# Effect registry: name -> callable(signal, sr, **kwargs) -> signal
EFFECTS = {
    "ring_mod": effect_ring_mod,
    "vocoder": effect_vocoder,
    # "pitch_quantize": effect_pitch_quantize,  # TODO: future effect
}


def normalize(signal: np.ndarray, peak: float = 0.95) -> np.ndarray:
    max_val = np.max(np.abs(signal))
    if max_val > 0:
        signal = signal / max_val * peak
    return signal


def robotize(input_path: Path, output_path: Path, effect: str, effect_params: dict) -> Path:
    if effect not in EFFECTS:
        raise ValueError(f"Unknown effect '{effect}'. Available: {list(EFFECTS)}")

    signal, sr = sf.read(input_path)
    processed = EFFECTS[effect](signal, sr, **effect_params)
    processed = normalize(processed)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, processed, sr)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Stage 2: apply a robotic voice effect")
    parser.add_argument("input", type=Path, help="Path to input vocal wav")
    parser.add_argument("--out", type=Path, default=Path("out/robo_vocal.wav"), help="Output wav path")
    parser.add_argument("--effect", default="vocoder", choices=list(EFFECTS), help="Effect to apply")
    parser.add_argument("--freq", type=float, default=40.0, help="ring_mod: carrier frequency in Hz")
    parser.add_argument("--mix", type=float, default=None, help="dry/wet mix (0-1); defaults per-effect")
    parser.add_argument("--n-bands", type=int, default=18, help="vocoder: number of frequency bands")
    parser.add_argument("--carrier", default="sawtooth", choices=["sawtooth", "square"], help="vocoder: carrier waveform")
    parser.add_argument("--octave-shift", type=int, default=-1, help="vocoder: shift carrier pitch by whole octaves (e.g. -1 for deeper/thicker)")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    if args.effect == "ring_mod":
        effect_params = {"freq": args.freq, "mix": args.mix if args.mix is not None else 1.0}
    elif args.effect == "vocoder":
        effect_params = {
            "n_bands": args.n_bands,
            "carrier": args.carrier,
            "mix": args.mix if args.mix is not None else 0.85,
            "octave_shift": args.octave_shift,
        }

    out_path = robotize(args.input, args.out, args.effect, effect_params)
    print(f"Robotized vocal written to: {out_path}")


if __name__ == "__main__":
    main()
