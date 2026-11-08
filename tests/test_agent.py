"""The bridge's Python side: the wire format, the scripted mind, and the gate."""
import datetime
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from borg_agent import agent, build, mind, play

ROOT = Path(__file__).resolve().parents[1]
ACTION_SCHEMA = Draft202012Validator(json.loads((ROOT / 'schemas/action@1.json').read_text()))
OBSERVATION_SCHEMA = Draft202012Validator(
    json.loads((ROOT / 'schemas/observation@1.json').read_text()))


def observation(**changes):
    """A small observation, valid against the schema."""
    base = {
        'schema': 'borg-agent/observation@1',
        'run_id': 'test', 'decision': 0, 'turn': 10,
        'character': {'race': 'Human', 'class': 'Warrior', 'level': 1,
                      'hp': 18, 'max_hp': 18, 'depth': 0, 'gold': 0},
        'map': {'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                'rows': ['#####',
                         '#.@.#',
                         '#####']},
        'monsters': [], 'inventory': [], 'equipment': [], 'messages': [],
        'prompt': {'kind': 'none'},
    }
    base.update(changes)
    OBSERVATION_SCHEMA.validate(base)
    return base


# --- the wire format: where an action becomes keys -------------------------

def test_a_command_becomes_a_wire_line():
    assert agent.wire({'schema': 'borg-agent/action@1', 'kind': 'command', 'reason': 'r',
                       'command': {'name': 'walk', 'direction': 6}}) == 'command walk dir=6'
    assert agent.wire({'schema': 'borg-agent/action@1', 'kind': 'command', 'reason': 'r',
                       'command': {'name': 'go_down'}}) == 'command go_down'


def test_whitespace_and_control_characters_are_escaped():
    # One action is one line, so nothing may carry a space or a newline.
    line = agent.wire({'schema': 'borg-agent/action@1', 'kind': 'keys', 'reason': 'r',
                       'keys': {'keys': '\x1b y\n', 'why': 'w'}})
    assert line == 'keys %1b%20y%0a'
    assert '\n' not in line and line.count(' ') == 1


def test_the_wire_refuses_what_the_bridge_cannot_translate():
    for action in (
            {'kind': 'primitive', 'primitive': {'name': 'explore_floor'}},   # T05
            {'kind': 'command', 'command': {'name': 'cast', 'item': 'b'}},   # no keys yet
            {'kind': 'command', 'command': {'name': 'walk', 'count': 3}},    # walk takes no count
    ):
        with pytest.raises(ValueError):
            agent.wire({'schema': 'borg-agent/action@1', 'reason': 'r', **action})


def test_every_wire_command_is_one_the_bridge_knows():
    bridge = (ROOT / 'bridge/agent-bridge.c').read_text()
    for name in agent.WIRE_COMMANDS:
        assert f'"{name}"' in bridge, name
    for field in {f for fields in agent.WIRE_COMMANDS.values() for f in fields.values()}:
        assert f'"{field}"' in bridge, field


# --- the scripted mind ------------------------------------------------------

def test_the_mind_walks_where_it_can_and_keeps_its_heading():
    scripted = mind.ScriptedMind(heading=6)
    action = scripted.act(observation())
    assert action['command'] == {'name': 'walk', 'direction': 6}
    ACTION_SCHEMA.validate(action)
    # Still 6 next time, so it crosses a room instead of jittering.
    assert scripted.act(observation())['command']['direction'] == 6


def test_the_mind_turns_when_the_way_is_blocked():
    walled = observation(map={'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                              'rows': ['#.###',
                                       '#.@##',
                                       '#####']})
    action = mind.ScriptedMind(heading=6).act(walled)
    assert action['command']['name'] == 'walk' and action['command']['direction'] in (4, 7)


