"""Trace parsing and outcome classification, and the headless play gate (slow)."""
import datetime
import json
import os

import pytest

from borg_agent import build, cli, play

TRACE = (
    'CHARACTER Measure Human Warrior\n'
    'STATE start turn=1 energy=0 decisions=0 depth=0 max_depth=0 level=1 max_level=1 hp=20 '
    'dead=0 winner=0 borg_rng=1 quick=0 quick_rng=2 rng_index=3 rng=' + 'deadbeef' * 8 + '\n'
    'BORG 10 # Flowing toward dark-2 at cost 3\n'
    'STATE turn_cap turn=5000 energy=0 decisions=42 depth=1 max_depth=1 level=3 max_level=3 hp=30 '
    'dead=0 winner=0 borg_rng=1 quick=0 quick_rng=2 rng_index=3 rng=' + 'deadbeef' * 8 + '\n'
    'CAUSE (alive and well)\n'
)


def test_parse_states_reads_game_facts():
    states = play.parse_states(TRACE)
    assert [s['kind'] for s in states] == ['start', 'turn_cap']
    assert states[-1]['turn'] == 5000 and states[-1]['decisions'] == 42
    assert states[-1]['rng'] == 'deadbeef' * 8


def test_parse_states_ignores_an_unfinished_line():
    assert play.parse_states('STATE start turn=1') == []
    assert len(play.parse_states(TRACE + 'STATE death turn=99')) == 2


def test_classify_uses_the_last_final_state():
    states = play.parse_states(TRACE)
    assert play.classify(0, states) == 'turn_cap'
    assert play.classify(0, states, interrupted='stalled') == 'stalled'
    assert play.classify(-6, states) == 'crash'
    assert play.classify(0, []) == 'harness_failure'
    assert play.classify(0, play.parse_states(TRACE.replace('turn_cap', 'progress'))) == 'harness_failure'


def test_the_birth_input_is_the_zoo_runners():
    assert play.BIRTH_INPUT.startswith('key space\nkey a\nkey a\nkey a\n')
    assert 'key C-z' in play.BIRTH_INPUT  # the Borg's own activation
    assert play.BORG_CONFIG == 'borg_cheat_death = FALSE\nborg_respawn_winners = FALSE\n'


def test_cli_rejects_an_impossible_seed_or_cap():
    for argv in (['play', '--seed', '-1', '--cap', '5000'],
                 ['play', '--seed', '7', '--cap', '1'],
                 ['determinism', '--seed', '4294967296', '--cap', '5000']):
        with pytest.raises(SystemExit):
            cli.main(argv)


# The trace seed 7 at cap 5,000 produced when T01 was written, on 2026-11-08.
# It is not a property of the seed alone: the game admits seasonal monsters on
# 24-26 December, so the same seed plays a different game then (finding 1 of
# the milestone-1 review). The hash is therefore asserted outside that window
# only, and the determinism of the pair is asserted always.
GOLDEN_SEED7_CAP5000 = '2242a3f55de1711fce9c37c5301c9ad3d4cdd9daf32cea8f44066b28a1d7d1f0'
SEASONAL_DAYS = {(12, 24), (12, 25), (12, 26)}


def seasonal_today():
    today = datetime.date.today()
    return (today.month, today.day) in SEASONAL_DAYS


@pytest.mark.slow
def test_seed_7_plays_twice_with_identical_traces(tmp_path):
    """T01's gate. Needs a compiler, CMake and libx11-dev; takes a few minutes."""
    out = build.prepare()
    assert build.binary(out).exists()
    traces = []
    for attempt in (1, 2):
        record = play.play(out, seed=7, cap=5000, output=tmp_path / f'run{attempt}',
                           lock=not os.environ.get('BORG_AGENT_NO_LOCK'))
        assert record['outcome'] in play.GOOD_OUTCOMES, record
        assert record['character'] == 'Measure Human Warrior'
        assert record['calendar']['utc']
        traces.append((tmp_path / f'run{attempt}/trace.txt').read_bytes())
    assert traces[0] and traces[0] == traces[1]
    recorded = json.loads((tmp_path / 'run1/result.json').read_text())['trace_sha256']
    assert recorded
    if not seasonal_today():
        assert recorded == GOLDEN_SEED7_CAP5000, (
            'the pinned build no longer plays seed 7 the way it did when T01 was written')
