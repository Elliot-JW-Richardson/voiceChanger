"""Tests for the `sawtooth_blend` Effect Step.

Added after real-hardware testing of `vocoder` (Slices 32-36) found it
destroyed voice intelligibility: `vocoder` discards the input block's own
waveform entirely and resynthesizes from only a detected pitch plus a
coarse per-band envelope, losing the actual harmonic/formant detail a
real voice needs to stay recognizable (see voice_engine/engine.py's
`CompileSawtoothBlendStep` docstring for the full reasoning).
`sawtooth_blend` takes the opposite approach: MIX a pitch-tracked
sawtooth into the voice instead of replacing the voice with one, so
intelligibility is never fully at the mercy of the carrier.

Verification (informal -- this Effect Step was added directly in response
to real-hardware findings, not through a SLICES.md slice):
- Given a chain containing a sawtooth_blend Effect Step at mix=0.0
- When a block is processed through it
- Then the output is an exact passthrough of the input (a graceful floor
  `vocoder` has no equivalent of)
- Given a chain containing a sawtooth_blend Effect Step at a moderate
  non-zero mix on a voiced (pitched) input block
- When that block is processed through it
- Then the output still correlates strongly with the original input
  (proving the voice itself is preserved, not replaced) while also
  showing clearly increased harmonic energy above the input's own (proving
  the sawtooth carrier's texture was actually added)
- Given an unvoiced (silent/no-clear-pitch) input block
- When it is processed through a sawtooth_blend Effect Step at a non-zero
  mix
- Then the output is an exact passthrough (no carrier mixed in -- see the
  UNVOICED FALLBACK note in CompileSawtoothBlendStep's docstring for why
  this differs deliberately from `vocoder`'s noise-carrier design)

Mix/tolerance values below were chosen by prototyping first (a scratch
script, not committed): at mix=0.1 on a 150Hz pure tone (SAMPLE_RATE=22050,
BLOCKSIZE=3072), correlation with the original input measured ~0.988 and
the output's 2nd-harmonic FFT-bin energy measured ~29.5 against the
input's own ~2.8 (~10.5x) -- comfortable margins for both assertions
below, not hopeful ones. Higher mix values (tried during prototyping,
e.g. 0.3+) can cause the sawtooth carrier to destructively interfere with
the voice's own phase at similar frequencies (correlation can even go
negative) -- expected given both signals are summed in the time domain,
and part of why this test deliberately uses a modest mix value rather
than the higher/more dramatic-sounding one a shipped Voice might
eventually use.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep

SAMPLE_RATE = 22050
BLOCKSIZE = 3072


def MakeSineBlock(frequency: float, amplitude: float = 0.3) -> np.ndarray:
    time = np.arange(BLOCKSIZE) / SAMPLE_RATE
    return (amplitude * np.sin(2 * np.pi * frequency * time)).astype(np.float32).reshape(-1, 1)


def test_SawtoothBlendStepAtZeroMixIsExactPassthrough() -> None:
    block = MakeSineBlock(150.0)

    chain = [EffectStep(type="sawtooth_blend", params={"mix": 0.0})]
    compiledStep = CompileChain(chain, SAMPLE_RATE)[0]

    result = ProcessChain([compiledStep], block)

    np.testing.assert_array_equal(result, block)


def test_SawtoothBlendStepPreservesVoiceWhileAddingHarmonicTexture() -> None:
    frequency = 150.0
    block = MakeSineBlock(frequency)

    chain = [EffectStep(type="sawtooth_blend", params={"mix": 0.1})]
    compiledStep = CompileChain(chain, SAMPLE_RATE)[0]

    result = ProcessChain([compiledStep], block)

    correlation = np.corrcoef(block[:, 0], result[:, 0])[0, 1]
    assert correlation > 0.95

    freqs = np.fft.rfftfreq(BLOCKSIZE, 1 / SAMPLE_RATE)
    secondHarmonicBin = np.argmin(np.abs(freqs - 2 * frequency))
    inputSpectrum = np.abs(np.fft.rfft(block[:, 0]))
    outputSpectrum = np.abs(np.fft.rfft(result[:, 0]))
    assert outputSpectrum[secondHarmonicBin] > 5 * inputSpectrum[secondHarmonicBin]


def test_SawtoothBlendStepIsPassthroughOnUnvoicedInput() -> None:
    silentBlock = np.zeros((BLOCKSIZE, 1), dtype=np.float32)

    chain = [EffectStep(type="sawtooth_blend", params={"mix": 0.5})]
    compiledStep = CompileChain(chain, SAMPLE_RATE)[0]

    result = ProcessChain([compiledStep], silentBlock)

    np.testing.assert_array_equal(result, silentBlock)
