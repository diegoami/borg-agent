"""How a mind can end a run.

Neither of these is a failure of the harness: the first is the agent giving
up, the second is a replay reaching the end of what was recorded. Both become
outcomes of R5's vocabulary, which is why they live apart from the modules
that raise them — `executor` and `replay` — and can be caught by `agent`
without either importing the other.
"""


class CannotAct(Exception):
    """Every primitive the mind chose stopped at once: the agent gave up.

    The run's outcome is `agent_stopped`, with this as the reason.
    """


class StreamEnded(Exception):
    """A replay ran out of recorded actions while the game asked for another.

    That is what happens when the run being replayed was ended by the harness
    — a decision or budget cap, a stall, a wall limit — rather than by the
    game: the game would have played on, and the recording simply stops. It is
    the expected end of such a replay, not a divergence (R2.3), and `verify`
    reads it as "the stream was replayed to its end".
    """

    def __init__(self, decisions, turn):
        self.decisions = decisions
        self.turn = turn
        super().__init__(f'the recorded action stream ended after {decisions} decisions, '
                         f'and the game asked again at turn {turn}')
