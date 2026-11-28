"""L2 — Turkish NLP Intelligence.

Turns a Turkish question into a :class:`ParsedQuestion` (intent, mentions,
temporal expressions, sort, limit, ambiguities) so that the small model
does not have to solve the linguistic problems alone.

The current implementation is rule-based (baseline for D4 in the ablation).
Zemberek / morphology-based analysis is evaluated in AR-03.
"""

from backend.turkish_nlp.normalize import tr_casefold
from backend.turkish_nlp.parser import RuleBasedTurkishParser

__all__ = ["RuleBasedTurkishParser", "tr_casefold"]
