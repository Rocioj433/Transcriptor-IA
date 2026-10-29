from engines.schema import Segment, Transcript, Word


def test_transcript_roundtrip():
    transcript = Transcript(
        file_name="a.mp3",
        duration=10.0,
        language="es",
        model_used="large-v3-turbo",
        segments=[Segment(id=0, start=0.0, end=1.0, text="hola", speaker="A", words=[Word(0, "hola", 0.0, 1.0)])],
        warnings=["w"],
    )
    restored = Transcript.from_dict(transcript.to_dict())
    assert restored == transcript


def test_transcript_text_and_speakers():
    transcript = Transcript(
        file_name="a.mp3",
        duration=2.0,
        language="es",
        model_used="m",
        segments=[
            Segment(id=0, start=0.0, end=1.0, text=" uno ", speaker="A"),
            Segment(id=1, start=1.0, end=2.0, text="dos", speaker="B"),
            Segment(id=2, start=2.0, end=3.0, text="tres", speaker="A"),
        ],
    )
    assert transcript.text == "uno\ndos\ntres"
    assert transcript.speakers == ["A", "B"]


def test_empty_transcript_has_empty_text():
    transcript = Transcript(file_name="", duration=0.0, language="unknown", model_used="m")
    assert transcript.text == ""
    assert transcript.speakers == []
    assert transcript.to_dict()["segments"] == []


def test_segment_and_word_roundtrip():
    segment = Segment(
        id=3,
        start=1.5,
        end=2.5,
        text="hey",
        speaker="B",
        confidence=0.75,
        words=[Word(index=None, word="hey", start=1.5, end=2.5)],
    )
    assert Segment.from_dict(segment.to_dict()) == segment


def test_to_dict_exposes_optional_raw_segments():
    transcript = Transcript(
        file_name="a.mp3",
        duration=1.0,
        language="es",
        model_used="m",
        segments=[Segment(id=0, start=0.0, end=1.0, text="x")],
        raw_segments=[Segment(id=0, start=0.0, end=1.0, text="X")],
    )
    payload = transcript.to_dict()
    assert payload["raw_segments"][0]["text"] == "X"
    assert payload["segments"][0]["text"] == "x"
