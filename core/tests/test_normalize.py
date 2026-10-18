"""normalize(): lowercase, trim, strip punctuation/whitespace and a leading "the"."""

import pytest

from games.normalize import normalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Apple", "apple"),
        ("  apple  ", "apple"),
        ("The Lion King", "lionking"),
        ("the   lion king", "lionking"),
        ("THE MATRIX!!!", "matrix"),
        ("Lion King", "lionking"),
        ("Schindler's List", "schindlerslist"),
        ("Spider-Man", "spiderman"),
        ("E.T.", "et"),
        ("Theater", "theater"),
        ("Other The", "otherthe"),
        ("the", "the"),
        ("Fish & Chips", "fishchips"),
        ("snake_case", "snakecase"),
        ("Café", "café"),
        ("ｆｕｌｌｗｉｄｔｈ", "fullwidth"),
        ("", ""),
        ("  !!  ", ""),
        ("Tab\tand\nnewline", "tabandnewline"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_answer_and_alternative_meet() -> None:
    assert normalize("The Lion King") == normalize("lion king") == normalize("LION-KING")
