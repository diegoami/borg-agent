"""Prompt packs (T06): what the model is told, and where it came from."""
import json
from pathlib import Path

import pytest

from borg_agent import executor, prompts

ROOT = Path(__file__).resolve().parents[1]


def observation(**changes):
    base = {
        'schema': 'borg-agent/observation@1', 'run_id': 'test', 'decision': 3, 'turn': 31,
        'character': {'race': 'Human', 'class': 'Warrior', 'level': 2, 'hp': 9, 'max_hp': 18,
                      'depth': 2, 'gold': 40, 'conditions': ['Afraid']},
        'map': {'player': {'x': 10, 'y': 5}, 'origin': {'x': 0, 'y': 0},
                'rows': ['#' * 20] + ['#' + '.' * 18 + '#'] * 9 + ['#' * 20]},
        'monsters': [{'letter': 'r', 'name': 'a rat', 'x': 12, 'y': 5}],
        'objects': [], 'inventory': [{'label': 'a', 'description': 'a Ration of Food'}],
        'equipment': [], 'messages': ['You hit the rat.'], 'prompt': {'kind': 'none'},
    }
    base.update(changes)
    return base


# --- the pack ---------------------------------------------------------------

def test_the_pack_loads_with_its_extracts_resolved_at_their_pins():
    pack = prompts.load_pack('play-1')
    assert pack.job == 'play' and pack.version == 'play-1'
    assert len(pack.sha256) == 64
    extract = pack.extracts['movement_and_resting_commands']
    assert extract.source == 'manual' and extract.path == 'docs/command.rst'
    assert extract.commit == prompts.pins.pin('better-borg-c')['commit']
    assert 'Movement Commands' in extract.text
    # Bounded: the section asked for, not the whole page.
    assert 1000 < len(extract.text) < 8000
    assert 'Alter Commands' not in extract.text


def test_the_packs_hash_covers_its_templates_and_extracts():
    pack = prompts.load_pack('play-1')
    assert prompts.load_pack('play-1').sha256 == pack.sha256
    assert pack.record() == {'version': 'play-1', 'sha256': pack.sha256}


def test_the_packs_hash_covers_the_generated_primitives(monkeypatch):
    """Milestone 3 review, finding 8.

    `primitive_help()` is generated from the executor and goes into every
    system message, but it was generated at render time and left out of the
    hash -- so two runs with the same pack sha could have been told different
    things about the primitives.
    """
    pack = prompts.load_pack('play-1')
    assert pack.primitives and 'walk_to' in pack.primitives
    assert pack.primitives in prompts.render(pack, observation())[0]['content']

    monkeypatch.setattr(prompts, 'primitive_help',
                        lambda: 'one primitive: wave_hands (no arguments)')
    changed = prompts.load_pack('play-1')
    assert changed.sha256 != pack.sha256
    assert 'wave_hands' in prompts.render(changed, observation())[0]['content']


def test_the_provenance_names_every_extract():
    provenance = prompts.load_pack('play-1').provenance()
    assert provenance and all(
        set(entry) == {'as', 'source', 'pin', 'path', 'commit', 'sha256'} for entry in provenance)
    for entry in provenance:
        assert entry['source'] in prompts.allowed_sources()


def test_a_pack_may_only_draw_on_a_source_pins_json_names(tmp_path):
    # The test is about provenance, not permission (D8): a pack must say where
    # its words came from, and `pins.json` is the list of places.
    pack = tmp_path / 'bad-1'
    pack.mkdir()
    (pack / 'system.md').write_text('hello')
    (pack / 'pack.json').write_text(json.dumps({
        'schema': prompts.SCHEMA, 'version': 'bad-1', 'job': 'play',
        'templates': {'system': 'system.md'},
        'extracts': [{'as': 'x', 'source': 'a-forum-post', 'pin': 'better-borg-c',
                      'path': 'docs/command.rst'}]}))
    with pytest.raises(prompts.PromptError, match='not a source in pins.json'):
        prompts.load_pack('bad-1', root=tmp_path)


