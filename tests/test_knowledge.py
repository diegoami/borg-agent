"""The knowledge store and mode D consolidation (T07)."""
import json
from pathlib import Path

import pytest

from borg_agent import consolidate, knowledge, models, prompts

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'schemas/examples/claim'


def example(name='valid-hypothesis-from-one-death.json', **changes):
    claim = json.loads((EXAMPLES / name).read_text())
    claim.update(changes)
    return claim


def store(tmp_path):
    return knowledge.Store(root=tmp_path / 'knowledge')


# --- what may enter the store -----------------------------------------------

def test_a_claim_enters_and_can_be_read_back(tmp_path):
    kept = store(tmp_path)
    added = kept.add(example())
    assert kept.all() == [added]
    assert kept.ids() == {added['id']}
    assert len(kept.sha256()) == 64


def test_a_claim_that_breaks_the_schema_is_refused(tmp_path):
    with pytest.raises(knowledge.KnowledgeError, match='statement'):
        store(tmp_path).add(example(statement='two\nlines'))


def test_a_claim_that_carries_a_credential_is_refused(tmp_path):
    # Milestone 3 review, finding 4: claims are model words with a worse
    # destination than a log -- git, the views, and every later prompt.
    kept = store(tmp_path)
    with pytest.raises(knowledge.KnowledgeError, match='RULES 16'):
        kept.add(example(statement='the shop sells wine with sk-abcdefghijklmnop1234'))
    with pytest.raises(knowledge.KnowledgeError, match='RULES 16'):
        kept.add(example(confidence='seen once; bearer abcdefghijklmnop was in the log'))
    assert kept.all() == []


def test_superseding_does_not_leave_half_a_store(tmp_path, monkeypatch):
    # The pointer is written as a rewrite of the whole file; a crash mid-write
    # must not shorten the store (review note).
    kept = store(tmp_path)
    first = kept.add(example(id='green-naga-bite'))
    before = kept.path.read_text()

    def explode(*_args, **_kwargs):
        raise OSError('disk full')

    monkeypatch.setattr('os.replace', explode)
    with pytest.raises(OSError):
        kept.supersede(first['id'], example(id='green-naga-bite-again'))
    # The append happened and survives; only the pointer is missing, which is
    # recoverable. What must never happen is a truncated store or a leftover
    # temporary file beside it.
    assert kept.path.read_text().startswith(before)
    assert [c['id'] for c in kept.all()] == ['green-naga-bite', 'green-naga-bite-again']
    assert 'superseded_by' not in kept.all()[0]
    assert not list(kept.path.parent.glob('claims.jsonl.*'))


def test_a_claim_that_breaks_a_rule_a_schema_cannot_express_is_refused(tmp_path):
    # borg_agent.checks: more successes than trials (R4).
    with pytest.raises(knowledge.KnowledgeError, match='successes'):
        store(tmp_path).add(example(
            basis={'kind': 'quantified', 'trials': 3, 'successes': 9},
            status='supported'))


def test_a_model_never_promotes_its_own_claim(tmp_path):
    # R4.3. Whatever it asked for, it enters as a hypothesis, and the claim
    # says that it was lowered.
    kept = store(tmp_path)
    added = kept.add(example(status='corroborated'), by_model=True)
    assert added['status'] == 'hypothesis'
    assert any('never promotes' in note for note in added['notes'])


def test_a_person_or_a_probe_may_set_a_status(tmp_path):
    # The same claim, added without by_model, keeps what it says -- it is the
    # model that is restrained, not the store.
    kept = store(tmp_path)
    added = kept.add(example(
        name='valid-quantified-tactic-with-a-test.json'))
    assert added['status'] == 'supported'


def test_the_same_id_cannot_enter_twice(tmp_path):
    kept = store(tmp_path)
    kept.add(example())
    with pytest.raises(knowledge.KnowledgeError, match='already in the store'):
        kept.add(example())


def test_a_correction_is_a_new_claim_that_supersedes_the_old_one(tmp_path):
    kept = store(tmp_path)
    first = kept.add(example())
    second = kept.supersede(first['id'], example(id='floating-eye-is-worse-than-that'))
    claims = {claim['id']: claim for claim in kept.all()}
    assert claims[first['id']]['superseded_by'] == second['id']
    assert 'superseded_by' not in claims[second['id']]
    # The old claim still says what it said: only the pointer was added.
    assert claims[first['id']]['statement'] == first['statement']


def test_superseding_something_that_is_not_there_is_refused(tmp_path):
    with pytest.raises(knowledge.KnowledgeError, match='no claim with the id'):
        store(tmp_path).supersede('never-existed', example())


# --- the views --------------------------------------------------------------

def test_a_view_is_written_for_each_area_and_an_index(tmp_path):
    kept = store(tmp_path)
    kept.add(example())                                        # danger
    kept.add(example(name='valid-documented-from-the-manual.json'))   # dungeon
    written = kept.render_views()
    assert set(written) == {'danger', 'dungeon', 'index'}
    danger = (tmp_path / 'knowledge/danger.md').read_text()
    assert '# Danger claims' in danger
    assert 'Do not edit' in danger
    claim = example()
    assert claim['statement'] in danger
    assert claim['confidence']['rests_on'] in danger
    assert 'seed 1865911738, turn 14310' in danger
    index = (tmp_path / 'knowledge/README.md').read_text()
    assert '[danger](danger.md)' in index and '[dungeon](dungeon.md)' in index


