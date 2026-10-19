import re

_LABEL = re.compile(r"^([A-Za-z]+)(\d+)(.*)$", re.DOTALL)


def label_sort_key(label):
    """Natural sort key for sector labels: letter, then the number as an integer, then the suffix as a string.

    B505 < B1012 < C99 < C868 < C868-599-140 < C1000 < K20 < K142 and K142 < K142_A < K142_B.
    Labels of any other shape (MIX, a bare id, an empty or missing label) sort after the matching ones, by plain string.
    """
    text = "" if label is None else str(label)
    match = _LABEL.match(text)
    if match:
        return (0, match.group(1), int(match.group(2)), match.group(3))
    return (1, text, 0, "")