def test_the_mind_stays_put_when_nothing_is_known():
    nowhere = observation(map={'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                               'rows': ['#####', '##@##', '#####']})
    assert mind.ScriptedMind().act(nowhere)['command'] == {'name': 'stay'}


def test_the_mind_does_not_step_onto_a_monster():
    occupied = observation(monsters=[{'letter': 'r', 'name': None, 'x': 3, 'y': 1}])
    action = mind.ScriptedMind(heading=6).act(occupied)
    assert action['command']['direction'] != 6


def test_the_mind_opens_a_door_rather_than_walking_into_it():
    door = observation(map={'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                            'rows': ['#####', '#.@+#', '#####']})
    assert mind.ScriptedMind(heading=6).act(door)['command'] == {'name': 'alter', 'direction': 6}


def test_the_mind_takes_a_down_staircase_it_is_standing_on():
    stairs = observation(map={'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                              'rows': ['#####', '#.>.#', '#####']})
    assert mind.ScriptedMind().act(stairs)['command'] == {'name': 'go_down'}


@pytest.mark.parametrize('kind,expected', [
    ('more', 'answer'), ('yes_no', 'answer'), ('item', 'escape'),
    ('menu', 'escape'), ('text', 'escape'),
])
def test_the_mind_answers_a_prompt_before_anything_else(kind, expected):
    asked = observation(prompt={'kind': kind, 'text': 'something?'})
    action = mind.ScriptedMind().act(asked)
    ACTION_SCHEMA.validate(action)
    assert action['command']['name'] == expected


def test_every_action_the_mind_can_produce_is_valid_and_translatable():
    cases = [observation(),
             observation(prompt={'kind': 'more'}),
             observation(prompt={'kind': 'yes_no'}),
             observation(prompt={'kind': 'menu'}),
             observation(map={'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                              'rows': ['#####', '#.>.#', '#####']}),
             observation(map={'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                              'rows': ['#####', '##@##', '#####']})]
    for case in cases:
        action = mind.ScriptedMind().act(case)
        ACTION_SCHEMA.validate(action)
        assert agent.wire(action)
        assert action['reason'] and '\n' not in action['reason']


# --- the run's own rules ----------------------------------------------------

def test_the_game_gets_none_of_our_keys():
    # Finding 5 of the milestone-1 review: the game never calls a model, so no
    # key of ours belongs in its environment or in the log it writes.
    os.environ['BORG_AGENT_TEST_FAKE_API_KEY'] = 'not-a-real-key'
    try:
        env = play.game_environment(BORG_MEASURE_SEED=7)
    finally:
        os.environ.pop('BORG_AGENT_TEST_FAKE_API_KEY')
    assert 'BORG_AGENT_TEST_FAKE_API_KEY' not in env
    assert not [name for name in env if 'KEY' in name or 'TOKEN' in name or 'SECRET' in name]
    assert env['BORG_MEASURE_SEED'] == '7' and env['LC_ALL'] == 'C.UTF-8'
    assert set(env) <= set(play.ENVIRONMENT_ALLOWLIST) | {'BORG_MEASURE_SEED'}


def test_a_budget_or_decision_cap_is_an_outcome_not_a_failure():
    # R2.3: hitting the budget is the outcome budget_cap, not a failure.
    for kind in ('budget_cap', 'decision_cap', 'agent_stopped', 'death', 'turn_cap'):
        assert kind in play.GOOD_OUTCOMES, kind
    for kind in play.HARNESS_OUTCOMES:
        assert kind not in play.GOOD_OUTCOMES, kind
    enum = set(json.loads((ROOT / 'schemas/run-record@1.json').read_text())
               ['properties']['outcome']['properties']['kind']['enum'])
    assert set(play.GOOD_OUTCOMES) | set(play.HARNESS_OUTCOMES) == enum | {'saved'}


def test_the_calendar_is_recorded_because_play_is_not_date_independent():
    # The game admits seasonal monsters on 24-26 December, so a record that
    # does not say when it ran cannot be replayed with confidence.
    recorded = play.calendar()
    assert set(recorded) == {'utc', 'local', 'timezone_name', 'TZ_environment', 'seasonal'}
    datetime.datetime.fromisoformat(recorded['utc'])
    assert recorded['seasonal'] is play.seasonal()


@pytest.mark.parametrize('date,expected', [
    ((2026, 12, 24), True), ((2026, 12, 25), True), ((2026, 12, 26), True),
    ((2026, 12, 23), False), ((2026, 12, 27), False), ((2026, 11, 8), False),
])
def test_the_seasonal_window_is_the_games_own(date, expected):
    # get_mon_num admits RF_SEASONAL monsters only on those three days.
    assert play.seasonal(datetime.datetime(*date)) is expected


def test_a_build_directory_that_is_not_ours_is_not_deleted(tmp_path):
    precious = tmp_path / 'notes'
    precious.mkdir()
    (precious / 'keep.txt').write_text('mine')
    with pytest.raises(ValueError):
        build.prepare(out=precious, log=lambda *a: None)
    assert (precious / 'keep.txt').read_text() == 'mine'


# --- the gate ---------------------------------------------------------------

@pytest.mark.slow
def test_a_scripted_mind_plays_the_same_game_twice(tmp_path):
    """T03's gate: the same mind, the same seed, the same recorded actions."""
    out = build.prepare(log=lambda *a: None)
    streams, records = [], []
    for attempt in (1, 2):
        record = agent.play_with_mind(out, seed=1, cap=1000, output=tmp_path / f'run{attempt}',
                                      mind=mind.ScriptedMind(), timeout=300, stall_timeout=60,
                                      lock=not os.environ.get('BORG_AGENT_NO_LOCK'))
        assert record['outcome'] in play.GOOD_OUTCOMES, record
        assert record['decisions'] > 0 and record['final_turn'] >= 1000
        records.append(record)
        streams.append((tmp_path / f'run{attempt}' / agent.ACTION_LOG).read_bytes())
    assert streams[0] and streams[0] == streams[1]
    assert records[0]['action_stream']['sha256'] == records[1]['action_stream']['sha256']
    assert records[0]['trace_sha256'] == records[1]['trace_sha256']
    assert records[0]['outcome'] == records[1]['outcome']


@pytest.mark.slow
def test_a_slow_mind_is_not_called_a_stall(tmp_path):
    """Review finding 2: model latency must never become an outcome (R1.3).

    The mind here takes far longer per decision than the stall limit. The run
    must still finish: the stall clock follows the protocol, not the clock.
    """
    import time

    class Slow(mind.ScriptedMind):
        name = 'slow'

        def act(self, observation):
            time.sleep(0.3)
            return super().act(observation)

    out = build.prepare(log=lambda *a: None)
    record = agent.play_with_mind(out, seed=1, cap=100, output=tmp_path / 'slow',
                                  mind=Slow(), timeout=300, stall_timeout=0.1,
                                  lock=not os.environ.get('BORG_AGENT_NO_LOCK'),
                                  log=lambda *a: None)
    assert record['outcome'] in play.GOOD_OUTCOMES, record
    assert record['decisions'] >= 5
    assert record['wall_seconds'] > record['decisions'] * 0.25


# --- the heavy-run lock -----------------------------------------------------

def test_the_lock_is_skipped_when_asked():
    os.environ['BORG_AGENT_NO_LOCK'] = '1'
    try:
        with play.heavy_lock() as handle:
            assert handle is None
    finally:
        os.environ.pop('BORG_AGENT_NO_LOCK')


def test_the_lock_is_skipped_when_an_ancestor_holds_it(tmp_path):
    """`flock <lock> pytest -m slow` must not deadlock against itself.

    The documented way to run heavy work is under an outer flock, and the
    suite's own runs take the same lock. A second acquire from inside that
    tree can never succeed, because the holder is waiting for us.
    """
    procfs = tmp_path / 'proc'
    lock = tmp_path / 'the.lock'
    lock.write_text('')
    # A tiny /proc: 100 is the parent of 200, which is this process's parent,
    # and 100 holds the lock.
    for pid, ppid, holds in ((100, 1, True), (200, 100, False), (300, 1, True)):
        (procfs / str(pid) / 'fd').mkdir(parents=True)
        (procfs / str(pid) / 'stat').write_text(f'{pid} (flock) S {ppid} 0 0')
        if holds:
            (procfs / str(pid) / 'fd' / '3').symlink_to(lock)
    assert play.lock_holders(lock, procfs) == [100, 300]
    assert play.parents(200, procfs) == [200, 100]
    assert play.held_by_an_ancestor(lock, procfs, pid=200) is True
    # A holder that is not an ancestor is a real wait, not a deadlock.
    (procfs / '100' / 'fd' / '3').unlink()
    assert play.held_by_an_ancestor(lock, procfs, pid=200) is False


def test_waiting_for_the_lock_gives_up_with_an_explanation(tmp_path, monkeypatch):
    lock = tmp_path / 'held.lock'
    monkeypatch.setattr(play, 'LOCK_PATH', str(lock))
    holder = open(lock, 'a+')
    import fcntl

    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        with pytest.raises(TimeoutError, match='BORG_AGENT_NO_LOCK'):
            with play.heavy_lock(timeout=0, log=lambda *a: None):
                pass
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        holder.close()
