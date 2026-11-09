"""One run, as a page a person can read (T30).

A run directory is five JSON Lines files and a record, which is complete and
unreadable: every session so far has rebuilt the same timeline by hand with a
throwaway script. This writes that timeline, the model's calls and reasoning,
the inventory, equipment and spells, and the known map at the turns that
matter, into **one self-contained HTML file** — no server, no dependencies, no
external requests, so it opens from a `file://` URL and can be attached to a
pull request.

It only reads. A run directory and its record are immutable (R4.1), it needs no
model and no key, and it is not where facts live: a claim still cites the run
and the turn (R4).
"""
import html
import json
from pathlib import Path

from . import agent, record as record_module, replay

NAME = 'report.html'
# How many map pictures to draw. Enough to see the shape of a run; a timeline
# row exists for every decision anyway.
MAPS = 8


# --- reading the run --------------------------------------------------------

def lines(path):
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def read(run_dir, verdict=None):
    """Everything the page needs, from the files the run wrote."""
    run_dir = Path(run_dir)
    if not (run_dir / 'result.json').exists():
        raise ValueError(f'{run_dir} holds no result.json: it is not a run directory')
    parts = {
        'run': run_dir,
        'result': json.loads((run_dir / 'result.json').read_text()),
        'observations': lines(run_dir / agent.OBSERVATION_LOG),
        'actions': lines(run_dir / agent.ACTION_LOG),
        'journal': lines(run_dir / agent.JOURNAL_LOG),
        'calls': lines(run_dir / agent.MODEL_CALL_LOG),
        'record': None,
        'probe': None,
        'verdict': None,
    }
    for name, key in ((record_module.RECORD_NAME, 'record'),
                      ('probe-result.json', 'probe')):
        if (run_dir / name).exists():
            parts[key] = json.loads((run_dir / name).read_text())
    if verdict:
        parts['verdict'] = json.loads(Path(verdict).read_text())
    elif (run_dir / replay.VERIFY_NAME).exists():
        parts['verdict'] = json.loads((run_dir / replay.VERIFY_NAME).read_text())
    return parts


def timeline(parts):
    """One row per decision: what was seen, what was chosen, what stopped."""
    chosen = {}
    stopped = {}
    # The journal's order inside one decision matters: the executor may stop a
    # primitive and be given another in the same breath (its PATIENCE loop), so
    # what is still running afterwards is whichever came last.
    sequence = {}
    for entry in parts['journal']:
        sequence.setdefault(entry['decision'], []).append(entry)
        if entry.get('kind') == 'choice':
            chosen[entry['decision']] = entry
        elif entry.get('kind') == 'stop':
            stopped.setdefault(entry['decision'], []).append(entry)
    calls = {}
    for call in parts['calls']:
        calls.setdefault(call.get('decision'), []).append(call)
    rows = []
    running = None
    for index, observation in enumerate(parts['observations']):
        action = parts['actions'][index] if index < len(parts['actions']) else None
        character = observation.get('character') or {}
        choice = chosen.get(observation['decision'])
        rows.append({
            # A decision the mind was not asked about is not a gap: a primitive
            # was still running, and saying which is what makes the table read.
            'running': running if not choice else None,
            'decision': observation['decision'],
            'turn': observation['turn'],
            'depth': character.get('depth'),
            'hp': character.get('hp'),
            'max_hp': character.get('max_hp'),
            'sp': character.get('sp'),
            'max_sp': character.get('max_sp'),
            'level': character.get('level'),
            'chose': (choice or {}).get('chose'),
            'reason': (choice or {}).get('answer', {}).get('reason') if choice else None,
            'acted': describe_action(action),
            'stops': [entry['stop'] for entry in stopped.get(observation['decision'], ())],
            'monsters': [f"{m['name'] or m['letter']}" + (f"@{m['distance']}"
                                                          if m.get('distance') is not None
                                                          else '')
                         for m in observation.get('monsters') or ()],
            'messages': [m for m in observation.get('messages') or ()],
            'calls': len(calls.get(observation['decision'], ())),
            'observation': observation,
        })
        # What carries into the next row: the entries of this decision, in the
        # order they happened. A primitive that stopped here was running during
        # this decision, so the row above keeps it.
        for entry in sequence.get(observation['decision'], ()):
            running = entry.get('chose') if entry.get('kind') == 'choice' else None
    return rows


