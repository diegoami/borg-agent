"""Replay, verify and branch (R5).

The engine is deterministic given the recorded actions, so a run can be played
again without the mind that made it. `verify` does that and compares the
outcome and the state at every observation; `branch` replays to a turn and
then hands over to another mind, which is what a mode B post-mortem does.
"""
import json
from pathlib import Path

from . import agent, mind as mind_module, play, record
from .build import sha
from .signals import StreamEnded

VERIFY_NAME = 'verify.json'


def recorded_actions(run_dir):
    """The action stream of a finished run, in order."""
    path = Path(run_dir) / agent.ACTION_LOG
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class ReplayMind:
    """Feeds a recorded action stream back, and notices when the game diverges.

    It compares the state it is shown with the state the original run was shown
    at the same decision (R5's state hashes), so a divergence is reported where
    it happens rather than as a different outcome at the end.
    """

    name = 'replay'
    kind = 'replay'

    def __init__(self, actions, state_hashes=None, then=None, until_turn=None):
        self.actions = list(actions)
        self.state_hashes = list(state_hashes or [])
        self.then = then            # the mind that takes over after `until_turn`
        self.until_turn = until_turn
        self.decisions = 0
        self.replayed = 0
        self.divergence = None
        self.handed_over_at = None

    @property
    def handed_over(self):
        return self.handed_over_at is not None

    def drain_journal(self):
        """The journal of the mind that took over, if it keeps one.

        A branch's own decisions are the interesting ones — mode B is "replay,
        then try something else" — and they were being dropped because the run
        asks the outer mind, which is this one (found by the milestone 2
        re-review).
        """
        drain = getattr(self.then, 'drain_journal', None)
        return drain() if drain else []

    def act(self, observation):
        self.decisions += 1
        if self.until_turn is not None and observation['turn'] >= self.until_turn and self.then:
            if not self.handed_over:
                self.handed_over_at = observation['turn']
            return self.then.act(observation)
        if self.replayed >= len(self.actions):
            # The stream ran out while the game was still asking. For a run the
            # harness ended — a cap, a stall — that is the expected end of the
            # replay, not a divergence; `verify` reads it that way. Either way
            # no action is invented here.
            raise StreamEnded(self.replayed, observation['turn'])
        action = self.actions[self.replayed]
        self.replayed += 1
        return action


# A run the game itself ended can be replayed to the same end; one the harness
# ended stops where the recording stops, because the game would have played on
# (R2.3). The two are verified differently, and conflating them was finding 1
# of the milestone 2 review.
GAME_ENDED = ('death', 'completion', 'turn_cap', 'saved')


def check_record_against_run(recorded, run_dir, actions):
    """Is the run beside this record still the run the record describes?

    Every count and hash the record published is compared with the file it
    was taken from. Without the counts, a run could be shortened at the end —
    the replay would reproduce the states that remained and `prefix` would
    accept it — while the record still claimed the longer stream.

    Returns (matches, reason). `matches` is None when the record published
    nothing to compare.
    """
    run_dir = Path(run_dir)
    stream = recorded.get('action_stream') or {}
    evidence = recorded.get('evidence') or {}
    checks = [
        ('the action stream', stream.get('sha256'), run_dir / agent.ACTION_LOG),
        ('the observations', evidence.get('observations_sha256'),
         run_dir / agent.OBSERVATION_LOG),
        ('the state hashes', evidence.get('state_hashes_sha256'),
         run_dir / record.STATE_HASHES_NAME),
        ('the journal', evidence.get('journal_sha256'), run_dir / agent.JOURNAL_LOG),
        # The stream this milestone added. T16's rule is every count and hash
        # the record published, and the model calls were left out of it
        # (milestone 3 review, finding 2).
        ('the model calls', evidence.get('model_calls_sha256'),
         run_dir / agent.MODEL_CALL_LOG),
    ]
    compared = False
    for what, published, path in checks:
        if not published:
            continue
        if not path.exists():
            return False, f'the record names {what}, but {path.name} is not beside the run'
        compared = True
        if sha(path) != published:
            return False, f'{what} is not what the record published ({path.name})'
    if stream.get('count') is not None:
        compared = True
        if stream['count'] != actions:
            return False, (f"the record says {stream['count']} actions, but "
                           f'{agent.ACTION_LOG} holds {actions}')
    # The count is published in `usage` even when the hash is not, so it is
    # checked on its own.
    published_calls = (recorded.get('usage') or {}).get('model_calls')
    if published_calls:
        compared = True
        log = run_dir / agent.MODEL_CALL_LOG
        if not log.exists():
            return False, (f'the record says {published_calls} model calls, but '
                           f'{agent.MODEL_CALL_LOG} is not beside the run')
        calls = len([line for line in log.read_text().splitlines() if line.strip()])
        if calls != published_calls:
            return False, (f'the record says {published_calls} model calls, but '
                           f'{agent.MODEL_CALL_LOG} holds {calls}')
    return (True if compared else None), None


