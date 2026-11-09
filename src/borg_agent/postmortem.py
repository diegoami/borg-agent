"""Mode B: a recorded death, replayed to just before it, played differently (R3).

The cheapest knowledge per model call, the requirements say, because the game
has already done the expensive part: it has killed somebody, and said what
killed them.

How it works here, and why there is no save file involved: the **Borg's own
play is deterministic** (T01's gate), so a death is reproduced by playing the
same seed again. The bridge takes the agent's hand off the wheel until a turn
the caller names (`BORG_AGENT_FROM_TURN`), so the Borg plays the prefix of its
own game and the agent takes over k turns before the end it is known to come
to. Nothing has to be serialized, and a post-mortem is therefore replayable
like any other run: the prefix comes back by itself, and the recorded actions
replay from the handover.

Its cases are **deaths this build produces**. The pinned tree's own
`docs/deaths/` are richer — a verified replay, an assessment, an issue — but
they belong to older builds and to turns in the hundreds of thousands, so they
are a source to read (decision D8), not a case list.
"""
import json
from pathlib import Path

from . import agent, play, record

RECORD_NAME = 'post-mortem.json'
# How far before the death to hand over, unless the caller says otherwise: far
# enough that something could still be done, near enough that the agent sees
# the situation that killed the Borg.
DEFAULT_BEFORE = 200


def find_death(build_out, seed, cap, output, timeout=900, stall_timeout=120, lock=True,
               log=print):
    """Play the pinned Borg on a seed and report how it ended."""
    result = play.play(build_out, seed=seed, cap=cap, output=output, timeout=timeout,
                       stall_timeout=stall_timeout, lock=lock, log=log)
    return result


def death_of(run_dir):
    """The turn and cause of a recorded death, or None if it did not die."""
    result = json.loads((Path(run_dir) / 'result.json').read_text())
    if result['outcome'] != 'death':
        return None
    return {'run_id': result.get('run_id') or Path(run_dir).name,
            'seed': result['seed'],
            'turn': result.get('final_turn'),
            'cause': result.get('cause'),
            'turn_cap': result['turn_cap'],
            'trace_sha256': result.get('trace_sha256')}


def post_mortem(build_out, death, mind, output, before=DEFAULT_BEFORE, cap=None,
                timeout=900, stall_timeout=120, lock=True, log=print):
    """Hand over to `mind` `before` turns short of a recorded death.

    `death` is what `death_of` returned. The run that comes back is a branch of
    that death: its record names the parent and the turn it took over at.
    """
    handover = max(1, (death['turn'] or 0) - before)
    result = agent.play_with_mind(
        build_out, seed=death['seed'], cap=cap or death['turn_cap'], output=output,
        mind=mind, timeout=timeout, stall_timeout=stall_timeout,
        from_turn=handover, lock=lock, log=lambda *a: None)
    parent = {'run_id': death['run_id'], 'turn': handover}
    result['parent'] = parent
    result['post_mortem'] = {
        'death': death,
        'asked_to_take_over_at': handover,
        'turns_before_the_death': before,
        'mind': getattr(mind, 'name', 'unknown'),
        'outcome': result['outcome'],
        'survived_past_the_death': bool(
            result.get('final_turn') and death['turn']
            and result['final_turn'] > death['turn']),
        'died_again': result['outcome'] == 'death',
        'same_cause': result['outcome'] == 'death' and result.get('cause') == death['cause'],
    }
    Path(output).joinpath('result.json').write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n')
    log(json.dumps({'death': f"{death['cause']} at turn {death['turn']}",
                    'took_over_at': handover,
                    'outcome': result['outcome'],
                    'ended_at': result.get('final_turn'),
                    'cause': result.get('cause')}))
    return result, parent


def write_record(output, parent, store_note=None):
    """The run record of a post-mortem: mode B, with its parent named."""
    return record.write_record(output, mode='post_mortem', parent=parent)