def describe_action(action):
    """The action as one short phrase."""
    if not action:
        return None
    if action['kind'] == 'primitive':
        primitive = action['primitive']
        extra = ', '.join(f'{k}={v}' for k, v in sorted(primitive.items()) if k != 'name')
        return primitive['name'] + (f' ({extra})' if extra else '')
    if action['kind'] == 'keys':
        return f"keys {action['keys']['keys']!r}"
    command = dict(action.get('command') or {})
    name = command.pop('name', '?')
    extra = ', '.join(f'{k}={v}' for k, v in sorted(command.items()))
    return name + (f' ({extra})' if extra else '')


def events(parts, hp_drop=3):
    """The turns worth jumping to, in order."""
    found = []
    rows = timeline(parts)
    seen_monsters = set()
    depth = None
    last_hp = None
    for row in rows:
        if row['depth'] != depth:
            found.append((row, f"depth {row['depth']}"
                               + (f" (was {depth})" if depth is not None else ' — the start')))
            depth = row['depth']
        for monster in row['monsters']:
            kind = monster.split('@')[0]
            if kind not in seen_monsters:
                seen_monsters.add(kind)
                found.append((row, f'first sight of {kind}'))
        if last_hp is not None and row['hp'] is not None and last_hp - row['hp'] >= hp_drop:
            found.append((row, f"hit points {last_hp} → {row['hp']}"))
        if row['hp'] is not None:
            last_hp = row['hp']
        for message in row['messages']:
            if 'AGENT refused' in message:
                found.append((row, message.strip('# ').strip()))
            elif 'dies' in message or 'destroyed' in message:
                found.append((row, message.strip()))
    for call in parts['calls']:
        if call.get('parse_problem'):
            row = next((r for r in rows if r['decision'] == call.get('decision')), None)
            if row:
                found.append((row, f"the reply could not be read: {call['parse_problem']}"))
    return found


def map_moments(parts):
    """The decisions to draw a map for: the shape of the run in a few pictures."""
    rows = timeline(parts)
    if not rows:
        return []
    wanted = {rows[0]['decision']: 'the start', rows[-1]['decision']: 'the last decision'}
    depth = rows[0]['depth']
    for row in rows:
        if row['depth'] != depth:
            wanted.setdefault(row['decision'], f"arriving at depth {row['depth']}")
            depth = row['depth']
        if row['monsters'] and row['chose']:
            wanted.setdefault(row['decision'], f"deciding with {', '.join(row['monsters'])}")
    for row in rows:
        if row['calls'] and len(wanted) < MAPS:
            wanted.setdefault(row['decision'], 'a model call')
    chosen = [row for row in rows if row['decision'] in wanted][:MAPS]
    return [(row, wanted[row['decision']]) for row in chosen]


def prompt_of(call, observations):
    """The prompt for a call, and how the page came by it.

    A run made since T30 has it in the call log. An older one does not, and
    `render` is deterministic, so the page rebuilds it from the pack the call
    names and the observation it was asked about — and says that is what it
    did, because the knowledge block of the day cannot be rebuilt: the store
    has moved on.
    """
    stored = call.get('prompt')
    if stored:
        return stored, 'as it was sent'
    version = call.get('prompt_pack')
    observation = observations.get(call.get('decision'))
    if not version or not observation:
        return None, 'not stored with this run, and not rebuildable'
    try:
        from . import prompts

        pack = prompts.load_pack(version)
        messages = prompts.render(pack, observation)
    except Exception as problem:                       # a pack that is gone, a pin away
        return None, f'not stored with this run; rebuilding it failed ({problem})'
    note = (f'rebuilt from the {version} pack and this observation'
            if pack.sha256 == call.get('prompt_pack_sha256')
            else f'rebuilt from the {version} pack, which has CHANGED since this run '
                 f'({call.get("prompt_pack_sha256", "")[:12]} then, {pack.sha256[:12]} now)')
    return messages, note + '; the knowledge block of the day is not rebuildable'


# --- the page ---------------------------------------------------------------