def verify(run_dir, output, timeout=900, stall_timeout=120, lock=True, log=print):
    """Replay a run without its mind and confirm it reproduces (R5).

    Compares, decision by decision, the state hash the agent was shown, and
    then the outcome, the final turn and the trace.

    How far the comparison can go depends on how the run ended:

    - the **game** ended it (a death, a cap on turns, a win): the replay must
      reach the same end, so every state hash, the outcome, the cause, the
      final turn and the trace must match. `scope` is `full`.
    - the **harness** ended it (a decision or budget cap, a stall, a wall
      limit, the agent giving up): the recording stops where the harness
      stopped it, and a replay runs out of actions one decision later, by
      which time the game has already been asked again. Every recorded state
      must match and the stream must end exactly where it did before.
      `scope` is `prefix`, and the outcome and trace are reported but not
      required to match, because they cannot.
    """
    run_dir, output = Path(run_dir), Path(output)
    original = json.loads((run_dir / 'result.json').read_text())
    record_path = run_dir / record.RECORD_NAME
    recorded = json.loads(record_path.read_text()) if record_path.exists() else None
    actions = recorded_actions(run_dir)
    before = record.state_hashes(run_dir / 'observations.jsonl')
    replay_mind = ReplayMind(actions)
    result = agent.play_with_mind(
        build_out=pins_build(original), seed=original['seed'], cap=original['turn_cap'],
        output=output, mind=replay_mind, timeout=timeout, stall_timeout=stall_timeout,
        decision_cap=max(len(actions) + 1, 2),
        # A post-mortem's recorded actions start at the handover: the Borg
        # plays the prefix again, which it does the same way every time, and
        # the stream replays from there (mode B).
        from_turn=original.get('from_turn'),
        validate=False, lock=lock, log=lambda *a: None)
    after = record.state_hashes(output / 'observations.jsonl')
    scope = 'full' if original['outcome'] in GAME_ENDED else 'prefix'
    first_difference = next((i for i, (a, b) in enumerate(zip(before, after)) if a != b), None)
    # Every state the original run saw must appear, in order, in the replay.
    states_match = bool(before) and before == after[:len(before)]
    stream_ended = result.get('stream_ended')
    verdict = {
        'schema': 'borg-agent/verify@1',
        'run': original.get('run_id') or run_dir.name,
        'run_record': str(record_path) if recorded else None,
        'replay': str(output),
        'scope': scope,
        'actions': len(actions),
        'from_turn': original.get('from_turn'),
        'decisions': [len(before), len(after)],
        'outcome': [original['outcome'], result['outcome']],
        'final_turn': [original.get('final_turn'), result.get('final_turn')],
        'cause': [original.get('cause'), result.get('cause')],
        'trace_sha256': [original.get('trace_sha256'), result.get('trace_sha256')],
        'state_hashes_match': states_match,
        'first_differing_decision': first_difference,
        'stream_ended': stream_ended,
        'calendar': [original['calendar']['utc'], result['calendar']['utc']],
        'seasonal': [original['calendar'].get('seasonal'), result['calendar'].get('seasonal')],
    }
    if recorded:
        # The record is checked against the run as well, not only the run
        # against its replay. Every stream the record published a hash or a
        # count for must still be the file the replay read: a consistent cut
        # of the end of both logs used to pass `prefix`, with the intact
        # record making it look endorsed (found by the milestone 2
        # re-review).
        verdict['record_matches_run'], verdict['record_mismatch'] = \
            check_record_against_run(recorded, run_dir, len(actions))
    if verdict['seasonal'][0] != verdict['seasonal'][1]:
        # The game's monster table differs on 24-26 December, so this replay
        # was never going to match and its result says nothing about the run.
        verdict['comparable'] = False
        verdict['verified'] = False
        verdict['incomparable_because'] = (
            'the run and the replay fall on different sides of the seasonal window '
            '(24-26 December): the game admits different monsters, so the same seed '
            'plays a different game. Replay it on a day of the same kind.')
        (output / VERIFY_NAME).write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
        log(json.dumps({k: verdict[k] for k in ('run', 'verified', 'comparable',
                                                'incomparable_because')}))
        return verdict
    verdict['comparable'] = True
    if verdict.get('record_matches_run') is False:
        verdict['verified'] = False
        verdict['failed_because'] = verdict['record_mismatch']
    elif scope == 'full':
        verdict['verified'] = bool(
            states_match and len(after) == len(before)
            and original['outcome'] == result['outcome']
            and original.get('final_turn') == result.get('final_turn')
            and original.get('cause') == result.get('cause')
            and original.get('trace_sha256') == result.get('trace_sha256'))
        if not verdict['verified']:
            verdict['failed_because'] = ('the replay did not reach the same end as the run'
                                         if states_match else
                                         'the replay diverged from the run')
    else:
        # The harness ended the run, so the replay ends with the stream. It may
        # see one observation more: the game asks again, and there is nothing
        # recorded to answer with.
        ended_where_it_should = bool(stream_ended
                                     and stream_ended['decisions'] == len(before))
        verdict['verified'] = bool(states_match
                                   and len(after) in (len(before), len(before) + 1)
                                   and ended_where_it_should)
        if not verdict['verified']:
            verdict['failed_because'] = (
                'the replay diverged from the run' if not states_match else
                f'the recorded stream ended at {stream_ended and stream_ended.get("decisions")} '
                f'decisions, not at the {len(before)} the run recorded')
        else:
            verdict['verified_as'] = (
                f'every one of the {len(before)} recorded states reproduced, and the stream '
                f'ended where the harness ended the run ({original["outcome"]})')
    (output / VERIFY_NAME).write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
    log(json.dumps({k: verdict.get(k) for k in
                    ('run', 'verified', 'scope', 'outcome', 'decisions',
                     'first_differing_decision', 'failed_because')}))
    return verdict


