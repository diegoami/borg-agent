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


def test_a_replay_that_runs_out_of_actions_says_where():
    # Not a failure: the run it came from was ended by the harness, so the
    # recording stops here and `verify` reads that as the stream's end (R2.3).
    replaying = replay.ReplayMind([mind.action('command', 'one', command={'name': 'stay'})])
    replaying.act(observation())
    with pytest.raises(replay.StreamEnded) as raised:
        replaying.act(observation(decision=1, turn=20))
    assert raised.value.decisions == 1 and raised.value.turn == 20
    assert 'asked again at turn 20' in str(raised.value)


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


# --- verifying a run the harness ended (milestone 2 review, finding 1) ------

@pytest.mark.slow
def test_a_capped_run_verifies_as_far_as_it_was_recorded(tmp_path):
    """The shape of every model run: stopped by a cap, not by the game.

    The reviewer found that such a run could never verify — the replay ran out
    of actions, which was recorded as a harness failure, and the one extra
    observation made the state hashes look different while naming no
    difference at all.
    """
    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    played = agent.play_with_mind(out, seed=1, cap=10000, output=tmp_path / 'capped',
                                  mind=mind.ScriptedMind(), decision_cap=20, timeout=300,
                                  stall_timeout=60, lock=lock, log=lambda *a: None)
    assert played['outcome'] == 'decision_cap' and played['decisions'] == 20
    record.write_record(tmp_path / 'capped')
    verdict = replay.verify(tmp_path / 'capped', tmp_path / 'verified', lock=lock,
                            log=lambda *a: None)
    assert verdict['verified'], verdict
    assert verdict['scope'] == 'prefix'
    assert verdict['state_hashes_match'] and verdict['first_differing_decision'] is None
    # The replay ends where the recording does, and says so.
    assert verdict['stream_ended'] == {'decisions': 20, 'turn': played['final_turn']}
    assert '20 recorded states reproduced' in verdict['verified_as']
    # And the record is checked against the run, not only the run against itself.
    assert verdict['record_matches_run'] is True


@pytest.mark.slow
def test_a_real_divergence_in_a_capped_run_is_still_caught(tmp_path):
    """The prefix rule must not become a way of passing anything.

    A recorded action is changed, so the replay plays a different game from the
    second decision on. `verify` must refuse it and name where.
    """
    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    agent.play_with_mind(out, seed=1, cap=10000, output=tmp_path / 'capped',
                         mind=mind.ScriptedMind(), decision_cap=20, timeout=300,
                         stall_timeout=60, lock=lock, log=lambda *a: None)
    actions = (tmp_path / 'capped' / agent.ACTION_LOG).read_text().splitlines()
    tampered = json.loads(actions[1])
    tampered['command'] = {'name': 'stay'}
    actions[1] = json.dumps(tampered, sort_keys=True)
    (tmp_path / 'capped' / agent.ACTION_LOG).write_text('\n'.join(actions) + '\n')
    verdict = replay.verify(tmp_path / 'capped', tmp_path / 'verified', lock=lock,
                            log=lambda *a: None)
    assert verdict['verified'] is False
    assert verdict['state_hashes_match'] is False
    assert verdict['first_differing_decision'] == 2
    assert verdict['failed_because'] == 'the replay diverged from the run'