STYLE = """
:root { color-scheme: light dark; --line: #d8d8d8; --dim: #666; --bg: #fff;
        --fg: #111; --head: #f4f4f4; --accent: #1a5fb4; }
@media (prefers-color-scheme: dark) {
  :root { --line: #333; --dim: #999; --bg: #15161a; --fg: #e8e8e8;
          --head: #1e2026; --accent: #78aeed; }
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); margin: 0 auto; max-width: 1100px;
       padding: 16px; font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 28px 0 8px; border-bottom: 1px solid var(--line);
     padding-bottom: 4px; }
.sub { color: var(--dim); margin: 0 0 18px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border-bottom: 1px solid var(--line); padding: 4px 6px; text-align: left;
         vertical-align: top; }
th { background: var(--head); position: sticky; top: 0; font-weight: 600; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
.facts { display: grid; grid-template-columns: max-content 1fr; gap: 2px 14px;
         font-size: 14px; }
.facts dt { color: var(--dim); }
.facts dd { margin: 0; }
pre { background: var(--head); border: 1px solid var(--line); padding: 10px;
      overflow-x: auto; font: 13px/1.25 ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
.chose { color: var(--accent); font-weight: 600; }
.msg { color: var(--dim); }
details { margin: 4px 0; }
summary { cursor: pointer; }
.maps { display: flex; flex-wrap: wrap; gap: 14px; }
.maps figure { margin: 0; flex: 1 1 320px; }
.maps figcaption { color: var(--dim); font-size: 13px; margin-bottom: 4px; }
.good { color: #26a269; } .bad { color: #c01c28; }
@media (max-width: 700px) { body { padding: 12px 16px; } table { font-size: 12px; } }
"""


def e(value):
    return html.escape('' if value is None else str(value))


def facts(parts):
    """The header: who played, how it ended, what it cost."""
    result = parts['result']
    recorded = parts['record'] or {}
    game = recorded.get('game') or {}
    birth = game.get('birth') or {}
    mind = recorded.get('mind') or {}
    usage = recorded.get('usage') or {}
    rows = [
        ('run', result.get('run_id') or parts['run'].name),
        ('mode', (recorded.get('mode') or 'play')
         + (' (an intervention, kept out of survival figures)'
            if recorded.get('intervention') else '')),
        ('character', result.get('character') or f"{birth.get('race', '?')} "
                                                 f"{birth.get('class', '?')}"),
        ('birth', f"{result.get('birth', '?')}"
                  + (f" — rule {birth['rule']}" if birth.get('rule') else '')),
        ('seed', result.get('seed')),
        ('turn cap', result.get('turn_cap')),
        ('took over at turn', result.get('from_turn') or '—  (played from birth)'),
        ('outcome', f"{result.get('outcome')}"
                    + (f" — {result.get('cause')}" if result.get('cause') else '')
                    + (f" at turn {result.get('final_turn')}"
                       if result.get('final_turn') else '')),
        ('decisions', result.get('decisions')),
        ('wall seconds', result.get('wall_seconds')),
    ]
    if mind:
        rows += [
            ('mind', f"{mind.get('provider')}/{mind.get('model')} ({mind.get('family')}), "
                     f"profile {mind.get('profile')}, chosen by {mind.get('chosen_by')}"),
            ('prompt pack', f"{(mind.get('prompt_pack') or {}).get('version')} "
                            f"{((mind.get('prompt_pack') or {}).get('sha256') or '')[:12]}"),
            ('knowledge', (mind.get('knowledge_sha256') or '—')[:12]),
            ('model calls', f"{usage.get('model_calls', len(parts['calls']))}"
                            + (f", {usage['prompt_tokens']} prompt + "
                               f"{usage['completion_tokens']} completion tokens"
                               if usage.get('prompt_tokens') is not None else '')),
        ]
    if parts['verdict']:
        verdict = parts['verdict']
        rows.append(('verify', ('reproduced' if verdict.get('verified') else 'did NOT reproduce')
                     + f" — scope {verdict.get('scope')}, "
                     + ('every state hash equal' if verdict.get('state_hashes_match')
                        else f"first difference at decision "
                             f"{verdict.get('first_differing_decision')}")))
    else:
        rows.append(('verify', 'not run here — `python -m borg_agent verify --run …`'))
    engine = (parts['record'] or {}).get('engine') or {}
    if engine:
        rows.append(('build', f"{engine.get('build_key')} · game pin "
                              f"{(engine.get('pins') or {}).get('better-borg-c', '')[:12]} · "
                              f"this repository {str(engine.get('commit'))[:12]}"
                              + (' (dirty)' if engine.get('dirty') else '')))
    return rows


