"""Mode D: turning one run into claims (R3, T07).

A run is evidence; a claim is what somebody can argue with. Consolidation
reads a finished run — its outcome, its decisions and the agent's own notes —
and asks the `consolidate` model what it teaches. Everything it answers enters
the store as a `hypothesis`, whatever it asked for (R4.3), and a claim that
does not point at a turn of that run is refused.
"""
import json
from pathlib import Path
from string import Template

from . import agent, knowledge, model_mind, prompts, record

PACK = 'consolidate-1'
RECORD_NAME = 'consolidation.json'


def facts(run_dir):
    """What the run has to say about itself, for the prompt."""
    run_dir = Path(run_dir)
    result = json.loads((run_dir / 'result.json').read_text())
    states = result.get('states') or []
    last = states[-1] if states else {}
    journal = []
    path = run_dir / agent.JOURNAL_LOG
    if path.exists():
        journal = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    notes = []
    calls = run_dir / 'model-calls.jsonl'
    if calls.exists():
        notes = [json.loads(line).get('note') for line in calls.read_text().splitlines()
                 if line.strip()]
    notes += [(entry.get('answer') or {}).get('note') for entry in journal]
    trace = run_dir / 'trace.txt'
    messages = []
    if trace.exists():
        # The observer writes the message log oldest first, so the newest -
        # the ones that explain how the run ended - are at the end.
        messages = [line[8:] for line in trace.read_text().splitlines()
                    if line.startswith('MESSAGE ')][-12:]
    return {
        'run_id': result.get('run_id') or run_dir.name,
        'seed': result['seed'],
        'birth': result.get('character') or result.get('birth', 'unknown'),
        'outcome': result['outcome'],
        'cause': f", killed by {result['cause']}" if result['outcome'] == 'death' else '',
        'turns': result.get('final_turn') or last.get('turn', 0),
        'decisions': result.get('decisions', 0),
        'max_depth': last.get('max_depth', 0),
        'max_level': last.get('max_level', 1),
        'notes': ', '.join(note for note in notes if note) or 'none',
        'journal': '\n'.join(
            f"- turn {entry['turn']}: {entry.get('chose') or ('stopped: ' + str(entry.get('stop')))}"
            + (f" — {(entry.get('answer') or {}).get('reason')}"
               if (entry.get('answer') or {}).get('reason') else '')
            for entry in journal[:60]) or '- (nothing recorded)',
        'messages': '\n'.join(f'- {message}' for message in messages) or '- (none)',
    }


def render(pack, run_facts):
    """The messages for one consolidation."""
    system = Template(pack.templates['system']).safe_substitute(
        run_id=run_facts['run_id'], seed=run_facts['seed'])
    return [{'role': 'system', 'content': system},
            {'role': 'user',
             'content': Template(pack.templates['decision']).substitute(**run_facts)}]


