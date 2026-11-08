"""Replay, verify and branch (R5).

The engine is deterministic given the recorded actions, so a run can be played
again without the mind that made it. `verify` does that and compares the
outcome and the state at every observation; `branch` replays to a turn and
then hands over to another mind, which is what a mode B post-mortem does.
"""
import json
from pathlib import Path

from . import agent, mind as mind_module, play, record

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

    def act(self, observation):
        self.decisions += 1
        if self.until_turn is not None and observation['turn'] >= self.until_turn and self.then:
            if not self.handed_over:
                self.handed_over_at = observation['turn']
            return self.then.act(observation)
        if self.replayed >= len(self.actions):
            # The stream ran out before the game ended: say so rather than
            # inventing an action.
            raise ValueError(f'the recorded action stream ended at decision {self.replayed}, '
                             f'but the game asked again at turn {observation["turn"]}')
        action = self.actions[self.replayed]
        self.replayed += 1
        return action


def verify(run_dir, output, timeout=900, stall_timeout=120, lock=True, log=print):
    """Replay a run without its mind and confirm it reproduces (R5).

    Compares, decision by decision, the state hash the agent was shown, and
    then the outcome, the final turn and the trace.
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
        decision_cap=max(len(actions) + 1, 2), validate=False, lock=lock, log=lambda *a: None)
    after = record.state_hashes(output / 'observations.jsonl')
    first_difference = next((i for i, (a, b) in enumerate(zip(before, after)) if a != b), None)
    verdict = {
        'schema': 'borg-agent/verify@1',
        'run': original.get('run_id') or run_dir.name,
        'run_record': str(record_path) if recorded else None,
        'replay': str(output),
        'actions': len(actions),
        'decisions': [len(before), len(after)],
        'outcome': [original['outcome'], result['outcome']],
        'final_turn': [original.get('final_turn'), result.get('final_turn')],
        'cause': [original.get('cause'), result.get('cause')],
        'trace_sha256': [original.get('trace_sha256'), result.get('trace_sha256')],
        'state_hashes_match': before == after,
        'first_differing_decision': first_difference,
        'calendar': [original['calendar']['utc'], result['calendar']['utc']],
    }
    verdict['verified'] = bool(
        before and before == after
        and original['outcome'] == result['outcome']
        and original.get('final_turn') == result.get('final_turn')
        and original.get('cause') == result.get('cause')
        and original.get('trace_sha256') == result.get('trace_sha256'))
    (output / VERIFY_NAME).write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
    log(json.dumps({k: verdict[k] for k in
                    ('run', 'verified', 'outcome', 'decisions', 'first_differing_decision')}))
    return verdict


def pins_build(result):
    """The build a recorded run was played with, by its key."""
    from . import build as build_module
    out = build_module.BUILD_ROOT / result['build_key']
    if not build_module.is_current(out, result['recipe']):
        raise ValueError(f'the build {result["build_key"]} this run used is not here; '
                         'run `python -m borg_agent build` with the same pins and bridge')
    return out


def branch(run_dir, turn, output, new_mind, timeout=900, stall_timeout=120, lock=True, log=print):
    """Replay to `turn`, then play on with another mind (R5, and mode B)."""
    run_dir, output = Path(run_dir), Path(output)
    original = json.loads((run_dir / 'result.json').read_text())
    actions = recorded_actions(run_dir)
    branching = ReplayMind(actions, then=new_mind, until_turn=turn)
    result = agent.play_with_mind(
        build_out=pins_build(original), seed=original['seed'], cap=original['turn_cap'],
        output=output, mind=branching, timeout=timeout, stall_timeout=stall_timeout,
        lock=lock, log=lambda *a: None)
    parent = {'run_id': original.get('run_id') or run_dir.name,
              'turn': branching.handed_over_at if branching.handed_over else turn}
    result['parent'] = parent
    result['branch'] = {'requested_turn': turn,
                        'handed_over_at': branching.handed_over_at,
                        'replayed_actions': branching.replayed,
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


def explain(run_dir, turn, window=3):
    """What was decided around a turn, and why (R5).

    With a model mind this will also carry the model call; until T06 there is
    none, so it shows the action, its reason and any note.
    """
    observed = observations(run_dir)
    actions = recorded_actions(run_dir)
    index, _ = at_turn(run_dir, turn)
    lines = []
    for i in range(max(0, index - window), min(len(observed), index + window + 1)):
        observation = observed[i]
        action = actions[i] if i < len(actions) else None
        lines.append({
            'decision': observation['decision'],
            'turn': observation['turn'],
            'depth': observation['character']['depth'],
            'hp': f"{observation['character']['hp']}/{observation['character']['max_hp']}",
            'messages': observation['messages'],
            'action': action and {k: v for k, v in action.items() if k not in ('schema',)},
            'current': i == index,
        })
    return lines
