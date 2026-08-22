"""Tests for the EQ (low/high shelf) Effect Step (Slice 23).

Verification (from SLICES.md, Slice 23):
- Given a chain containing an EQ Effect Step boosting a shelf band
- When a block containing a frequency inside that band and one outside it
  is processed through it
- Then the in-band frequency's amplitude increases relative to the
  out-of-band frequency's, compared to the unprocessed input

Verified in the frequency domain: a block is built from two superposed
sine tones -- one below a low-shelf cutoff (in-band, expected to be
boosted) and one well above it (out-of-band, expected to be left
essentially alone). The block is run through a compiled `eq` Effect Step
configured as a low-shelf boost, and the FFT magnitude of each tone is
compared before and after processing. The acceptance criteria is a
RELATIVE comparison -- in-band amplitude vs out-of-band amplitude,
before vs after -- so this checks the in-band/out-of-band magnitude
ratio increases after processing, not just that the in-band tone grew in
absolute terms.
"""
import numpy as np

from voice_engine.engine import CompileChain, ProcessChain
from voice_engine.voice import EffectStep


def test_EqStepBoostsLowShelfBandRelativeToOutOfBandFrequency() -> None:
    sampleRate = 48000
    durationSeconds = 1.0
    frameCount = int(sampleRate * durationSeconds)
    inBandFrequency = 100.0  # well inside a low-shelf band below cutoff
    outOfBandFrequency = 8000.0  # well above the shelf cutoff, untouched
    cutoffFrequencyHz = 400.0
    gainDb = 12.0

    time = np.arange(frameCount, dtype=np.float32) / sampleRate
    inBandTone = np.sin(2 * np.pi * inBandFrequency * time)
    outOfBandTone = np.sin(2 * np.pi * outOfBandFrequency * time)
    sineWave = (inBandTone + outOfBandTone).astype(np.float32)
    # Block shape/dtype matches sounddevice's indata/outdata convention:
    # float32, (frames, channels) — see tests/test_engine.py.
    block = sineWave.reshape(-1, 1)

    frequencyBins = np.fft.rfftfreq(frameCount, d=1.0 / sampleRate)
    inBandBin = np.argmin(np.abs(frequencyBins - inBandFrequency))
    outOfBandBin = np.argmin(np.abs(frequencyBins - outOfBandFrequency))

    inputSpectrum = np.abs(np.fft.rfft(block[:, 0]))
    inputInBandMagnitude = inputSpectrum[inBandBin]
    inputOutOfBandMagnitude = inputSpectrum[outOfBandBin]
    inputRatio = inputInBandMagnitude / inputOutOfBandMagnitude

    chain = [
        EffectStep(
            type="eq",
            params={
                "band": "low",
                "cutoff_frequency_hz": cutoffFrequencyHz,
                "gain_db": gainDb,
            },
        )
    ]
    compiledChain = CompileChain(chain, sampleRate)
    result = ProcessChain(compiledChain, block)

    assert result.dtype == np.float32
    assert result.shape == block.shape

    outputSpectrum = np.abs(np.fft.rfft(result[:, 0]))
    outputInBandMagnitude = outputSpectrum[inBandBin]
    outputOutOfBandMagnitude = outputSpectrum[outOfBandBin]
    outputRatio = outputInBandMagnitude / outputOutOfBandMagnitude

    # The in-band frequency's amplitude relative to the out-of-band
    # frequency's must increase after processing, compared to the
    # unprocessed input -- the actual acceptance criteria.
    assert outputRatio > inputRatio
