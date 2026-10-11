# Robo-Singer: Vocal Robotizer + Acoustic Guitar Backing Pipeline

## Project Summary
A software pipeline that takes an input song/vocal audio file and produces a new
mix where:
1. The original vocal is isolated from its background music.
2. The isolated vocal is transformed into a "robotic" voice.
3. A new acoustic guitar backing track is generated programmatically from a
   user-specified chord progression, key, and tempo.
4. The robotic vocal and the generated guitar backing are mixed into a final
   output audio file.

This is an **offline/batch pipeline**, not real-time. Input: an audio file.
Output: a processed audio file. No live mic input, no full AI singing-voice
synthesis (e.g. DiffSinger/VISinger) — the vocal always comes from a real
recording provided by the user, not generated from lyrics/melody alone.

## Pipeline Stages

### 1. Vocal / Instrumental Separation
- Goal: strip background instrumentation from the input song, leaving a clean
  vocal stem.
- Preferred tool: **Demucs** (Meta, open-source, high quality, runs on CPU).
- Fallback/alternative: **Spleeter** (Deezer, faster, slightly lower quality).
- Input: user-provided song file (mp3/wav).
- Output: isolated vocal stem (wav), and optionally the isolated instrumental
  stem (not used further in this pipeline, but useful for comparison/debug).

### 2. Robotize the Vocal
- Goal: apply a robotic voice effect to the isolated vocal stem.
- Candidate techniques (in rough order of simplicity):
  - **Ring modulation**: multiply the vocal signal by a fixed-frequency sine
    wave (~30-50 Hz for subtle, higher for metallic/Dalek-style).
  - **Vocoder effect**: use the vocal as a modulator over a synth carrier tone
    (e.g. sawtooth/square wave) to impose vocal formants onto a synthetic tone.
  - **Pitch quantization**: snap pitch to the nearest semitone very fast/hard
    (Auto-Tune-style robotic quality).
  - **Bitcrushing**: reduce bit depth / sample rate for a harsh digital lo-fi
    quality; can be layered with the above.
- Implementation: Python DSP using `numpy`/`scipy`/`librosa`. No external
  binaries required.
- Should be modular/parameterized so different robot "flavors" can be selected
  or combined (e.g. `--effect ring_mod --freq 40`).

### 3. Programmatic Acoustic Guitar Backing Track
- Goal: generate a new acoustic guitar backing track from a user-specified
  chord progression, key, and tempo (no chord/key auto-detection from audio —
  user provides these explicitly).
- Approach (chosen): **MIDI + soundfont rendering**
  - Programmatically generate a chord/strum pattern as MIDI based on the
    user's chord progression, key, tempo (BPM), and time signature.
  - Render the MIDI through `fluidsynth` using a free acoustic guitar
    soundfont (sourced from GitHub or another allowed host).
  - Rationale: this gets a convincingly real acoustic guitar tone quickly,
    since the soundfont uses sampled real guitar recordings.
- Deferred/optional future upgrade: **Karplus-Strong physical modeling
  synthesis** for fully synthesized (non-sampled) guitar tone with more low-
  level control over string behavior. Noted as a "phase 2" idea — not part of
  the initial build, since tuning it to sound convincingly acoustic (body
  resonance, string coupling, pick/finger noise) is a substantial task on its
  own.

### 4. Mixing
- Goal: combine the robotized vocal stem and the generated guitar backing
  track into a single final audio file.
- Implementation: `pydub` or `soundfile`/`numpy` for level balancing, timing
  alignment, and export.
- Output: final mixed audio file (wav/mp3).

## User-Provided Inputs (per run)
- Source audio file (song or vocal recording) to robotize.
- Chord progression (e.g. `C - G - Am - F`).
- Key.
- Tempo (BPM) — if not provided, may need to be derived (e.g. via `librosa`
  tempo estimation) or set manually.
- Time signature (assume 4/4 unless specified).
- Desired robot voice style/effect parameters (optional, can default to a
  preset).

## Environment Notes / Constraints
- Built and tested inside a sandboxed container: no persistent storage across
  sessions, limited network access (only specific allowlisted domains),
  CPU only (no GPU).
- Demucs runs acceptably on CPU but is slower than GPU (a few minutes for a
  typical song length).
- Any soundfont file needed for guitar rendering must be sourced from an
  allowed domain (e.g. GitHub) since not all hosts are reachable.
- Deliverable should be handed to the user as standalone Python script(s) /
  files so they can install dependencies and run the pipeline on their own
  machine going forward, not just as a one-off run in this session.

## Suggested Project Structure
```
robo-singer/
├── separate.py        # Stage 1: Demucs-based vocal/instrumental separation
├── robotize.py        # Stage 2: robotic voice effects (ring mod, vocoder, etc.)
├── guitar_backing.py  # Stage 3: chord progression -> MIDI -> soundfont render
├── mix.py             # Stage 4: combine vocal + guitar into final mix
├── pipeline.py         # Orchestrates all stages end-to-end via CLI
├── requirements.txt
└── README.md
```

## Explicitly Out of Scope (for now)
- Real-time processing (live mic input -> live robot voice output).
- Full AI vocal synthesis from lyrics/melody alone (no reference recording).
- Automatic chord/key detection from audio (user specifies these manually).
- Physical/hardware robot integration (this is a software-only voice/audio
  project).