def test_a_view_shows_what_moved_a_claim_and_what_would_test_it(tmp_path):
    kept = store(tmp_path)
    kept.add(example(name='valid-quantified-tactic-with-a-test.json'))
    kept.render_views()
    tactic = (tmp_path / 'knowledge/tactic.md').read_text()
    assert 'quantified, 3 of 20' in tactic
    assert 'how to test it' in tactic
    assert 'review' in tactic


def test_an_area_that_empties_loses_its_view(tmp_path):
    kept = store(tmp_path)
    kept.add(example())
    kept.render_views()
    assert (tmp_path / 'knowledge/danger.md').exists()
    kept.path.write_text('')                   # as if every claim were withdrawn
    kept.render_views()
    assert not (tmp_path / 'knowledge/danger.md').exists()
    assert (tmp_path / 'knowledge/README.md').exists()


def test_the_repositorys_own_views_are_what_the_claims_say():
    # The views in git are generated; a stale one would mislead a reader.
    kept = knowledge.Store()
    if not kept.all():
        pytest.skip('the knowledge base is empty')
    for area, claims in kept.by_area().items():
        path = Path(kept.root) / f'{area}.md'
        assert path.exists(), area
        assert path.read_text() == knowledge.view(area, claims), (
            f'{area}.md is stale; run `python -m borg_agent knowledge views`')


# --- what a prompt is given --------------------------------------------------

def test_retrieval_leaves_out_what_cannot_apply(tmp_path):
    kept = store(tmp_path)
    kept.add(example(id='for-a-mage', scope={'class': 'Mage', 'version': '4.2.6'}))
    kept.add(example(id='for-the-deep',
                     scope={'depth': {'min': 20}, 'version': '4.2.6'}))
    kept.add(example(id='for-anyone', scope={'version': '4.2.6'}))
    warrior = {'character': {'class': 'Warrior', 'race': 'Human', 'depth': 2, 'level': 3}}
    found = {claim['id'] for claim in kept.retrieve(warrior)}
    assert found == {'for-anyone'}
    # With no observation, nothing is filtered out.
    assert len(kept.retrieve()) == 3


def test_a_superseded_claim_is_not_put_in_a_prompt(tmp_path):
    kept = store(tmp_path)
    first = kept.add(example())
    kept.supersede(first['id'], example(id='the-better-one'))
    assert [claim['id'] for claim in kept.retrieve()] == ['the-better-one']


def test_what_a_prompt_gets_is_one_line_per_claim(tmp_path):
    kept = store(tmp_path)
    kept.add(example())
    lines = kept.for_prompt().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith('- ') and 'hypothesis' in lines[0]
    assert example()['id'] in lines[0]


def test_the_best_established_claims_come_first(tmp_path):
    kept = store(tmp_path)
    kept.add(example(id='a-guess'))
    kept.add(example(name='valid-quantified-tactic-with-a-test.json'))
    statuses = [claim['status'] for claim in kept.retrieve()]
    assert statuses == ['supported', 'hypothesis']


# --- consolidation (mode D) --------------------------------------------------

CHOICE = models.Choice(job='consolidate', provider='house', model='big', family='alpha',
                       base_url='https://house.example/v1', api_key_env='HOUSE_KEY',
                       context_k=128, effort=None, profile='house', chosen_by='profile')


def a_run(tmp_path, outcome='death', cause='a wild cat'):
    """A run directory with just enough in it to consolidate."""
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'result.json').write_text(json.dumps({
        'run_id': 'run-1', 'seed': 42, 'outcome': outcome, 'cause': cause,
        'final_turn': 900, 'decisions': 30, 'character': 'Measure Human Warrior',
        'calendar': {'utc': '2026-11-09T12:00:00Z'},
        'states': [{'kind': 'death', 'turn': 900, 'max_depth': 2, 'max_level': 4}],
    }))
    (run / 'decisions.jsonl').write_text(json.dumps({
        'kind': 'choice', 'turn': 100, 'chose': 'fight_nearest',
        'answer': {'reason': 'It is next to me.', 'note': 'the cat hits hard'}}) + '\n')
    (run / 'trace.txt').write_text('MESSAGE oldest\nMESSAGE The wild cat claws you.\n')
    return run


def a_claim(**changes):
    claim = {
        'id': 'wild-cat-claws-hurt', 'statement': 'A wild cat claws for several hit points.',
        'area': 'monster', 'scope': {'version': '4.2.6'},
        'basis': {'kind': 'observed'},
        'evidence': [{'kind': 'run', 'run_id': 'run-1', 'seed': 1, 'turn': 100,
                      'note': 'it clawed the warrior'}],
        'confidence': {'rests_on': 'one fight', 'alternatives_ruled_out': []},
    }
    claim.update(changes)
    return claim


