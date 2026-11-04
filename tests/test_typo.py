from collections import Counter

from app.services.search_v2 import fix_typos

VOCAB = Counter({"diabetes": 50, "mellitus": 40, "type": 90, "treated": 30, "tarlov": 5, "rare": 1})


def test_misspelled_words_snap_to_corpus_words():
    assert fix_typos("diabeets mellitus type 1", VOCAB) == "diabetes mellitus type 1"
    assert fix_typos("tralov cysts", VOCAB) == "tarlov cysts"


def test_known_short_and_unmatched_words_are_left_alone():
    assert fix_typos("how is rare diabetes treated", VOCAB) == "how is rare diabetes treated"
    assert fix_typos("zzzzzzzz", VOCAB) == "zzzzzzzz"
    assert fix_typos("diabeets", Counter()) == "diabeets"
