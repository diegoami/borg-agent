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


def find_death(build_out, seed, cap, output, race=None, class_=None, timeout=900,
               stall_timeout=120, lock=True, log=print):
    """Play the pinned Borg on a seed and report how it ended.

    `race` and `class_` look for a death of that character rather than the
    cohort's Human Warrior (T24); a post-mortem of it has to be born the same.
    """
    result = play.play(build_out, seed=seed, cap=cap, output=output, race=race,
                       class_=class_, timeout=timeout, stall_timeout=stall_timeout,
                       lock=lock, log=log)
    return result


def death_of(run_dir):
    """The turn and cause of a recorded death, or None if it did not die."""
    result = json.loads((Path(run_dir) / 'result.json').read_text())
    if result['outcome'] != 'death':
        return None
    found = {'run_id': result.get('run_id') or Path(run_dir).name,
             'seed': result['seed'],
             'turn': result.get('final_turn'),
             'cause': result.get('cause'),
             'turn_cap': result['turn_cap'],
             'trace_sha256': result.get('trace_sha256')}
    if result.get('birth_choice'):
        # A post-mortem has to be born the character that died (T24).
        found['birth'] = result['birth_choice']
    return found


def post_mortem(build_out, death, mind, output, before=DEFAULT_BEFORE, cap=None,
                race=None, class_=None, timeout=900, stall_timeout=120, lock=True,
                log=print):
    """Hand over to `mind` `before` turns short of a recorded death.

    `death` is what `death_of` returned. The run that comes back is a branch of
    that death: its record names the parent and the turn it took over at.
    """
    if before < 0:
        raise ValueError(f'--before is how many turns before the death to take over, '
                         f'so it cannot be {before}')
    handover = max(1, (death['turn'] or 0) - before)
    if death['turn'] and handover >= death['turn']:
        raise ValueError(f'the handover at turn {handover} is not before the death at turn '
                         f"{death['turn']}: there would be nothing for the agent to change")
    if cap and death['turn'] and cap <= handover:
        raise ValueError(f'the cap of {cap} turns stops the game at or before the handover at '
                         f'turn {handover}')
    result = agent.play_with_mind(
        build_out, seed=death['seed'], cap=cap or death['turn_cap'], output=output,
        mind=mind, timeout=timeout, stall_timeout=stall_timeout,
        from_turn=handover,
        # The death's own birth wins: a post-mortem of a Mage's death is a Mage
        # (T24). An explicit race and class override it, for a deliberate
        # "what would another character have done here".
        race=race or (death.get('birth') or {}).get('race'),
        class_=class_ or (death.get('birth') or {}).get('class'),
        lock=lock, log=lambda *a: None)
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
        # Nothing about the death is answered by a run the agent never played:
        # the flags describe the Borg's own game then, not the agent's, and
        # they read as if the agent had tried and failed (review finding 7).
        'agent_played': bool(result.get('decisions')),
    }
    if not result['post_mortem']['agent_played']:
        result['post_mortem']['warning'] = (
            'the agent never got a decision: the game ended at or before the handover, so the '
            'other fields describe the Borg\'s own play')
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
