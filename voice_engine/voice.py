"""Voice loader: parses a single Voice definition (see CONTEXT.md) into a
Voice.

A Voice definition describes an id, a display name, whether it is the
default Voice, and an ordered chain of declarative Effect Steps. This is
the declarative form only -- each Effect Step here is data (an effect
type plus its parameters), not the callable, compiled form
(`CompiledEffectStep`) used by `voice_engine.engine.ProcessChain` to
process audio blocks. Bridging from one to the other is out of scope for
this slice; it happens once concrete Effect Step types exist.

Voice definitions are stored as YAML, one file per Voice (see ADR 0001
and CONTEXT.md's Voice Bank entry), e.g.:

    id: passthrough
    name: Passthrough
    default: true
    chain: []

or with steps:

    id: example
    name: Example Voice
    default: false
    chain:
      - type: pitch_shift
        semitones: -6

Each chain entry's `type` key names the Effect Step type; every other key
on that entry becomes part of its `params`. No validation against a known
set of Effect Step types is performed here -- no concrete types exist
yet, and that validation arrives with each one in later slices. This
slice loads a single Voice definition (e.g. one file's content); scanning
a `voices/` directory to load many is Slice 3, which is expected to reuse
`LoadVoice` per discovered file path.
"""
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class EffectStep:
    """One declarative entry in a Voice's chain: an effect type plus its
    parameters. Not a callable -- see `voice_engine.engine.CompiledEffectStep`
    for the runtime, callable form later slices bridge to."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Voice:
    """A single loaded Voice: its id, display name, default flag, and
    ordered chain of declarative Effect Steps."""

    id: str
    name: str
    default: bool
    chain: list[EffectStep]


def ParseEffectStep(stepDefinition: dict[str, Any]) -> EffectStep:
    """Parse one raw chain entry (a dict with a `type` key and arbitrary
    other parameter keys) into an EffectStep."""
    effectType = stepDefinition["type"]
    params = {key: value for key, value in stepDefinition.items() if key != "type"}
    return EffectStep(type=effectType, params=params)


def LoadVoice(voiceFilePath: str) -> Voice:
    """Load a single Voice definition from the YAML file at
    `voiceFilePath` and parse it into a Voice, preserving its id, name,
    default flag, and ordered Effect Step chain.

    `voiceFilePath` points at one Voice definition file; Slice 3's
    directory scan is expected to discover many such paths and call this
    function once per path.
    """
    with open(voiceFilePath, "r", encoding="utf-8") as voiceFile:
        rawVoice = yaml.safe_load(voiceFile)

    chain = [ParseEffectStep(stepDefinition) for stepDefinition in rawVoice.get("chain", [])]

    return Voice(
        id=rawVoice["id"],
        name=rawVoice["name"],
        default=rawVoice.get("default", False),
        chain=chain,
    )
