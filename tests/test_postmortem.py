"""Mode B: a recorded death, taken over shortly before the end (T08)."""
import json
import os
from pathlib import Path

import pytest

from borg_agent import agent, build, mind, play, postmortem, record, replay


def a_death(tmp_path, outcome='death', turn=1740, cause='a stegocentipede'):
    run = tmp_path / 'death'
    run.mkdir()
    (run / 'result.json').write_text(json.dumps({
        'run_id': 'death-1', 'seed': 7, 'outcome': outcome, 'cause': cause,
        'final_turn': turn, 'turn_cap': 30000, 'trace_sha256': 'a' * 64,
        'calendar': {'utc': '2026-11-09T12:00:00Z', 'seasonal': False},
    }))
    return run


# --- reading a death --------------------------------------------------------

def test_a_recorded_death_is_read_with_what_mode_b_needs(tmp_path):
    found = postmortem.death_of(a_death(tmp_path))
    assert found == {'run_id': 'death-1', 'seed': 7, 'turn': 1740,
                     'cause': 'a stegocentipede', 'turn_cap': 30000,
                     'trace_sha256': 'a' * 64}


def test_a_run_that_did_not_die_is_no_case(tmp_path):
    assert postmortem.death_of(a_death(tmp_path, outcome='turn_cap', cause=None)) is None


# --- the handover -----------------------------------------------------------

def test_the_handover_is_the_asked_for_distance_before_the_death(tmp_path, monkeypatch):
    seen = {}

    def fake_play(build_out, seed, cap, output, mind, **kwargs):
        seen.update(seed=seed, cap=cap, from_turn=kwargs.get('from_turn'))
        Path(output).mkdir(parents=True, exist_ok=True)
        return {'outcome': 'turn_cap', 'final_turn': 30000, 'seed': seed,
                'calendar': {'utc': 'x'}}

    monkeypatch.setattr(agent, 'play_with_mind', fake_play)
    death = postmortem.death_of(a_death(tmp_path))
    result, parent = postmortem.post_mortem(
        'build', death, mind.ScriptedMind(), tmp_path / 'branch', before=200,
        log=lambda *a: None)
    assert seen['from_turn'] == 1540 and seen['seed'] == 7
    assert parent == {'run_id': 'death-1', 'turn': 1540}
    assert result['post_mortem']['turns_before_the_death'] == 200
    assert result['post_mortem']['survived_past_the_death'] is True
    assert result['post_mortem']['died_again'] is False


