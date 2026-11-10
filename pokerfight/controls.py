"""Public-contract adapter around the isolated v1/v2 implementation."""
from dataclasses import asdict
from time import perf_counter
from types import SimpleNamespace

from .domain import Action
from .equity import EquityResult
from .strategy import BotConfig, Decision, PokerBot
from .frozen_v2 import strategy as frozen
from .frozen_v2.domain import Observation as FrozenObservation


class ControlBot(PokerBot):
    """Copy at the boundary: no live charts, sampler or model enter the control."""

    def __init__(self, config: BotConfig, legacy: bool = False, extended_budget: bool = False):
        self.config = config
        factory = frozen.LegacyPokerBot if legacy else frozen.PokerBot
        # v2mc changes ONLY the allowed compute envelope; frozen algorithms and
        # selection stay byte-identical. Ordinary v1/v2 retain their old limits.
        settings = SimpleNamespace(**asdict(config)) if extended_budget else frozen.BotConfig(**asdict(config))
        self.control = factory(settings)
        self.model = self.control.model

    def decide(self, obs):
        started = perf_counter()
        result = self.control.decide(FrozenObservation.from_dict(asdict(obs)))
        equity = EquityResult(**asdict(result.equity)) if result.equity else None
        return Decision(Action(result.action.kind, result.action.amount), result.reason,
                        (perf_counter() - started) * 1000, result.fallback, equity)