def render(parts):
    """The whole page, as one string."""
    result = parts['result']
    rows = timeline(parts)
    name = result.get('run_id') or parts['run'].name
    out = [f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
           f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
           f'<title>{e(name)} run report</title>\n<style>{STYLE}</style>\n</head>\n'
           f'<body>\n<h1>{e(name)}</h1>']
    out.append(f'<p class="sub">{e(result.get("character") or "")} · '
               f'{e(result.get("outcome"))} · {len(rows)} decisions · '
               f'{len(parts["calls"])} model calls</p>')

    out.append('<h2>The run</h2>\n<dl class="facts">')
    for label, value in facts(parts):
        out.append(f'<dt>{e(label)}</dt><dd>{e(value)}</dd>')
    out.append('</dl>')

    if parts['probe']:
        probe = parts['probe']
        out.append('<h2>Probe</h2>')
        out.append(f'<p>{e(probe.get("question"))} — predicate '
                   f'<code>{e(probe.get("predicate"))}</code>, '
                   f'{e(len(probe.get("seeds") or []))} declared seeds, cap '
                   f'{e(probe.get("cap"))}.</p>')
        out.append('<table><tr><th>arm</th><th class="n">trials</th>'
                   '<th class="n">successes</th><th class="n">deaths</th>'
                   '<th class="n">monster died</th></tr>')
        for arm, counts in (probe.get('arms') or {}).items():
            out.append(f'<tr><td>{e(arm)}</td><td class="n">{e(counts.get("trials"))}</td>'
                       f'<td class="n">{e(counts.get("successes"))}</td>'
                       f'<td class="n">{e(counts.get("deaths"))}</td>'
                       f'<td class="n">{e(counts.get("monster_died"))}</td></tr>')
        out.append('</table>')
        if not probe.get('control_isolated_the_action', True):
            out.append('<p class="bad">The control arm ended the situation too, so these '
                       'counts do not separate the action from being there.</p>')

    out.append('<h2>What happened</h2>')
    for row, what in events(parts):
        out.append(f'<p class="msg">decision {row["decision"]}, turn {row["turn"]}: '
                   f'{e(what)}</p>')

    out.append('<h2>Timeline</h2>\n<table>')
    out.append('<tr><th class="n">dec</th><th class="n">turn</th><th class="n">depth</th>'
               '<th class="n">hp</th><th class="n">sp</th><th>chose</th><th>acted</th>'
               '<th>stopped</th><th>in sight</th><th>messages</th></tr>')
    for row in rows:
        if row['chose']:
            chose = f'<span class="chose">{e(row["chose"])}</span>'
        elif row['running']:
            chose = f'<span class="msg">{e(row["running"])}, still running</span>'
        else:
            chose = ''
        if row['reason']:
            chose += f'<br><span class="msg">{e(row["reason"])}</span>'
        messages = '<br>'.join(e(m) for m in row['messages'][:4])
        out.append(
            f'<tr><td class="n">{e(row["decision"])}</td><td class="n">{e(row["turn"])}</td>'
            f'<td class="n">{e(row["depth"])}</td>'
            f'<td class="n">{e(row["hp"])}/{e(row["max_hp"])}</td>'
            f'<td class="n">{e(row["sp"])}/{e(row["max_sp"])}</td>'
            f'<td>{chose}</td><td>{e(row["acted"])}</td>'
            f'<td>{e(", ".join(row["stops"]))}</td>'
            f'<td>{e(", ".join(row["monsters"]))}</td>'
            f'<td class="msg">{messages}</td></tr>')
    out.append('</table>')

    if parts['calls']:
        observations = {o['decision']: o for o in parts['observations']}
        out.append('<h2>Model calls</h2>')
        out.append('<p class="msg">Every call carries what was asked and what came back: '
                   'the prompt, the model\'s own thinking, and the reply it was parsed '
                   'from.</p>\n<table>')
        out.append('<tr><th class="n">dec</th><th class="n">turn</th><th class="n">s</th>'
                   '<th class="n">prompt<br>tokens</th><th class="n">out<br>tokens</th>'
                   '<th>asked, thought, answered</th></tr>')
        for call in parts['calls']:
            inner = [f'<p>{e(call.get("reason"))}</p>']
            prompt, how = prompt_of(call, observations)
            if prompt:
                inner.append(f'<details><summary>prompt — {e(how)}</summary>'
                             + ''.join(f'<p class="msg">{e(message["role"])}</p>'
                                       f'<pre>{e(message["content"])}</pre>'
                                       for message in prompt)
                             + '</details>')
            else:
                inner.append(f'<p class="msg">prompt: {e(how)}</p>')
            if call.get('reasoning'):
                inner.append(f'<details><summary>thinking — '
                             f'{e(call.get("reasoning_chars"))} characters</summary>'
                             f'<pre>{e(call["reasoning"])}</pre></details>')
            else:
                inner.append('<p class="msg">thinking: none sent by this provider</p>')
            inner.append(f'<details><summary>reply — {e(len(call.get("reply") or ""))} '
                         f'characters</summary><pre>{e(call.get("reply"))}</pre></details>')
            if call.get('parse_problem'):
                inner.append(f'<p class="bad">{e(call["parse_problem"])}</p>')
            out.append(
                f'<tr><td class="n">{e(call.get("decision"))}</td>'
                f'<td class="n">{e(call.get("turn"))}</td>'
                f'<td class="n">{e(round(call.get("seconds") or 0, 1))}</td>'
                f'<td class="n">{e(call.get("prompt_tokens"))}</td>'
                f'<td class="n">{e(call.get("completion_tokens"))}</td>'
                f'<td>{"".join(inner)}</td></tr>')
        out.append('</table>')

    out.append('<h2>The map, at a few moments</h2>\n<div class="maps">')
    for row, why in map_moments(parts):
        known = row['observation']['map']
        out.append(f'<figure><figcaption>decision {row["decision"]}, turn {row["turn"]} — '
                   f'{e(why)}</figcaption><pre>{e(chr(10).join(known["rows"]))}</pre>'
                   f'</figure>')
    out.append('</div>')

    last = parts['observations'][-1] if parts['observations'] else {}
    for field, columns in (('inventory', ('label', 'description', 'count')),
                           ('equipment', ('label', 'description', 'count'))):
        items = last.get(field) or []
        if not items:
            continue
        out.append(f'<h2>{field.title()} at the end</h2>\n<table><tr>'
                   + ''.join(f'<th>{e(c)}</th>' for c in columns) + '</tr>')
        for item in items:
            out.append('<tr>' + ''.join(f'<td>{e(item.get(c))}</td>' for c in columns)
                       + '</tr>')
        out.append('</table>')

    spells = last.get('spells') or []
    if spells:
        out.append('<h2>Spells at the end</h2>\n<table><tr><th>book</th><th>letter</th>'
                   '<th>name</th><th class="n">level</th><th class="n">mana</th>'
                   '<th class="n">fail</th><th>castable</th><th>studyable</th></tr>')
        for spell in spells:
            out.append(
                f'<tr><td>{e(spell["book"])}</td><td>{e(spell["letter"])}</td>'
                f'<td>{e(spell["name"])}</td><td class="n">{e(spell["level"])}</td>'
                f'<td class="n">{e(spell["mana"])}</td>'
                f'<td class="n">{e(spell["fail_percent"])}%</td>'
                f'<td class="{"good" if spell["castable"] else ""}">'
                f'{"yes" if spell["castable"] else "no"}</td>'
                f'<td>{"yes" if spell["studyable"] else "no"}</td></tr>')
        out.append('</table>')

    out.append('<h2>Where this came from</h2>')
    out.append(f'<p class="msg">Written by <code>python -m borg_agent report --run '
               f'{e(parts["run"])}</code> from the run\'s own files. It reads and never '
               f'writes: the run and its record are immutable (R4.1). A claim cites the run '
               f'and the turn, not this page.</p>')
    out.append('</body>\n</html>\n')
    return '\n'.join(out)


def write(run_dir, output=None, verdict=None):
    """Render the page beside the run, or wherever asked."""
    parts = read(run_dir, verdict)
    path = Path(output) if output else Path(run_dir) / NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(parts))
    return path
