"""v6 research candidate: terminal alternatives to the v4rb baseline.

The fold/call model omits reraises and postflop bets. Do not use that proxy
to introduce a new investment that leaves a later hero betting decision.
This is a scope restriction, not a calibrated risk penalty or a strength claim.
"""
from .action_integration import IntegratedAction
from .action_model import candidate_actions
from .action_search import ActionSearchBot, search


def terminal_alternatives(obs, baseline):
    result = []
    coverage = max(p.street_bet + p.stack for p in obs.opponents)
    for action in candidate_actions(obs, baseline):
        # The baseline is always arm zero and remains available. Fold/check
        # add no investment. Calls/raises are alternatives only if hero is
        # all-in or covers every opponent's remaining effective stack.
        terminal = (action.kind in ('fold', 'check')
            or action.kind == 'call' and obs.legal.call_amount == obs.hero.stack
            or action.kind == 'raise_to' and action.amount >= min(
                obs.hero.street_bet + obs.hero.stack, coverage))
        if action == baseline or terminal:
            result.append(action)
    return tuple(result)


class TerminalSearchBot(ActionSearchBot):
    policy_name = 'v6'

    def run_search(self, *args):
        action, info = search(*args, prepared_factory=IntegratedAction,
                              action_factory=terminal_alternatives)
        info['model'] = 'exact_fold_call_terminal_alternatives'
        info['restriction'] = 'No new nonterminal investment; baseline always retained.'
        info['limitations'] += ' Baseline checkdown value remains a proxy; opponent response priors remain manual. Hero all-in does not prevent opponent side-pot betting.'
        return action, info