def pins_build(result):
    """The build a recorded run was played with, by its key."""
    from . import build as build_module
    out = build_module.BUILD_ROOT / result['build_key']
    if not build_module.is_current(out, result['recipe']):
        raise ValueError(f'the build {result["build_key"]} this run used is not here; '
                         'run `python -m borg_agent build` with the same pins and bridge')
    return out


def branch(run_dir, turn, output, new_mind, timeout=900, stall_timeout=120, lock=True,
           log=print):
    """Replay to `turn`, then play on with another mind (R5, and mode B)."""
    run_dir, output = Path(run_dir), Path(output)
    original = json.loads((run_dir / 'result.json').read_text())
    actions = recorded_actions(run_dir)
    # A post-mortem's recorded actions start at its handover turn, so a branch
    # of one has to play the same prefix before the stream means anything --
    # exactly what `verify` does above. Without this the stream was fed to a
    # newborn character in town and the branch recorded a different game under
    # the parent's name (milestone 3 review, finding 1).
    from_turn = original.get('from_turn')
    if from_turn and turn < from_turn:
        raise ValueError(
            f'this run took over at turn {from_turn}, so it has no recorded actions at turn '
            f'{turn}: branch at {from_turn} or later, or branch the run it came from')
    branching = ReplayMind(actions, then=new_mind, until_turn=turn)
    result = agent.play_with_mind(
        build_out=pins_build(original), seed=original['seed'], cap=original['turn_cap'],
        output=output, mind=branching, timeout=timeout, stall_timeout=stall_timeout,
        from_turn=from_turn, lock=lock, log=lambda *a: None)
    parent = {'run_id': original.get('run_id') or run_dir.name,
              'turn': branching.handed_over_at if branching.handed_over else turn}
    result['parent'] = parent
    result['branch'] = {'requested_turn': turn,
                        'handed_over_at': branching.handed_over_at,
                        'replayed_actions': branching.replayed,
                        'parent_from_turn': from_turn,
                        'mind': new_mind.name}
    (output / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    log(json.dumps({'branch_of': parent, 'outcome': result['outcome'],
                    'final_turn': result.get('final_turn'),
                    'replayed': branching.replayed, 'mind': new_mind.name}))
    return result, parent


# --- reading a recorded run -------------------------------------------------

def observations(run_dir):
    path = Path(run_dir) / agent.OBSERVATION_LOG
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def at_turn(run_dir, turn):
    """The last observation at or before `turn`, with its index."""
    found = None
    for index, observation in enumerate(observations(run_dir)):
        if observation['turn'] <= turn:
            found = (index, observation)
        else:
            break
    if found is None:
        raise ValueError(f'no observation at or before turn {turn}')
    return found


def view(run_dir, turn):
    """The screen as the player saw it (R5)."""
    index, observation = at_turn(run_dir, turn)
    return index, observation, '\n'.join(observation.get('screen') or [])


def dump(run_dir, turn):
    """The observation at a turn (R5)."""
    return at_turn(run_dir, turn)


def journal(run_dir):
    """The chooser's decisions and the executor's stop reasons, if any."""
    path = Path(run_dir) / agent.JOURNAL_LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def explain(run_dir, turn, window=3):
    """What was decided around a turn, and why (R5).

    The command the game was sent, the reason given with it, and — when a
    chooser was picking primitives — what it chose, why, and why the previous
    primitive stopped. With a model mind the model call joins the same line
    (T06).
    """
    observed = observations(run_dir)
    actions = recorded_actions(run_dir)
    entries = journal(run_dir)
    index, _ = at_turn(run_dir, turn)
    lines = []
    for i in range(max(0, index - window), min(len(observed), index + window + 1)):
        observation = observed[i]
        action = actions[i] if i < len(actions) else None
        decided = [entry for entry in entries if entry.get('decision') == observation['decision']]
        lines.append({
            'decision': observation['decision'],
            'turn': observation['turn'],
            'depth': observation['character']['depth'],
            'hp': f"{observation['character']['hp']}/{observation['character']['max_hp']}",
            'messages': observation['messages'],
            'action': action and {k: v for k, v in action.items() if k not in ('schema',)},
            'chose': [{'kind': entry['kind'],
                       'what': entry.get('chose') or entry.get('stop'),
                       'why': (entry.get('answer') or {}).get('reason'),
                       'primitive': entry.get('primitive'),
                       'after_stop': entry.get('after_stop')}
                      for entry in decided] or None,
            'current': i == index,
        })
    return lines
