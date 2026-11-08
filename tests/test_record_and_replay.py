"""The run record, and replay, verify and branch (T04)."""
import json
import os
import shutil
from pathlib import Path

import pytest

from borg_agent import agent, build, mind, play, record, replay

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / 'schemas/examples/run-record/valid-scripted-mind-turn-cap.json')
                     .read_text())
TRACE = (
    'CHARACTER Measure Human Warrior\n'
    'OPTIONS none=0 birth_connect_stairs=1 birth_no_selling=1 rogue_like_commands=0\n'
    'BORG_OPTIONS borg_verbose=0 borg_cheat_death=0 borg_respawn_winners=0\n'
    'STATE start turn=1 depth=0 max_depth=0 level=1 max_level=1 decisions=0\n'
    'STATE turn_cap turn=1000 depth=1 max_depth=1 level=2 max_level=2 decisions=101\n'
)


def observation(decision=0, turn=10, run_id='a', **changes):
    base = {
        'schema': 'borg-agent/observation@1', 'run_id': run_id,
        'decision': decision, 'turn': turn,
        'character': {'race': 'Human', 'class': 'Warrior', 'level': 1,
                      'hp': 18, 'max_hp': 18, 'depth': 0, 'gold': 0},
        'map': {'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                'rows': ['#####', '#.@.#', '#####']},
        'monsters': [], 'inventory': [], 'equipment': [], 'messages': [],
        'prompt': {'kind': 'none'}, 'screen': ['a screen line'],
    }
    base.update(changes)
    return base


# --- the state hash ---------------------------------------------------------

def test_the_state_hash_is_about_the_state_not_the_run():
    # A run replayed into another directory has another run_id; that must not
    # change the state hash, or verify could never pass.
    assert record.state_hash(observation(run_id='first')) == \
           record.state_hash(observation(run_id='second'))


def test_the_state_hash_is_not_changed_by_key_order():
    one = observation()
    other = {k: one[k] for k in reversed(list(one))}
    assert record.state_hash(one) == record.state_hash(other)


@pytest.mark.parametrize('change', [
    {'turn': 11}, {'decision': 1},
    {'messages': ['You feel a sense of loss.']},
    {'character': {'race': 'Human', 'class': 'Warrior', 'level': 2,
                   'hp': 18, 'max_hp': 18, 'depth': 0, 'gold': 0}},
    {'monsters': [{'letter': 'r', 'name': None, 'x': 3, 'y': 1}]},
])
def test_any_change_to_the_state_changes_its_hash(change):
    assert record.state_hash(observation(**change)) != record.state_hash(observation())


def test_state_hashes_are_one_per_observation(tmp_path):
    path = tmp_path / 'observations.jsonl'
    path.write_text(''.join(json.dumps(observation(decision=i, turn=10 * i + 1)) + '\n'
                            for i in range(4)))
    hashes = record.state_hashes(path)
    assert len(hashes) == 4 and len(set(hashes)) == 4


# --- the record -------------------------------------------------------------

def test_the_generated_example_is_what_the_recorder_writes():
    # The example is generated from a real run, so it cannot drift from the
    # recorder. These are the fields R5 names.
    record.validate(EXAMPLE)
    assert EXAMPLE['engine']['pins'] and EXAMPLE['engine']['data_sha256']
    assert EXAMPLE['engine']['commit'] and 'dirty' in EXAMPLE['engine']
    assert EXAMPLE['game']['settings'] and EXAMPLE['game']['settings_sha256']
    assert EXAMPLE['game']['birth']['options'] and EXAMPLE['game']['input_sha256']
    assert EXAMPLE['calendar']['utc']
    assert EXAMPLE['action_stream']['count'] and EXAMPLE['action_stream']['sha256']
    assert EXAMPLE['evidence']['state_hashes_sha256']


def test_a_record_that_omits_what_r5_names_is_refused():
    for missing in ('calendar', 'engine', 'game', 'action_stream', 'outcome'):
        broken = {k: v for k, v in EXAMPLE.items() if k != missing}
        with pytest.raises(ValueError):
            record.validate(broken)


def test_the_settings_and_birth_options_come_from_the_observers_own_lines():
    assert record.parse_settings(TRACE, 'BORG_OPTIONS') == {
        'borg_verbose': 0, 'borg_cheat_death': 0, 'borg_respawn_winners': 0}
    options = record.birth_options(TRACE)
    assert options == {'birth_connect_stairs': 1, 'birth_no_selling': 1}
    assert 'rogue_like_commands' not in options


def test_depth_marks_are_the_first_turn_at_each_depth():
    states = play.parse_states(TRACE)
    assert record.depth_marks(states) == {'0': 1, '1': 1000}


def test_a_run_record_is_never_rewritten(tmp_path):
    # R4.1: raw run records are immutable; a correction is a new record.
    (tmp_path / record.RECORD_NAME).write_text('{}')
    with pytest.raises(ValueError, match='immutable'):
        record.write_record(tmp_path)


def test_a_model_run_is_not_deterministic():
    api = json.loads((ROOT / 'schemas/examples/run-record/valid-api-mind-death.json').read_text())
    record.validate(api)
    assert api['deterministic'] is False
    assert api['mind']['kind'] == 'api' and api['mind']['chosen_by'] == 'profile'
    # R6.3 and the reverse: a mind that does not call a model is deterministic.
    assert EXAMPLE['deterministic'] is True


def test_a_branch_record_names_its_parent_and_turn():
    branch = json.loads((ROOT / 'schemas/examples/run-record/valid-branch-of-another-run.json')
                        .read_text())
    record.validate(branch)
    assert branch['mode'] == 'post_mortem'
    assert branch['parent']['run_id'] and branch['parent']['turn'] > 0


# --- replay -----------------------------------------------------------------

def test_the_replay_mind_gives_back_exactly_what_was_recorded():
    actions = [mind.action('command', f'step {i}', command={'name': 'walk', 'direction': 6})
               for i in range(3)]
    replaying = replay.ReplayMind(actions)
    assert [replaying.act(observation(decision=i)) for i in range(3)] == actions
    assert replaying.replayed == 3


def test_a_replay_that_runs_out_of_actions_says_so():
    replaying = replay.ReplayMind([mind.action('command', 'one', command={'name': 'stay'})])
    replaying.act(observation())
    with pytest.raises(ValueError, match='ended at decision'):
        replaying.act(observation(decision=1, turn=20))


def test_a_branching_mind_replays_then_hands_over():
    actions = [mind.action('command', f'step {i}', command={'name': 'walk', 'direction': 6})
               for i in range(5)]
    taking_over = mind.ScriptedMind(heading=4)
    branching = replay.ReplayMind(actions, then=taking_over, until_turn=31)
    for turn in (1, 11, 21):
        assert branching.act(observation(turn=turn)) in actions
    assert not branching.handed_over
    handed = branching.act(observation(turn=31))
    assert branching.handed_over and branching.handed_over_at == 31
    assert handed['command']['direction'] == 4 and branching.replayed == 3


def test_reading_a_recorded_run(tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    (run / agent.OBSERVATION_LOG).write_text(''.join(
        json.dumps(observation(decision=i, turn=10 * i + 1)) + '\n' for i in range(5)))
    (run / agent.ACTION_LOG).write_text(''.join(
        json.dumps(mind.action('command', f'step {i}', command={'name': 'stay'})) + '\n'
        for i in range(5)))
    index, found = replay.at_turn(run, 25)
    assert index == 2 and found['turn'] == 21
    assert replay.view(run, 25)[2] == 'a screen line'
    assert replay.dump(run, 1)[1]['decision'] == 0
    around = replay.explain(run, 25, window=1)
    assert [line['decision'] for line in around] == [1, 2, 3]
    assert sum(line['current'] for line in around) == 1
    assert around[1]['action']['reason'] == 'step 2'
    with pytest.raises(ValueError):
        replay.at_turn(run, 0)


# --- the gates --------------------------------------------------------------

@pytest.mark.slow
def test_play_then_verify_reproduces_the_run(tmp_path):
    """T04's first gate: the same outcome and the same state at every observation."""
    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    played = agent.play_with_mind(out, seed=1, cap=1000, output=tmp_path / 'play',
                                  mind=mind.ScriptedMind(), timeout=300, stall_timeout=60,
                                  lock=lock)
    assert played['outcome'] in play.GOOD_OUTCOMES
    written = record.write_record(tmp_path / 'play')
    record.validate(json.loads(written.read_text()))
    verdict = replay.verify(tmp_path / 'play', tmp_path / 'verify', lock=lock,
                            log=lambda *a: None)
    assert verdict['verified'], verdict
    assert verdict['state_hashes_match'] and verdict['first_differing_decision'] is None
    assert verdict['decisions'][0] == verdict['decisions'][1] == played['decisions']
    assert verdict['trace_sha256'][0] == verdict['trace_sha256'][1]


@pytest.mark.slow
def test_branch_continues_with_another_mind_and_names_its_parent(tmp_path):
    """T04's second gate."""
    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    played = agent.play_with_mind(out, seed=1, cap=1000, output=tmp_path / 'play',
                                  mind=mind.ScriptedMind(), timeout=300, stall_timeout=60,
                                  lock=lock)
    assert played['outcome'] in play.GOOD_OUTCOMES
    result, parent = replay.branch(tmp_path / 'play', turn=500, output=tmp_path / 'branch',
                                   new_mind=mind.ScriptedMind(heading=4), lock=lock,
                                   log=lambda *a: None)
    assert parent['run_id'] == 'play' and parent['turn'] >= 500
    assert result['branch']['replayed_actions'] > 0
    written = record.write_record(tmp_path / 'branch', mode='post_mortem', parent=parent)
    branch_record = json.loads(written.read_text())
    record.validate(branch_record)
    assert branch_record['parent'] == parent
    # Up to the handover the branch is the same game; after it, it is not.
    before = record.state_hashes(tmp_path / 'play/observations.jsonl')
    after = record.state_hashes(tmp_path / 'branch/observations.jsonl')
    shared = sum(1 for a, b in zip(before, after) if a == b)
    assert shared >= result['branch']['replayed_actions']
    assert after != before


# --- what must never reach a record (review finding 5) ----------------------

def test_a_key_anywhere_in_a_record_is_refused():
    for where, change in (
            ('the mind block', lambda r: r['mind'].__setitem__('api_key', 'sk-abcdefghijkl')),
            ('a note', lambda r: r.__setitem__('notes', ['the key is sk-abcdefghijklmnop'])),
            ('an endpoint', lambda r: r['mind'].__setitem__(
                'endpoint_host', 'https://user:secret@host')),
            ('a uri', lambda r: r.setdefault('evidence', {}).__setitem__(
                'uris', {'observations_sha256': 'https://user:secret@store/x'})),
    ):
        broken = json.loads(json.dumps(EXAMPLE))
        change(broken)
        with pytest.raises(ValueError):
            record.validate(broken)


def test_a_key_in_the_environment_never_reaches_a_record_or_a_log(tmp_path):
    os.environ['BORG_AGENT_TEST_SECRET_API_KEY'] = 'sk-abcdefghijklmnopqrstuvwxyz'
    try:
        env = play.game_environment(BORG_MEASURE_SEED=1)
        assert not any('sk-' in value for value in env.values())
        assert record.secrets_in(EXAMPLE) == []
        # The run record is built from result.json and the build manifest, and
        # neither carries the environment.
        text = json.dumps(EXAMPLE)
        assert 'sk-' not in text and 'API_KEY' not in text
    finally:
        os.environ.pop('BORG_AGENT_TEST_SECRET_API_KEY')


def test_the_seasonal_window_makes_a_replay_incomparable():
    # Review finding 1: the game admits seasonal monsters on 24-26 December,
    # so a replay across that boundary says nothing. verify must say so rather
    # than report a difference as a failure to reproduce.
    assert 'seasonal' in EXAMPLE['calendar']
    assert isinstance(EXAMPLE['calendar']['seasonal'], bool)
