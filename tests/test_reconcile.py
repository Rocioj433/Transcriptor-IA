from core.diarizer.base import SpeakerSpan
from core.diarizer.reconcile import dominant_speaker, overlap, reconcile_speakers
from engines.schema import Segment


def segment(start: float, end: float, speaker=None) -> Segment:
    return Segment(id=0, start=start, end=end, text="x", speaker=speaker)


def test_overlap_math():
    assert overlap(0, 5, 3, 9) == 2
    assert overlap(0, 1, 2, 3) == 0
    assert overlap(0, 10, 0, 10) == 10


def test_dominant_speaker_uses_largest_overlap():
    spans = [SpeakerSpan(0, 6, "A"), SpeakerSpan(6, 10, "B")]
    assert dominant_speaker(segment(0, 5), spans) == "A"
    assert dominant_speaker(segment(5, 10), spans) == "B"


def test_tie_goes_to_earliest_span():
    spans = [SpeakerSpan(5, 10, "B"), SpeakerSpan(0, 5, "A")]
    assert dominant_speaker(segment(0, 10), spans) == "A"


def test_gap_keeps_speaker_none():
    spans = [SpeakerSpan(0, 2, "A")]
    assert dominant_speaker(segment(5, 6), spans) is None


def test_reconcile_assigns_and_preserves_other_fields():
    spans = [SpeakerSpan(0, 6, "A"), SpeakerSpan(6, 10, "B")]
    segments = [segment(0, 5), segment(5, 10)]
    reconciled = reconcile_speakers(segments, spans)
    assert [item.speaker for item in reconciled] == ["A", "B"]
    assert segments[0].speaker is None  # inputs are not mutated
    assert reconciled[0].text == "x"


def test_reconcile_with_no_spans_leaves_speakers_unset():
    reconciled = reconcile_speakers([segment(0, 1)], [])
    assert reconciled[0].speaker is None