@pytest.mark.slow
def test_branching_a_death_before_it_happens(tmp_path):
    """T08's own shape: take a recorded death and try something else.

    Replay starts from birth, so this needs no save of the dying game — which
    is worth knowing before T08 is written. The review listed it as untested.
    """
    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    died = agent.play_with_mind(out, seed=7, cap=2000, output=tmp_path / 'death',
                                mind=mind.ScriptedMind(), timeout=300, stall_timeout=60,
                                lock=lock, log=lambda *a: None)
    assert died['outcome'] == 'death', died
    assert died['cause'] and died['final_turn'] < 2000
    record.write_record(tmp_path / 'death')
    # The death itself reproduces: the game ended this run, so the whole of it.
    verdict = replay.verify(tmp_path / 'death', tmp_path / 'verified', lock=lock,
                            log=lambda *a: None)
    assert verdict['verified'] and verdict['scope'] == 'full', verdict
    assert verdict['cause'][0] == verdict['cause'][1] == died['cause']
    # Now go back and try something else before the end: a mind that waits
    # where the first one walked. "What if it had stood still?" is the kind of
    # question mode B exists to ask.
    class Waiting:
        name = 'waiting'
        kind = 'scripted'

        def act(self, observation):
            prompt = (observation.get('prompt') or {'kind': 'none'})['kind']
            if prompt == 'more':
                return mind.action('command', 'Clear the prompt.',
                                   command={'name': 'answer', 'answer': '\r'})
            if prompt != 'none':
                return mind.action('command', 'Leave the prompt.',
                                   command={'name': 'escape'})
            return mind.action('command', 'Wait and see.', command={'name': 'stay'})

    before_the_end = max(10, died['final_turn'] - 100)
    result, parent = replay.branch(tmp_path / 'death', turn=before_the_end,
                                   output=tmp_path / 'branch',
                                   new_mind=Waiting(), lock=lock,
                                   log=lambda *a: None)
    assert parent == {'run_id': 'death', 'turn': result['branch']['handed_over_at']}
    assert parent['turn'] >= before_the_end
    branch_record = json.loads(record.write_record(
        tmp_path / 'branch', mode='post_mortem', parent=parent).read_text())
    assert branch_record['mode'] == 'post_mortem'
    assert branch_record['parent']['run_id'] == 'death'
    # The branch is the same game up to the handover and its own after it.
    before = record.state_hashes(tmp_path / 'death/observations.jsonl')
    after = record.state_hashes(tmp_path / 'branch/observations.jsonl')
    assert before[:result['branch']['replayed_actions']] == \
        after[:result['branch']['replayed_actions']]
    assert after != before


# --- the record must describe the run beside it (re-review, finding 1) ------

def run_directory(tmp_path, actions=4, record_it=True):
    """A small run directory with a record, built without playing anything."""
    run = tmp_path / 'run'
    run.mkdir()
    (run / agent.OBSERVATION_LOG).write_text(''.join(
        json.dumps(observation(decision=i, turn=10 * i + 1)) + '\n' for i in range(actions)))
    (run / agent.ACTION_LOG).write_text(''.join(
        json.dumps(mind.action('command', f'step {i}', command={'name': 'stay'})) + '\n'
        for i in range(actions)))
    hashes = record.state_hashes(run / agent.OBSERVATION_LOG)
    (run / record.STATE_HASHES_NAME).write_text(''.join(h + '\n' for h in hashes))
    (run / agent.MODEL_CALL_LOG).write_text(''.join(
        json.dumps({'decision': i, 'reply': 'walk', 'model': 'm'}) + '\n'
        for i in range(actions)))
    recorded = {
        'action_stream': {'count': actions, 'sha256': record.sha(run / agent.ACTION_LOG)},
        'evidence': {'observations_sha256': record.sha(run / agent.OBSERVATION_LOG),
                     'state_hashes_sha256': record.sha(run / record.STATE_HASHES_NAME),
                     'model_calls_sha256': record.sha(run / agent.MODEL_CALL_LOG)},
        'usage': {'model_calls': actions},
    }
    return run, recorded


def test_a_record_matches_the_run_it_describes(tmp_path):
    run, recorded = run_directory(tmp_path)
    assert replay.check_record_against_run(recorded, run, 4) == (True, None)


def test_a_run_cut_short_at_the_end_is_caught(tmp_path):
    """The hole the prefix rule opened, found by the re-review.

    Cut the last lines off both logs and leave the record and the state hashes
    alone: the replay reproduces what remains, and `prefix` tolerates a stream
    that ends early — so only the record's own counts and hashes can tell.
    """
    run, recorded = run_directory(tmp_path, actions=6)
    for name in (agent.ACTION_LOG, agent.OBSERVATION_LOG):
        path = run / name
        path.write_text('\n'.join(path.read_text().splitlines()[:-2]) + '\n')
    matches, reason = replay.check_record_against_run(recorded, run, 4)
    assert matches is False
    assert 'action stream' in reason


