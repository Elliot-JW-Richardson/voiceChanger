"""Tests for the vocoder Effect Step's pitch-tracked sawtooth carrier
(Slice 33).

Verification (from SLICES.md, Slice 33):
- Given a chain containing a vocoder Effect Step and a two-block input
  where the detected pitch differs between the blocks
- When the blocks are processed through it
- Then each output block's dominant frequency matches that block's own
  detected input pitch, and the output's spectrum shows the rich
  multi-harmonic structure of a sawtooth wave rather than a single sine
  tone

This is Band 7's second slice (see CONTEXT.md's "Vocoder Effect Step (v2,
scoped -- see ADR 0004)" entry and docs/adr/0004-vocoder-over-tuned-ring-
mod.md): Slice 32's `DetectPitch` (voice_engine/pitch_tracker.py) is the
first stage, called once per block; this Effect Step is the second stage,
replacing the block's own waveform with a sawtooth oscillator synthesized
at that block's own detected fundamental. A pitched-but-not-yet-envelope-
shaped carrier is a genuine, audible milestone in its own right (envelope
shaping lands in Slice 34, unvoiced/noise-carrier handling in Slice 35 --
neither is this slice's job).

TEST APPROACH -- two numerical estimation steps are chained here
(autocorrelation pitch detection on the input, then FFT peak-bin
detection on the sawtooth output), each with its own quantization error,
so this test compares the output against the ACTUAL detected input pitch
(what `DetectPitch` reports on the raw input, called directly -- exactly
what the acceptance criteria means by "that block's own detected input
pitch"), not the nominal synthetic tone frequency. This mirrors
tests/test_pitch_shift_step.py's exact technique for reading a block's
dominant frequency: `numpy.fft.rfft` + `numpy.fft.rfftfreq`, argmax of
the magnitude spectrum.

BLOCK LENGTH: SAMPLE_RATE=22050 / BLOCKSIZE=3072, this project's live
audio settings (see CLAUDE.md's Real-time performance notes) and the
exact block length tests/test_pitch_tracker.py already validated
`DetectPitch` against -- long enough for both autocorrelation (several
periods of even a 150Hz tone) and a clean FFT peak-bin read (bin width
SAMPLE_RATE/BLOCKSIZE =~ 7.18Hz).

TEST FREQUENCIES: 150Hz and 300Hz, well inside `DetectPitch`'s searched
50-500Hz range and well separated from each other (double), so a
per-block-tracking carrier is clearly distinguishable from a stuck fixed
one. A scratch prototype (not committed) of this exact
DetectPitch-then-sawtooth-then-FFT-peak chain at this sample
rate/block size found detected pitches of 150.0Hz and ~302.05Hz for
150Hz/300Hz input sines (DetectPitch's own small quantization, already
established behavior per Slice 32), and sawtooth output dominant
frequencies within ~1Hz of each of those detected values -- comfortably
inside one FFT bin width. A 10Hz absolute tolerance below is therefore
generous, not hopeful.

HARMONIC RICHNESS: the same prototype found the sawtooth output's energy
at the 2nd-harmonic bin (~2x the fundamental) roughly 35-40x the raw
input sine's energy at that same bin (a pure sine has only rounding-level
leakage there) -- checked below via a clear order-of-magnitude threshold
rather than an exact ratio, since the precise ratio isn't itself
meaningful, only that it is unambiguously present in the sawtooth and
unambiguously absent from the sine.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.pitch_tracker import DetectPitch
from voice_engine.voice import EffectStep

SAMPLE_RATE = 22050
BLOCKSIZE = 3072


def MakeSineBlock(frequency: float) -> np.ndarray:
    time = np.arange(BLOCKSIZE, dtype=np.float32) / SAMPLE_RATE
    sineWave = np.sin(2 * np.pi * frequency * time).astype(np.float32)
    return sineWave.reshape(-1, 1)


def DominantFrequency(signal: np.ndarray, sampleRate: int) -> float:
    spectrum = np.fft.rfft(signal)
    frequencyBins = np.fft.rfftfreq(len(signal), d=1.0 / sampleRate)
    return frequencyBins[np.argmax(np.abs(spectrum))]


def EnergyNearFrequency(signal: np.ndarray, sampleRate: int, targetFrequency: float) -> float:
    spectrum = np.fft.rfft(signal)
    frequencyBins = np.fft.rfftfreq(len(signal), d=1.0 / sampleRate)
    binIndex = int(np.argmin(np.abs(frequencyBins - targetFrequency)))
    return float(np.abs(spectrum[binIndex]))


def test_VocoderStepOutputTracksEachBlockOwnDetectedPitch() -> None:
    inputBlocks = [MakeSineBlock(150.0), MakeSineBlock(300.0)]
    groundTruthPitches = [DetectPitch(block, SAMPLE_RATE) for block in inputBlocks]

    # Both known synthetic tones must actually be detected cleanly by
    # DetectPitch (established behavior from Slice 32) -- otherwise this
    # test wouldn't be exercising per-block pitch TRACKING at all.
    assert groundTruthPitches[0] > 0.0
    assert groundTruthPitches[1] > 0.0
    assert groundTruthPitches[0] != groundTruthPitches[1]

    chain = [EffectStep(type="vocoder", params={})]
    compiledChain = CompileChain(chain, SAMPLE_RATE)

    outputDominantFrequencies = []
    for block in inputBlocks:
        result = ProcessChain(compiledChain, block)
        assert result.dtype == np.float32
        assert result.shape == block.shape
        outputDominantFrequencies.append(DominantFrequency(result[:, 0], SAMPLE_RATE))

    # Each output block's dominant frequency matches THAT block's own
    # detected input pitch -- proving per-block tracking, not a fixed
    # carrier reused across calls.
    assert abs(outputDominantFrequencies[0] - groundTruthPitches[0]) < 10.0
    assert abs(outputDominantFrequencies[1] - groundTruthPitches[1]) < 10.0

    # The two outputs clearly differ from each other by roughly the same
    # amount the two blocks' detected input pitches did -- a fixed
    # single-frequency carrier would produce (near-)identical outputs for
    # both blocks regardless of input pitch, failing this check.
    inputPitchDelta = groundTruthPitches[1] - groundTruthPitches[0]
    outputFrequencyDelta = outputDominantFrequencies[1] - outputDominantFrequencies[0]
    assert abs(outputFrequencyDelta - inputPitchDelta) < 20.0


def test_VocoderStepOutputHasRichHarmonicStructureUnlikeInputSine() -> None:
    inputBlock = MakeSineBlock(150.0)
    groundTruthPitch = DetectPitch(inputBlock, SAMPLE_RATE)
    assert groundTruthPitch > 0.0

    chain = [EffectStep(type="vocoder", params={})]
    compiledChain = CompileChain(chain, SAMPLE_RATE)
    result = ProcessChain(compiledChain, inputBlock)

    secondHarmonicFrequency = 2 * groundTruthPitch
    inputSecondHarmonicEnergy = EnergyNearFrequency(inputBlock[:, 0], SAMPLE_RATE, secondHarmonicFrequency)
    outputSecondHarmonicEnergy = EnergyNearFrequency(result[:, 0], SAMPLE_RATE, secondHarmonicFrequency)

    # A pure sine has only rounding-level leakage at its 2nd harmonic; a
    # sawtooth carries a genuine, much stronger harmonic there. Checked
    # as a clear order-of-magnitude threshold (>10x), not an exact ratio.
    assert outputSecondHarmonicEnergy > inputSecondHarmonicEnergy * 10.0


def MakeTwoToneBlock(fundamentalHz: float, harmonicHz: float, harmonicAmplitude: float) -> np.ndarray:
    time = np.arange(BLOCKSIZE, dtype=np.float32) / SAMPLE_RATE
    signal = np.sin(2 * np.pi * fundamentalHz * time) + harmonicAmplitude * np.sin(2 * np.pi * harmonicHz * time)
    return signal.astype(np.float32).reshape(-1, 1)


def EnergyInFrequencyRange(signal: np.ndarray, sampleRate: int, lowHz: float, highHz: float) -> float:
    spectrum = np.fft.rfft(signal)
    frequencyBins = np.fft.rfftfreq(len(signal), d=1.0 / sampleRate)
    inRange = (frequencyBins >= lowHz) & (frequencyBins <= highHz)
    return float(np.sum(np.abs(spectrum[inRange])))


def test_VocoderStepShapesCarrierWithEachInputsOwnFormantEnvelope() -> None:
    """Tests for Slice 34 (SLICES.md verification):

    - Given a chain containing a vocoder Effect Step and two different
      input signals that share the same pitch but differ in spectral/
      formant shape
    - When each is processed through it
    - Then the two outputs differ from each other in spectral shape,
      proving the carrier is shaped by each input's own envelope rather
      than output as a flat sawtooth, while both retain the same
      underlying pitch

    TEST SIGNAL DESIGN: both inputs share the same fundamental (150Hz,
    well inside DetectPitch's 50-500Hz search range) built from
    `sin(2*pi*f0*t) + 0.5*sin(2*pi*harmonic*t)` -- a stand-in for
    "differing formant shape" per the slice's TEST DESIGN GUIDANCE.
    `signalEmphasizingLowHarmonic` adds its extra energy at the 3rd
    harmonic (450Hz); `signalEmphasizingHighHarmonic` adds it at the 9th
    harmonic (1350Hz), matching ADR 0004's "dense near-complete harmonic
    series through at least the 9th harmonic" observation. A scratch
    prototype (not committed) of this exact two-tone-then-vocode-then-FFT
    chain at this sample rate/block size confirmed `DetectPitch` reports
    150.0Hz for BOTH signals despite the added harmonic emphasis
    (autocorrelation is robust to it, as expected) -- so both blocks are
    genuinely exercising the SAME pitch, only differing in shape.

    ASSERTIONS:
    - Both outputs' FFT dominant frequency stays close to the shared
      150Hz fundamental (and to each other) -- the carrier's underlying
      pitch survives envelope shaping.
    - Spectral-shape difference is checked via energy in two frequency
      REGIONS chosen independently of this implementation's own internal
      filter-bank band edges (a black-box check, per the slice's TEST
      DESIGN GUIDANCE): a +/-50Hz window around each input's emphasized
      harmonic. The same prototype found output-for-the-low-harmonic-
      input carries ~1.56x MORE energy in the low-harmonic region than
      output-for-the-high-harmonic-input does there, and output-for-the-
      high-harmonic-input carries ~1.80x more energy in the high-harmonic
      region than the other output does there -- checked below via a
      1.2x margin, comfortably inside both observed ratios, not a guess.
    """
    fundamentalHz = 150.0
    thirdHarmonicHz = 3 * fundamentalHz
    ninthHarmonicHz = 9 * fundamentalHz
    harmonicAmplitude = 0.5

    signalEmphasizingLowHarmonic = MakeTwoToneBlock(fundamentalHz, thirdHarmonicHz, harmonicAmplitude)
    signalEmphasizingHighHarmonic = MakeTwoToneBlock(fundamentalHz, ninthHarmonicHz, harmonicAmplitude)

    pitchOfLowHarmonicSignal = DetectPitch(signalEmphasizingLowHarmonic, SAMPLE_RATE)
    pitchOfHighHarmonicSignal = DetectPitch(signalEmphasizingHighHarmonic, SAMPLE_RATE)

    # Both signals must genuinely share the same detected pitch --
    # otherwise this test wouldn't isolate "differs in spectral shape"
    # from "differs because the pitch differs".
    assert pitchOfLowHarmonicSignal > 0.0
    assert pitchOfHighHarmonicSignal > 0.0
    assert abs(pitchOfLowHarmonicSignal - pitchOfHighHarmonicSignal) < 5.0

    chain = [EffectStep(type="vocoder", params={})]

    outputForLowHarmonicSignal = ProcessChain(CompileChain(chain, SAMPLE_RATE), signalEmphasizingLowHarmonic)
    outputForHighHarmonicSignal = ProcessChain(CompileChain(chain, SAMPLE_RATE), signalEmphasizingHighHarmonic)

    assert outputForLowHarmonicSignal.dtype == np.float32
    assert outputForHighHarmonicSignal.dtype == np.float32
    assert outputForLowHarmonicSignal.shape == signalEmphasizingLowHarmonic.shape
    assert outputForHighHarmonicSignal.shape == signalEmphasizingHighHarmonic.shape

    # Both outputs retain the same underlying pitch.
    dominantOfLowHarmonicOutput = DominantFrequency(outputForLowHarmonicSignal[:, 0], SAMPLE_RATE)
    dominantOfHighHarmonicOutput = DominantFrequency(outputForHighHarmonicSignal[:, 0], SAMPLE_RATE)
    assert abs(dominantOfLowHarmonicOutput - fundamentalHz) < 10.0
    assert abs(dominantOfHighHarmonicOutput - fundamentalHz) < 10.0
    assert abs(dominantOfLowHarmonicOutput - dominantOfHighHarmonicOutput) < 10.0

    # The two outputs differ in spectral shape: each carries relatively
    # more energy around the harmonic ITS OWN input emphasized, proving
    # the carrier was shaped by that input's own envelope rather than
    # both outputs being an identical flat sawtooth.
    lowHarmonicRegion = (thirdHarmonicHz - 50.0, thirdHarmonicHz + 50.0)
    highHarmonicRegion = (ninthHarmonicHz - 50.0, ninthHarmonicHz + 50.0)

    lowHarmonicRegionEnergyInLowOutput = EnergyInFrequencyRange(outputForLowHarmonicSignal[:, 0], SAMPLE_RATE, *lowHarmonicRegion)
    lowHarmonicRegionEnergyInHighOutput = EnergyInFrequencyRange(outputForHighHarmonicSignal[:, 0], SAMPLE_RATE, *lowHarmonicRegion)
    highHarmonicRegionEnergyInLowOutput = EnergyInFrequencyRange(outputForLowHarmonicSignal[:, 0], SAMPLE_RATE, *highHarmonicRegion)
    highHarmonicRegionEnergyInHighOutput = EnergyInFrequencyRange(outputForHighHarmonicSignal[:, 0], SAMPLE_RATE, *highHarmonicRegion)

    assert lowHarmonicRegionEnergyInLowOutput > lowHarmonicRegionEnergyInHighOutput * 1.2
    assert highHarmonicRegionEnergyInHighOutput > highHarmonicRegionEnergyInLowOutput * 1.2


def MakeNoiseBlock(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, size=(BLOCKSIZE, 1)).astype(np.float32)


def PeakToAverageRatio(signal: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(signal))
    return float(np.max(spectrum) / np.mean(spectrum))


def test_VocoderStepUsesNoiseCarrierForUnvoicedInputButSawtoothForPitchedInput() -> None:
    """Tests for Slice 35 (SLICES.md verification):

    - Given a chain containing a vocoder Effect Step and an input block
      that is noise-like with no clear pitch
    - When it is processed through it
    - Then the output is noise-carrier-based rather than a tonal sawtooth
      at some spuriously detected pitch, while a separate clearly-pitched
      block in the same test still produces the pitched sawtooth carrier
      as before

    TEST SIGNAL DESIGN: the noise-like block is
    `np.random.default_rng(42).uniform(-1.0, 1.0, size=(BLOCKSIZE, 1))`
    -- genuine white noise, no periodicity for autocorrelation to lock
    onto. A scratch prototype (not committed) confirmed `DetectPitch`
    reports exactly 0.0 for this seed and 19 others tried (0-19), so this
    reliably exercises the unvoiced path rather than occasionally landing
    on a spurious weak peak. The pitched block reuses `MakeSineBlock`
    (150Hz), the same style Slices 33/34's tests above already use.

    SPECTRAL METRIC -- PEAK-TO-AVERAGE RATIO: `PeakToAverageRatio`
    computes the FFT magnitude spectrum's max bin divided by its mean
    bin -- a sharp, single-frequency tone (like a sawtooth's fundamental)
    concentrates most of its energy in one bin, giving a very high
    ratio; broadband noise spreads energy roughly evenly across bins,
    giving a low ratio close to 1. The same scratch prototype (running
    this exact noise block and a 150Hz/300Hz sawtooth-carrier block
    through this slice's own filter-bank shaping loop) found peak/average
    ratios of ~5-6 for the noise-carrier-shaped output across 3 different
    seeds, versus ~260-273 for the sawtooth-carrier-shaped output -- a
    ~45x gap. The thresholds below (<50 for noise, >100 for pitched) sit
    with wide, non-flaky margin on either side of that gap, not tuned to
    a hairline.

    NOT SILENCE: the same prototype found the noise-carrier-shaped
    output's RMS around ~0.06 -- well above a small floor -- confirming
    this slice's behavior (a shaped noise carrier) is genuinely different
    from the OLD `np.zeros_like(block)` fallback it replaces (which would
    have RMS exactly 0.0).
    """
    noiseBlock = MakeNoiseBlock(42)
    assert DetectPitch(noiseBlock, SAMPLE_RATE) == 0.0

    pitchedBlock = MakeSineBlock(150.0)
    groundTruthPitch = DetectPitch(pitchedBlock, SAMPLE_RATE)
    assert groundTruthPitch > 0.0

    chain = [EffectStep(type="vocoder", params={})]
    compiledChain = CompileChain(chain, SAMPLE_RATE)

    noiseOutput = ProcessChain(compiledChain, noiseBlock)
    pitchedOutput = ProcessChain(compiledChain, pitchedBlock)

    assert noiseOutput.dtype == np.float32
    assert noiseOutput.shape == noiseBlock.shape
    assert pitchedOutput.dtype == np.float32
    assert pitchedOutput.shape == pitchedBlock.shape

    # Noise-like input's output is NOT silence/near-zero -- distinguishing
    # this slice's noise-carrier behavior from the OLD np.zeros_like
    # fallback it replaces.
    noiseOutputRms = float(np.sqrt(np.mean(noiseOutput.astype(np.float64) ** 2)))
    assert noiseOutputRms > 0.01

    # Noise-like input's output lacks a single sharp dominant peak the way
    # a tonal sawtooth would -- it's broadband/noise-carrier-based.
    noiseOutputPeakToAverage = PeakToAverageRatio(noiseOutput[:, 0])
    assert noiseOutputPeakToAverage < 50.0

    # The separate, clearly-pitched block still produces a tonal sawtooth
    # carrier as before: a sharp dominant peak close to its own detected
    # input pitch.
    pitchedOutputPeakToAverage = PeakToAverageRatio(pitchedOutput[:, 0])
    assert pitchedOutputPeakToAverage > 100.0
    pitchedOutputDominantFrequency = DominantFrequency(pitchedOutput[:, 0], SAMPLE_RATE)
    assert abs(pitchedOutputDominantFrequency - groundTruthPitch) < 10.0
