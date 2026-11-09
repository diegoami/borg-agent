"""One run as a readable page (T30)."""
import json
import os
from pathlib import Path

import pytest

from borg_agent import agent, build, executor, mind, record, replay, report

ROOT = Path(__file__).resolve().parents[1]


def observation(decision=0, turn=1, depth=0, hp=10, sp=2, monsters=(), messages=(),
                spells=()):
    return {
        'schema': 'borg-agent/observation@1', 'run_id': 'paper', 'decision': decision,
        'turn': turn,
        'character': {'race': 'Human', 'class': 'Mage', 'level': 1, 'hp': hp, 'max_hp': 10,
                      'sp': sp, 'max_sp': 2, 'depth': depth, 'gold': 0, 'new_spells': 0},
        'map': {'player': {'x': 2, 'y': 1}, 'origin': {'x': 0, 'y': 0},
                'rows': ['#####', '#.@.#', '#####']},
        'monsters': list(monsters), 'objects': [],
        'inventory': [{'label': 'a', 'description': 'a Book of Magic Spells', 'count': 1}],
        'equipment': [], 'spells': list(spells), 'messages': list(messages),
        'prompt': {'kind': 'none', 'text': ''},
    }


def a_run(tmp_path, calls=True):
    """A run directory written by hand, so the page can be tested without play."""
    run = tmp_path / 'paper'
    run.mkdir()
    (run / 'result.json').write_text(json.dumps({
        'run_id': 'paper', 'seed': 2, 'turn_cap': 800, 'outcome': 'turn_cap',
        'final_turn': 30, 'decisions': 3, 'wall_seconds': 12.5,
        'character': 'Measure Human Mage', 'birth': 'Human Mage; default point buy',
        'birth_choice': {'race': 'Human', 'class': 'Mage'},
        'calendar': {'utc': '2026-11-09T12:00:00Z', 'seasonal': False},
    }))
    lizard = {'letter': 'R', 'name': 'rock lizard', 'x': 3, 'y': 1, 'distance': 1,
              'asleep': None, 'health': None}
    missile = {'book': 'a', 'letter': 'a', 'name': 'Magic Missile', 'level': 1, 'mana': 1,
               'fail_percent': 16, 'castable': True, 'studyable': False}
    (run / agent.OBSERVATION_LOG).write_text(''.join(json.dumps(o) + '\n' for o in (
        observation(0, 1, spells=[missile]),
        observation(1, 11, depth=1, spells=[missile]),
        observation(2, 21, depth=1, hp=6, monsters=[lizard], spells=[missile],
                    messages=['The rock lizard bites you.']),
    )))
    (run / agent.ACTION_LOG).write_text(''.join(json.dumps(a) + '\n' for a in (
        mind.action('primitive', 'go down', primitive={'name': 'take_stairs',
                                                       'direction': 'down'}),
        mind.action('primitive', 'look around', primitive={'name': 'explore_floor'}),
        mind.action('command', 'blast it', command={'name': 'cast', 'book': 'a',
                                                    'spell': 'a'}),
    )))
    (run / agent.JOURNAL_LOG).write_text(''.join(json.dumps(j) + '\n' for j in (
        {'kind': 'choice', 'decision': 0, 'turn': 1, 'chose': 'take_stairs',
         'answer': {'reason': 'Head down.'}},
        {'kind': 'stop', 'decision': 1, 'turn': 11, 'stop': 'changed_level'},
        {'kind': 'choice', 'decision': 2, 'turn': 21, 'chose': 'cast_at_nearest',
         'answer': {'reason': 'Blast the lizard.'}},
    )))
    if calls:
        (run / agent.MODEL_CALL_LOG).write_text(''.join(json.dumps(c) + '\n' for c in (
            {'decision': 0, 'turn': 1, 'seconds': 14.2, 'prompt_tokens': 2000,
             'completion_tokens': 700, 'reason': 'Head down.', 'reply': '{"kind": "..."}',
             'reasoning': 'The town is explored, so the dungeon is next.',
             'reasoning_chars': 46, 'parse_problem': None},
            {'decision': 2, 'turn': 21, 'seconds': 9.1, 'prompt_tokens': 2100,
             'completion_tokens': 400, 'reason': 'Blast the lizard.',
             'reply': 'nonsense', 'reasoning': None, 'reasoning_chars': 0,
             'parse_problem': 'not an action@1 document'},
        )))
    return run