@pytest.mark.parametrize('what,break_it', [
    ('the actions', lambda run: (run / agent.ACTION_LOG).write_text('{"changed": true}\n')),
    ('the observations', lambda run: (run / agent.OBSERVATION_LOG).write_text('{}\n')),
    ('the state hashes', lambda run: (run / record.STATE_HASHES_NAME).write_text('nope\n')),
    ('a missing file', lambda run: (run / record.STATE_HASHES_NAME).unlink()),
    # The stream milestone 3 added: published, and not compared (finding 2).
    ('the model calls', lambda run: (run / agent.MODEL_CALL_LOG).write_text('{"a": 1}\n')),
    ('the model calls, truncated', lambda run: (run / agent.MODEL_CALL_LOG).write_text('')),
    ('the model call log, gone', lambda run: (run / agent.MODEL_CALL_LOG).unlink()),
])
def test_every_stream_the_record_names_is_compared(tmp_path, what, break_it):
    run, recorded = run_directory(tmp_path)
    break_it(run)
    matches, reason = replay.check_record_against_run(recorded, run, 4)
    assert matches is False and reason, what


def test_a_truncated_model_call_log_is_caught_by_its_count(tmp_path):
    """Milestone 3 review, finding 2.

    The call log is what R2.1 asks for -- what the model was told, what it
    answered and what it cost -- so an edited one is edited evidence. The
    record published its hash and its count; neither was compared.
    """
    run, recorded = run_directory(tmp_path, actions=4)
    lines = (run / agent.MODEL_CALL_LOG).read_text().splitlines()
    (run / agent.MODEL_CALL_LOG).write_text('\n'.join(lines[:-1]) + '\n')
    matches, reason = replay.check_record_against_run(recorded, run, 4)
    assert matches is False
    assert 'model calls' in reason, reason


def test_a_record_with_nothing_to_compare_says_so(tmp_path):
    run, _ = run_directory(tmp_path)
    assert replay.check_record_against_run({}, run, 4) == (None, None)


@pytest.mark.slow
def test_a_tail_cut_run_does_not_verify(tmp_path):
    """The same hole, end to end: the replay reproduces, the record does not agree."""
    import shutil

    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    agent.play_with_mind(out, seed=1, cap=10000, output=tmp_path / 'capped',
                         mind=mind.ScriptedMind(), decision_cap=20, timeout=300,
                         stall_timeout=60, lock=lock, log=lambda *a: None)
    record.write_record(tmp_path / 'capped')
    cut = tmp_path / 'cut'
    cut.mkdir()
    for item in (tmp_path / 'capped').iterdir():
        if item.is_file() and not item.name.endswith('.fifo'):
            shutil.copy(item, cut / item.name)
    for name in (agent.ACTION_LOG, agent.OBSERVATION_LOG):
        path = cut / name
        path.write_text('\n'.join(path.read_text().splitlines()[:-3]) + '\n')
    verdict = replay.verify(cut, tmp_path / 'verified', lock=lock, log=lambda *a: None)
    assert verdict['verified'] is False
    assert verdict['record_matches_run'] is False
    assert 'the record published' in verdict['failed_because']


@pytest.mark.slow
def test_a_branch_keeps_the_journal_of_the_mind_that_took_over(tmp_path):
    """Re-review finding 2: mode B is "replay, then try something else", and
    what the something else chose is the interesting part."""
    from borg_agent import executor

    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    agent.play_with_mind(out, seed=1, cap=3000, output=tmp_path / 'play',
                         mind=mind.ScriptedMind(), timeout=300, stall_timeout=60,
                         lock=lock, log=lambda *a: None)
    taking_over = executor.ExecutingMind(mind.PrimitiveMind(), name='scripted-primitives')
    result, _parent = replay.branch(tmp_path / 'play', turn=150, output=tmp_path / 'branch',
                                    new_mind=taking_over, lock=lock, log=lambda *a: None)
    assert result['journal']['count'] > 0, 'the branch recorded no decisions'
    entries = [json.loads(line) for line in
               (tmp_path / 'branch' / agent.JOURNAL_LOG).read_text().splitlines()]
    assert {entry['kind'] for entry in entries} == {'choice', 'stop'}
    # Only what the new mind decided, so nothing before the handover.
    assert min(entry['turn'] for entry in entries) >= 150