def replying(text):
    def transport(messages):
        return {'choices': [{'message': {'content': text}}],
                'usage': {'prompt_tokens': 900, 'completion_tokens': 300}}
    return transport


def test_the_run_is_described_to_the_consolidator(tmp_path):
    facts = consolidate.facts(a_run(tmp_path))
    assert facts['run_id'] == 'run-1' and facts['seed'] == 42
    assert facts['outcome'] == 'death' and 'wild cat' in facts['cause']
    assert facts['max_depth'] == 2 and facts['max_level'] == 4
    assert 'the cat hits hard' in facts['notes']
    assert 'fight_nearest' in facts['journal'] and 'It is next to me.' in facts['journal']
    # The newest messages, which are the ones that explain the ending.
    assert 'The wild cat claws you.' in facts['messages']


def test_claims_are_read_however_the_model_wraps_them():
    assert consolidate.claims_from('[{"id": "a"}]') == [{'id': 'a'}]
    assert consolidate.claims_from('Here:\n```json\n[{"id": "a"}]\n```') == [{'id': 'a'}]
    # One claim rather than an array is still an answer.
    assert consolidate.claims_from('{"id": "a"}') == [{'id': 'a'}]
    with pytest.raises(ValueError):
        consolidate.claims_from('I have nothing to say')


def test_a_claim_is_anchored_to_the_run_and_its_author_named():
    facts = {'run_id': 'run-1', 'seed': 42, 'created': '2026-11-09T12:00:00Z'}
    anchored = consolidate.anchor(a_claim(), facts, CHOICE)
    assert anchored['evidence'][0]['seed'] == 42          # the run knows the seed
    assert anchored['produced_by'] == {'mind': 'model', 'model': 'big', 'family': 'alpha',
                                       'profile': 'house', 'run_id': 'run-1'}
    assert anchored['phase'] == 1 and anchored['sources'] == ['own-play']


def test_a_claim_that_points_at_nothing_in_the_run_is_refused():
    facts = {'run_id': 'run-1', 'seed': 42, 'created': '2026-11-09T12:00:00Z'}
    with pytest.raises(knowledge.KnowledgeError, match='points at no turn'):
        consolidate.anchor(a_claim(evidence=[{'kind': 'manual', 'reference': 'somewhere'}]),
                           facts, CHOICE)
    with pytest.raises(knowledge.KnowledgeError, match='points at no turn'):
        consolidate.anchor(
            a_claim(evidence=[{'kind': 'run', 'run_id': 'another-run', 'seed': 1, 'turn': 2}]),
            facts, CHOICE)


def test_consolidation_puts_what_it_accepts_in_the_store(tmp_path):
    run = a_run(tmp_path)
    kept = store(tmp_path)
    result = consolidate.consolidate(
        run, CHOICE, store=kept, pack=prompts.load_pack('consolidate-1'),
        transport=replying(json.dumps([a_claim()])), log=lambda *a: None)
    assert result['added'] == ['wild-cat-claws-hurt'] and result['refused'] == []
    assert result['offered'] == 1
    stored = kept.all()[0]
    assert stored['status'] == 'hypothesis'          # whatever it asked for (R4.3)
    assert stored['produced_by']['model'] == 'big'
    # The consolidation is recorded beside the run, with what it cost.
    recorded = json.loads((run / consolidate.RECORD_NAME).read_text())
    assert recorded['model'] == 'big' and recorded['usage']['used']['model_calls'] == 1
    assert recorded['knowledge_sha256'] == kept.sha256()
    assert recorded['prompt_pack']['version'] == 'consolidate-1'
    # And the views are rebuilt, so what a person reads is never stale.
    assert (tmp_path / 'knowledge/monster.md').exists()


def test_a_claim_the_store_refuses_is_recorded_not_hidden(tmp_path):
    run = a_run(tmp_path)
    kept = store(tmp_path)
    result = consolidate.consolidate(
        run, CHOICE, store=kept,
        pack=prompts.load_pack('consolidate-1'),
        transport=replying(json.dumps([a_claim(), a_claim(statement='two\nlines',
                                                          id='bad-one')])),
        log=lambda *a: None)
    assert result['added'] == ['wild-cat-claws-hurt']
    assert [refused['id'] for refused in result['refused']] == ['bad-one']
    assert 'statement' in result['refused'][0]['why']


def test_a_model_that_has_nothing_to_say_is_not_a_failure(tmp_path):
    run = a_run(tmp_path)
    kept = store(tmp_path)
    result = consolidate.consolidate(
        run, CHOICE, store=kept, pack=prompts.load_pack('consolidate-1'),
        transport=replying('[]'), log=lambda *a: None)
    assert result['offered'] == 0 and result['added'] == [] and result['refused'] == []
    assert kept.all() == []


def test_the_consolidation_pack_carries_the_rules_that_matter():
    pack = prompts.load_pack('consolidate-1')
    assert pack.job == 'consolidate'
    system = pack.templates['system']
    for rule in ('One statement per claim', 'points at a turn', 'Status is not yours',
                 'Do not invent'):
        assert rule in system, rule