def claims_from(reply):
    """The claims in a reply: a JSON array, however it is wrapped."""
    start = reply.find('[')
    while start != -1:
        depth = 0
        for index in range(start, len(reply)):
            if reply[index] == '[':
                depth += 1
            elif reply[index] == ']':
                depth -= 1
                if depth == 0:
                    try:
                        found = json.loads(reply[start:index + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(found, list):
                        return found
                    break
        start = reply.find('[', start + 1)
    # A model that answers with one claim rather than an array is still
    # answering.
    try:
        return [model_mind.extract_action(reply)]
    except ValueError:
        raise ValueError('the reply held no claims') from None


def anchor(claim, run_facts, choice=None):
    """Force a claim to point at this run, and to say who wrote it.

    A model does not get to assert its own identity, or the run's seed: the
    harness knows both, and a claim that disagrees would be unverifiable. Nor
    does it set its status — `Store.add(by_model=True)` sees to that (R4.3).
    """
    claim = json.loads(json.dumps(claim))
    claim['schema'] = knowledge.SCHEMA
    claim.setdefault('engine', 'c-4.2.6')
    claim.setdefault('phase', 1)
    claim.setdefault('sources', ['own-play'])
    claim.setdefault('created', run_facts['created'])
    claim['produced_by'] = {
        'mind': 'model',
        'model': choice.model if choice else None,
        'family': choice.family if choice else None,
        'profile': choice.profile if choice else None,
        'run_id': run_facts['run_id'],
    }
    evidence = [piece for piece in (claim.get('evidence') or [])
                if piece.get('kind') != 'run' or piece.get('run_id') == run_facts['run_id']]
    for piece in evidence:
        if piece.get('kind') == 'run':
            # The model may mistype the seed or leave it out; the run knows it.
            piece['run_id'] = run_facts['run_id']
            piece['seed'] = run_facts['seed']
    if not any(piece.get('kind') == 'run' for piece in evidence):
        raise knowledge.KnowledgeError(
            f'the claim {claim.get("id")!r} points at no turn of run '
            f'{run_facts["run_id"]!r}, so nothing can check it')
    claim['evidence'] = evidence
    return claim


# A consolidator reads a whole run and reasons over it, which takes much
# longer than choosing a primitive: the first real call timed out at the play
# mind's 120 seconds.
DEFAULT_TIMEOUT = 420


def consolidate(run_dir, choice, store=None, pack=None, budget=None, call_log=None,
                transport=None, environ=None, timeout=DEFAULT_TIMEOUT, log=print):
    """Read a run, ask the consolidator, and put what it says in the store."""
    run_dir = Path(run_dir)
    store = store or knowledge.Store()
    pack = pack or prompts.load_pack(PACK)
    budget = budget or model_mind.Budget(model_calls=4)
    run_facts = facts(run_dir)
    run_facts['created'] = json.loads(
        (run_dir / 'result.json').read_text())['calendar']['utc']
    messages = render(pack, run_facts)

    client = None if transport else model_mind.ChatClient(choice, environ, timeout=timeout)
    post = transport or client.post
    budget.check()
    import time

    started = time.monotonic()
    answer = post(messages)
    reply, usage = model_mind.reply_of(answer)
    budget.spend(usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
    elapsed = round(time.monotonic() - started, 3)

    if call_log is not None:
        call_log.write({
            'job': choice.job, 'provider': choice.provider, 'model': choice.model,
            'family': choice.family, 'effort': choice.effort,
            'endpoint_host': choice.endpoint_host(),
            'prompt_pack': pack.version, 'prompt_pack_sha256': pack.sha256,
            'run': run_facts['run_id'], 'reply': reply,
            'prompt_tokens': usage.get('prompt_tokens'),
            'completion_tokens': usage.get('completion_tokens'), 'seconds': elapsed,
        })

    offered = claims_from(reply)
    added, refused = [], []
    for claim in offered:
        try:
            added.append(store.add(anchor(claim, run_facts, choice), by_model=True))
        except (knowledge.KnowledgeError, KeyError, TypeError) as problem:
            refused.append({'id': (claim or {}).get('id'), 'why': str(problem)[:300]})
    store.render_views()

    consolidation = {
        'schema': 'borg-agent/consolidation@1',
        'run': run_facts['run_id'],
        'run_record': str(run_dir / record.RECORD_NAME),
        'mode': 'consolidate',
        'job': choice.job,
        'provider': choice.provider,
        'model': choice.model,
        'family': choice.family,
        'profile': choice.profile,
        'chosen_by': choice.chosen_by,
        'endpoint_host': choice.endpoint_host(),
        'prompt_pack': pack.record(),
        'offered': len(offered),
        'added': [claim['id'] for claim in added],
        'refused': refused,
        'usage': budget.record(),
        'knowledge_sha256': store.sha256(),
        'seconds': elapsed,
    }
    (run_dir / RECORD_NAME).write_text(
        json.dumps(consolidation, indent=2, sort_keys=True) + '\n')
    log(json.dumps({k: consolidation[k] for k in
                    ('run', 'model', 'offered', 'added', 'refused')}))
    return consolidation