def test_the_handover_never_goes_before_the_first_turn(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(agent, 'play_with_mind',
                        lambda *a, **k: (seen.update(from_turn=k.get('from_turn')),
                                         Path(a[3] if len(a) > 3 else k['output']).mkdir(
                                             parents=True, exist_ok=True),
                                         {'outcome': 'death', 'final_turn': 10, 'seed': 7,
                                          'cause': 'a rat', 'calendar': {'utc': 'x'}})[-1])
    death = postmortem.death_of(a_death(tmp_path, turn=50))
    postmortem.post_mortem('build', death, mind.ScriptedMind(), tmp_path / 'branch',
                           before=500, log=lambda *a: None)
    assert seen['from_turn'] == 1


def test_a_second_death_from_the_same_cause_is_noticed(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, 'play_with_mind',
                        lambda *a, **k: (Path(k.get('output') or a[3]).mkdir(
                            parents=True, exist_ok=True),
                            {'outcome': 'death', 'final_turn': 1750, 'seed': 7,
                             'cause': 'a stegocentipede', 'calendar': {'utc': 'x'}})[-1])
    death = postmortem.death_of(a_death(tmp_path))
    result, _parent = postmortem.post_mortem('build', death, mind.ScriptedMind(),
                                             tmp_path / 'branch', log=lambda *a: None)
    assert result['post_mortem']['died_again'] is True
    assert result['post_mortem']['same_cause'] is True
    assert result['post_mortem']['survived_past_the_death'] is True   # by ten turns


def test_a_handover_that_is_not_before_the_death_is_refused(tmp_path):
    # Milestone 3 review, finding 7: with before=0 (or a cap that stops the
    # game first) the Borg dies before the agent has a decision, and the
    # post-mortem block read as if the agent had played and failed.
    death = postmortem.death_of(a_death(tmp_path))
    for arguments, message in (({'before': 0}, 'not before the death'),
                               ({'before': -5}, 'cannot be -5'),
                               ({'before': 200, 'cap': 1500}, 'cap of 1500')):
        with pytest.raises(ValueError, match=message):
            postmortem.post_mortem('build', death, mind.ScriptedMind(), tmp_path / 'branch',
                                   log=lambda *a: None, **arguments)


def test_a_post_mortem_the_agent_never_played_says_so(tmp_path, monkeypatch):
    # The handover is before the death, but the game ended first anyway.
    monkeypatch.setattr(agent, 'play_with_mind',
                        lambda *a, **k: (Path(k['output']).mkdir(parents=True, exist_ok=True),
                                         {'outcome': 'death', 'final_turn': 1700, 'seed': 7,
                                          'decisions': 0, 'cause': 'a stegocentipede',
                                          'calendar': {'utc': 'x'}})[-1])
    death = postmortem.death_of(a_death(tmp_path))
    result, _parent = postmortem.post_mortem('build', death, mind.ScriptedMind(),
                                             tmp_path / 'branch', before=200,
                                             log=lambda *a: None)
    assert result['post_mortem']['agent_played'] is False
    assert 'never got a decision' in result['post_mortem']['warning']


# --- the bridge's side of it -------------------------------------------------

def test_the_bridge_hands_over_at_a_turn_and_says_so():
    # The C the recipe applies: the Borg keeps deciding until the turn the run
    # names, and the handover is written into the trace.
    bridge = (Path(__file__).resolve().parents[1] / 'bridge/agent-bridge.c').read_text()
    assert 'BORG_AGENT_FROM_TURN' in bridge
    assert 'if (turn < from_turn)' in bridge
    assert 'AGENT taking over at turn' in bridge


def test_a_run_records_the_turn_it_took_over_at(tmp_path, monkeypatch):
    # So that verify can replay the prefix the same way (mode B).
    assert 'from_turn' in (Path(__file__).resolve().parents[1]
                           / 'src/borg_agent/agent.py').read_text()
    source = (Path(__file__).resolve().parents[1] / 'src/borg_agent/replay.py').read_text()
    assert "from_turn=original.get('from_turn')" in source


def test_branching_a_post_mortem_before_its_handover_is_refused(tmp_path, monkeypatch):
    # The recording starts at the handover, so there is nothing to replay
    # before it; asking for that turn is a mistake worth naming.
    run = tmp_path / 'mortem'
    run.mkdir()
    (run / 'result.json').write_text(json.dumps(
        {'run_id': 'pm-1', 'seed': 3, 'turn_cap': 30000, 'from_turn': 1500,
         'outcome': 'turn_cap', 'build_key': 'x'}))
    (run / 'actions.jsonl').write_text('')
    with pytest.raises(ValueError, match='took over at turn 1500'):
        replay.branch(run, 900, tmp_path / 'branch', mind.ScriptedMind(),
                      lock=False, log=lambda *a: None)


# --- the gate ----------------------------------------------------------------

@pytest.mark.slow
def test_a_borg_death_is_reproduced_and_then_taken_over(tmp_path):
    """T08's gate, on a death this build produces.

    The Borg's play is deterministic, so the prefix needs no save: playing the
    seed again brings the game back to the same place, and the bridge hands
    over at the turn asked for.
    """
    seed = int(os.environ.get('BORG_AGENT_DEATH_SEED', '0'))
    if not seed:
        # T34: with munchkin off -- which the requirements demand -- no seed
        # with a known death is left. Twelve seeds survived 30,000 turns, and
        # the deaths we had were a munchkin Warrior's. A death to gate on now
        # comes from better-borg-c's curated corpus or from the zoo, which is
        # also where the pivot (docs/DEATH-ANALYSIS-SPEC.md) takes its input.
        pytest.skip('no seed with a known Borg death is configured '
                    '(BORG_AGENT_DEATH_SEED); see docs/POST-MORTEM.md')
    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    first = postmortem.find_death(out, seed, 30000, tmp_path / 'death-1',
                                  lock=lock, log=lambda *a: None)
    death = postmortem.death_of(tmp_path / 'death-1')
    assert death, f'seed {seed} did not die: {first["outcome"]}'
    # The same death, again, from the seed alone.
    second = postmortem.find_death(out, seed, 30000, tmp_path / 'death-2',
                                   lock=lock, log=lambda *a: None)
    assert second['trace_sha256'] == first['trace_sha256']
    assert second['cause'] == death['cause'] and second['final_turn'] == death['turn']
    # Now take over before the end, and record it as a branch of that death.
    result, parent = postmortem.post_mortem(
        out, death, mind.ScriptedMind(), tmp_path / 'branch', before=200,
        lock=lock, log=lambda *a: None)
    assert parent['run_id'] == death['run_id']
    assert parent['turn'] == death['turn'] - 200
    assert result['decisions'] > 0, 'the agent never got a decision'
    record.write_record(tmp_path / 'branch', mode='post_mortem', parent=parent)
    # And the post-mortem itself replays: the Borg's prefix comes back by
    # itself, and the recorded actions replay from the handover.
    verdict = replay.verify(tmp_path / 'branch', tmp_path / 'verified', lock=lock,
                            log=lambda *a: None)
    assert verdict['verified'], verdict
    assert verdict['from_turn'] == parent['turn']


@pytest.mark.slow
def test_a_branch_of_a_handover_run_lands_in_the_same_game(tmp_path):
    """Milestone 3 review, finding 1.

    `branch` left `from_turn` out, so the actions a post-mortem recorded from
    its handover turn were fed to a newborn character in town: a self-
    consistent recording of a different game, under the parent's name. The
    cheap version of that shape is enough to catch it -- a short run that takes
    over at turn 200, branched afterwards.
    """
    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    first = agent.play_with_mind(build_out=out, seed=7, cap=400, output=tmp_path / 'handover',
                                 mind=mind.ScriptedMind(), from_turn=200, lock=lock,
                                 log=lambda *a: None)
    assert first['from_turn'] == 200
    observations = [json.loads(line) for line
                    in (tmp_path / 'handover/observations.jsonl').read_text().splitlines()]
    assert observations and observations[0]['turn'] >= 200, 'the prefix was not the Borg\'s'

    result, parent = replay.branch(tmp_path / 'handover', observations[-1]['turn'],
                                   tmp_path / 'branched', mind.ScriptedMind(),
                                   lock=lock, log=lambda *a: None)
    # The branch played the same prefix, so its own first observation is at
    # the handover too -- not at turn 1 in the town.
    branched = [json.loads(line) for line
                in (tmp_path / 'branched/observations.jsonl').read_text().splitlines()]
    assert result['from_turn'] == 200
    assert branched and branched[0]['turn'] >= 200, branched[0]['turn']
    assert record.state_hash(branched[0]) == record.state_hash(observations[0]), \
        'the branch started in a different game from its parent'
    assert parent['run_id'] == (first.get('run_id') or 'handover')