def test_a_pack_may_not_read_a_source_at_another_pin(tmp_path):
    pack = tmp_path / 'bad-2'
    pack.mkdir()
    (pack / 'system.md').write_text('hello')
    (pack / 'pack.json').write_text(json.dumps({
        'schema': prompts.SCHEMA, 'version': 'bad-2', 'job': 'play',
        'templates': {'system': 'system.md'},
        'extracts': [{'as': 'x', 'source': 'manual', 'pin': 'borg-rs',
                      'path': 'docs/PROGRESS.md'}]}))
    with pytest.raises(prompts.PromptError, match='is read at the better-borg-c pin'):
        prompts.load_pack('bad-2', root=tmp_path)


def test_a_missing_pack_says_so(tmp_path):
    with pytest.raises(prompts.PromptError, match='no prompt pack'):
        prompts.load_pack('nowhere', root=tmp_path)


# --- what the model is told about the primitives -----------------------------

def test_the_primitives_are_described_from_the_executor_itself():
    described = prompts.primitive_help()
    for name in executor.PRIMITIVES:
        assert f'`{name}`' in described, name
    # And the stops each one reports, read from its own code.
    assert 'explored' in described and 'no_target' in described and 'healed' in described
    # Not a stop of any primitive, so it must not be claimed as one.
    assert 'cheat' not in described


def test_a_primitive_nobody_described_is_an_error(monkeypatch):
    monkeypatch.setitem(executor.PRIMITIVES, 'teleport_home', executor.WalkTo)
    with pytest.raises(prompts.PromptError, match='teleport_home'):
        prompts.primitive_help()


# --- the summary a prompt carries -------------------------------------------

def test_the_summary_is_a_window_with_the_player_in_it():
    summary = prompts.summarise(observation(), width=11, height=5)
    rows = summary['map'].splitlines()
    assert len(rows) <= 5 and all(len(row) <= 11 for row in rows)
    assert sum(row.count('@') for row in rows) == 1
    assert 'window' in summary['map_note']


def test_the_summary_carries_what_the_mind_needs():
    summary = prompts.summarise(observation())
    assert 'Human Warrior' in summary['character'] and '9/18' in summary['character']
    assert 'Afraid' in summary['character']
    assert 'a rat' in summary['monsters'] and '2 away' in summary['monsters']
    assert 'Ration of Food' in summary['inventory']
    assert 'You hit the rat.' in summary['messages']
    assert summary['prompt'].startswith('No prompt')
    assert summary['last_stop'] == ''


def test_the_summary_says_why_it_was_asked_again():
    summary = prompts.summarise(observation(last_stop='explored'))
    assert 'explored' in summary['last_stop']


def test_a_shop_is_in_the_summary_with_its_prices():
    summary = prompts.summarise(observation(shop={
        'kind': 'General Store',
        'stock': [{'label': 'c', 'description': '40 Rations of Food', 'price': 3}]}))
    assert 'General Store' in summary['inventory']
    assert '`c` 40 Rations of Food — 3 gold' in summary['inventory']


def test_the_same_observation_always_summarises_the_same_way():
    assert prompts.summarise(observation()) == prompts.summarise(observation())


# --- the messages -----------------------------------------------------------

def test_render_gives_a_system_and_a_user_message():
    pack = prompts.load_pack('play-1')
    messages = prompts.render(pack, observation())
    assert [message['role'] for message in messages] == ['system', 'user']
    system, user = (message['content'] for message in messages)
    # The system message carries the primitives and the manual's own words,
    # with the citation that makes them checkable.
    assert 'walk_to' in system and 'Movement Commands' in system
    assert 'docs/command.rst at better-borg-c' in system
    assert 'action@1' in system
    assert 'Turn 31, decision 3' in user and '@' in user


def test_a_decision_fits_the_context_the_profile_allows():
    from borg_agent import models

    pack = prompts.load_pack('play-1')
    messages = prompts.render(pack, observation())
    characters = sum(len(message['content']) for message in messages)
    # Four characters to a token is the usual rule of thumb; the smallest
    # context any profile gives must still leave room to answer.
    smallest = min(models.load()[job].context_k for job in models.JOBS)
    assert characters / 4 < smallest * 1000 / 2, characters


def test_knowledge_joins_the_system_message_when_there_is_any():
    pack = prompts.load_pack('play-1')
    messages = prompts.render(pack, observation(), knowledge='- a floating eye paralyses')
    assert 'floating eye paralyses' in messages[0]['content']
    assert 'What you have learned' in messages[0]['content']
