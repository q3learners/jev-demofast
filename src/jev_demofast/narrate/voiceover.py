"""The founder's voice-over as one continuous piece of speech, with [NN] markers where each recorded moment comes up:
"[00] Finding a shoe should take seconds, so watch this. [01] Everything for men lives up here... [02] [03] and there
it is." Two markers can sit side by side for a quick step with no words of its own. Words before the first marker
belong to the opening."""
import re

MARK = re.compile(r"\[(\d\d)\]")


def _pieces(text):
    """[(segment id, its words)] in order, the words before the first marker joined to the first segment."""
    parts = MARK.split(text)
    pre, pairs = parts[0], list(zip(parts[1::2], parts[2::2]))
    if pairs:
        pairs[0] = (pairs[0][0], f"{pre} {pairs[0][1]}")
    return [(sid, " ".join(words.split())) for sid, words in pairs]


def split(text, ids):
    """{segment id: its words} when the markers are exactly `ids`, once each and in order; otherwise None."""
    pieces = _pieces(text or "")
    if [sid for sid, _ in pieces] != list(ids):
        return None
    return dict(pieces)


def plain(text):
    """(the words to speak, without markers; [(segment id, where in those words its own words start)]). A marker
    with no words of its own starts where the next words do."""
    spoken, marks, waiting = "", [], []
    for sid, words in _pieces(text):
        waiting.append(sid)
        if words:
            if spoken:
                spoken += " "
            marks += [(w, len(spoken)) for w in waiting]
            waiting = []
            spoken += words
    marks += [(w, len(spoken)) for w in waiting]
    if marks:
        marks[0] = (marks[0][0], 0)
    return spoken, marks