def test_the_page_is_one_file_with_nothing_fetched(tmp_path):
    """Self-contained: it opens from a file:// URL with no network at all."""
    page = report.write(a_run(tmp_path))
    assert page.name == report.NAME
    text = page.read_text()
    assert text.startswith('<!doctype html>') and text.rstrip().endswith('</html>')
    for forbidden in ('src=', 'href=', 'http://', 'https://', '<script'):
        assert forbidden not in text, forbidden


def test_the_header_says_who_played_and_how_it_ended(tmp_path):
    text = report.write(a_run(tmp_path)).read_text()
    for fact in ('Measure Human Mage', 'turn_cap', 'seed', 'Human Mage; default point buy'):
        assert fact in text, fact
    # With no verdict beside the run, the page says so rather than implying one.
    assert 'not run here' in text


def test_a_verdict_is_quoted_when_there_is_one(tmp_path):
    run = a_run(tmp_path)
    (tmp_path / 'verify.json').write_text(json.dumps({
        'verified': True, 'scope': 'full', 'state_hashes_match': True,
        'first_differing_decision': None}))
    text = report.write(run, verdict=tmp_path / 'verify.json').read_text()
    assert 'reproduced' in text and 'every state hash equal' in text


def test_the_timeline_has_a_row_per_decision_with_what_was_chosen(tmp_path):
    rows = report.timeline(report.read(a_run(tmp_path)))
    assert [row['decision'] for row in rows] == [0, 1, 2]
    assert rows[0]['chose'] == 'take_stairs' and rows[0]['reason'] == 'Head down.'
    assert rows[0]['acted'] == 'take_stairs (direction=down)'
    assert rows[1]['stops'] == ['changed_level']
    assert rows[2]['monsters'] == ['rock lizard@1']
    assert rows[2]['acted'] == 'cast (book=a, spell=a)'


def test_a_decision_without_a_choice_says_what_was_still_running(tmp_path):
    """A blank row reads as a gap; it is the executor mid-primitive."""
    run = a_run(tmp_path)
    rows = report.timeline(report.read(run))
    assert rows[0]['chose'] == 'take_stairs' and rows[0]['running'] is None
    assert rows[1]['chose'] is None and rows[1]['running'] == 'take_stairs'
    assert 'still running' in report.write(run).read_text()


def test_the_events_are_the_turns_worth_jumping_to(tmp_path):
    found = [what for _row, what in report.events(report.read(a_run(tmp_path)))]
    assert any('depth 1' in what for what in found)
    assert any('first sight of rock lizard' in what for what in found)
    assert any('hit points 10 → 6' in what for what in found)
    assert any('could not be read' in what for what in found)


def test_a_stored_prompt_is_shown_as_it_was_sent(tmp_path):
    run = a_run(tmp_path)
    calls = [json.loads(line) for line
             in (run / agent.MODEL_CALL_LOG).read_text().splitlines() if line.strip()]
    calls[0]['prompt'] = [{'role': 'system', 'content': 'You are playing Angband.'},
                          {'role': 'user', 'content': 'Decision 0, turn 1. What now?'}]
    (run / agent.MODEL_CALL_LOG).write_text(''.join(json.dumps(c) + '\n' for c in calls))
    text = report.write(run).read_text()
    assert 'as it was sent' in text
    assert 'You are playing Angband.' in text
    assert 'Decision 0, turn 1. What now?' in text


