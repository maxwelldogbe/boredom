"""Answer normalization shared by Guess Race and Name It."""

import re
import unicodedata

_LEADING_THE = re.compile(r"^the\s+")
_NOT_ALNUM = re.compile(r"[\W_]+")


def normalize(s: str) -> str:
    """Lowercase, trim, strip a leading "the", then drop punctuation and whitespace.

    "  The Lion King! " -> "lionking"; "Schindler's List" -> "schindlerslist";
    "Theater" keeps its "the" because the word is not followed by a space.
    """
    text = unicodedata.normalize("NFKC", s).lower().strip()
    text = _LEADING_THE.sub("", text)
    return _NOT_ALNUM.sub("", text)
