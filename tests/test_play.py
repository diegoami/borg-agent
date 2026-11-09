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


# The trace seed 7 at cap 5,000 produces on the pinned build. It is a property
# of the pin as much as of the seed: better-borg-c milestone 6 gave
# 2242a3f5..., milestone 8 gives this. Nor is it a property of the seed alone —
# the game admits seasonal monsters on 24-26 December, so the same seed plays a
# different game then (decision D9) — so the hash is asserted outside that
# window only, while the determinism of the pair is asserted always.
GOLDEN_SEED7_CAP5000 = 'a6ffbae042dddaabfd8d48a9b6d3546d935c422249062fe633f10688ee4ce844'
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


def test_the_birth_input_is_exactly_the_runners():
    # Review's test note: a prefix is not enough. This is the runner's INPUT at
    # the pin, character for character.
    import ast
    import re

    from borg_agent import pins

    runner = pins.show('runner', 'tools/measure-native.py').decode()
    theirs = ast.literal_eval(re.search(r"INPUT = ('''.*?''')", runner, re.S).group(1))
    assert play.BIRTH_INPUT == theirs


def test_the_outcome_vocabulary_is_read_from_the_zoo_not_copied():
    # The zoo's design document at its pin lists the classes its runner uses.
    from borg_agent import pins

    design = pins.show('borg-zoo', 'docs/DESIGN.md').decode()
    listed = design[design.index('- **Outcomes:**'):][:400]
    for kind in ('death', 'turn_cap', 'stalled', 'borg_stopped', 'decision_cap',
                 'harness_failure'):
        assert kind in listed, kind
        # Each of the zoo's classes is one of ours, with its one rename.
        ours = 'agent_stopped' if kind == 'borg_stopped' else kind
        assert ours in play.GOOD_OUTCOMES + play.HARNESS_OUTCOMES, ours


@pytest.mark.slow
def test_a_death_and_the_checkpoint_saves(tmp_path):
    """The paths T08 needs: a run that dies, with the runner's saves kept.

    The stock Borg used to oblige on seed 7 within 100,000 turns; at
    better-borg-c milestone 8 it survives that (and takes two minutes to prove
    it), so the death comes from an agent run instead. The checkpoint path is
    the runner's either way: the observer forks and saves, so neither the save
    nor its monster-list compaction touches live play.
    """
    from borg_agent import agent, mind

    out = build.prepare(log=lambda *a: None)
    record = agent.play_with_mind(out, seed=7, cap=2000, output=tmp_path / 'death',
                                  mind=mind.ScriptedMind(), checkpoint_saves=True,
                                  timeout=300, stall_timeout=60,
                                  lock=not os.environ.get('BORG_AGENT_NO_LOCK'),
                                  log=lambda *a: None)
    assert record['outcome'] == 'death', record['outcome']
    assert record['cause'] and record['cause'] != '(alive and well)'
    assert record['checkpoint_saves'] is True
    assert (tmp_path / 'death/start.save').exists()
    assert any(state['kind'] == 'checkpoint' for state in record['states'])


def test_the_seasonal_days_are_the_games_own():
    """Not a copied constant: the game's own condition, read at the pin.

    `get_mon_num` admits RF_SEASONAL monsters only when the local date matches,
    and play.SEASONAL_DAYS has to be that date set (the review's point (e)).
    """
    import re

    from borg_agent import pins

    source = pins.show('better-borg-c', 'src/mon-make.c').decode()
    seasonal = source[source.index('RF_SEASONAL'):]
    window = seasonal[:seasonal.index('}', seasonal.index('tm_mday'))]
    month = int(re.search(r'tm_mon\s*==\s*(\d+)', window).group(1))
    days = sorted(int(day) for day in re.findall(r'tm_mday\s*[=<>!]*\s*(\d+)', window))
    # The game counts months from zero, so 11 is December.
    assert {(month + 1, day) for day in range(min(days), max(days) + 1)} \
        == set(play.SEASONAL_DAYS), (month, days, play.SEASONAL_DAYS)