def test_a_prompt_that_was_not_stored_is_rebuilt_and_said_to_be(tmp_path):
    """Runs made before T30 kept only the pack's hash and the size, and
    `render` is deterministic, so the page rebuilds the prompt -- and says so,
    because the knowledge block of the day cannot be rebuilt."""
    run = a_run(tmp_path)
    calls = [json.loads(line) for line
             in (run / agent.MODEL_CALL_LOG).read_text().splitlines() if line.strip()]
    calls[0]['prompt_pack'] = 'play-1'
    calls[0]['prompt_pack_sha256'] = 'x' * 64
    (run / agent.MODEL_CALL_LOG).write_text(''.join(json.dumps(c) + '\n' for c in calls))
    text = report.write(run).read_text()
    assert 'rebuilt from the play-1 pack' in text
    # The pack moved, so the page refuses to pretend it is the same prompt.
    assert 'CHANGED since this run' in text
    assert 'knowledge block of the day is not rebuildable' in text


def test_a_call_with_neither_says_so(tmp_path):
    run = a_run(tmp_path)
    calls = [json.loads(line) for line
             in (run / agent.MODEL_CALL_LOG).read_text().splitlines() if line.strip()]
    for call in calls:
        call.pop('prompt_pack', None)
    (run / agent.MODEL_CALL_LOG).write_text(''.join(json.dumps(c) + '\n' for c in calls))
    assert 'not rebuildable' in report.write(run).read_text()


def test_the_thinking_and_the_failures_are_on_the_page(tmp_path):
    text = report.write(a_run(tmp_path)).read_text()
    assert 'The town is explored, so the dungeon is next.' in text
    assert '46 characters' in text
    assert 'not an action@1 document' in text


def test_the_spells_are_a_table_with_what_a_caster_decides_on(tmp_path):
    text = report.write(a_run(tmp_path)).read_text()
    assert 'Magic Missile' in text and '16%' in text


def test_a_run_without_a_model_still_renders(tmp_path):
    text = report.write(a_run(tmp_path, calls=False)).read_text()
    assert 'Model calls' not in text
    assert 'Timeline' in text


def test_a_directory_that_is_not_a_run_says_so(tmp_path):
    with pytest.raises(ValueError, match='not a run directory'):
        report.read(tmp_path)


def test_everything_on_the_page_is_escaped(tmp_path):
    run = a_run(tmp_path)
    observations = (run / agent.OBSERVATION_LOG).read_text().splitlines()
    first = json.loads(observations[0])
    first['messages'] = ['<script>alert("x")</script>']
    (run / agent.OBSERVATION_LOG).write_text(
        '\n'.join([json.dumps(first)] + observations[1:]) + '\n')
    text = report.write(run).read_text()
    assert '<script' not in text
    assert '&lt;script&gt;' in text


@pytest.mark.slow
def test_a_real_run_renders_and_quotes_its_own_verdict(tmp_path):
    """T30's gate: play, record, verify, and read the page that comes out."""
    out = build.prepare(log=lambda *a: None)
    lock = not os.environ.get('BORG_AGENT_NO_LOCK')
    played = agent.play_with_mind(out, seed=1, cap=400, output=tmp_path / 'play',
                                  mind=executor.ExecutingMind(mind.PrimitiveMind()),
                                  lock=lock, log=lambda *a: None)
    record.write_record(tmp_path / 'play')
    verdict = replay.verify(tmp_path / 'play', tmp_path / 'verify', lock=lock,
                            log=lambda *a: None)
    assert verdict['verified'], verdict

    page = report.write(tmp_path / 'play', verdict=tmp_path / 'verify' / replay.VERIFY_NAME)
    text = page.read_text()
    assert 'reproduced' in text
    assert str(played['decisions']) in text
    # The map pictures are the observation's own rows, not the sparse screen.
    assert text.count('<figure>') >= 1
    assert '#' in text
