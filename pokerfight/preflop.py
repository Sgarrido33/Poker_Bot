"""Hand-written starting charts; these are initial design parameters."""
from .cards import expand_range, hand_class

OPEN_RANGES = {
    "UTG": "66+,ATs+,KJs+,QJs,JTs,T9s,AJo+,KQo",
    "HJ": "55+,A8s+,KTs+,QTs+,JTs,T9s,98s,ATo+,KJo+,QJo",
    "CO": "44+,A2s+,K8s+,Q9s+,J9s+,T8s+,98s,87s,76s,A8o+,KTo+,QTo+,JTo",
    "BTN": "22+,A2s+,K2s+,Q6s+,J7s+,T7s+,97s+,86s+,75s+,65s,54s,A2o+,K8o+,Q9o+,J9o+,T9o",
    "SB": "22+,A2s+,K5s+,Q8s+,J8s+,T8s+,97s+,87s,76s,65s,A5o+,K9o+,QTo+,JTo",
    "BB": "22+,A2s+,K5s+,Q8s+,J8s+,T8s+,97s+,87s,76s,65s,A7o+,KTo+,QTo+,JTo",
}
DEFEND = "55+,A9s+,KTs+,QTs+,JTs,T9s,98s,AJo+,KQo"
BLIND_DEFEND = "22+,A2s+,K7s+,Q9s+,J9s+,T9s,98s,87s,76s,ATo+,KJo+,QJo"
PREMIUM = "QQ+,AKs,AKo"
SHORT_VALUE = "TT+,AQs+,AKo"


def in_range(cards: tuple[str, str], notation: str) -> bool:
    return hand_class(cards) in expand_range(notation)


def warm_charts() -> None:
    for notation in (*OPEN_RANGES.values(), DEFEND, BLIND_DEFEND, PREMIUM, SHORT_VALUE):
        expand_range(notation)
