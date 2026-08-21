"""Tests for CompiledChainCache (bug fix, not a planned slice).

Regression coverage for a real bug: the live audio callback was calling
CompileChain fresh on every ~21ms block, which is expensive enough (e.g.
constructing a pedalboard plugin per call) to cause audible output
underflow/input overflow. CompiledChainCache must recompile only when the
active Voice actually changes, identified by id.
"""
from voice_engine.engine import CompiledChainCache
from voice_engine.voice import Voice


def test_CompiledChainCacheRecompilesOnlyWhenVoiceIdChanges() -> None:
    sampleRate = 48000
    cache = CompiledChainCache(sampleRate)
    voiceA = Voice(id="a", name="A", default=False, chain=[])
    voiceB = Voice(id="b", name="B", default=False, chain=[])

    firstResult = cache.Get(voiceA)
    secondResult = cache.Get(voiceA)
    thirdResult = cache.Get(voiceB)

    assert firstResult is secondResult
    assert firstResult is not thirdResult
