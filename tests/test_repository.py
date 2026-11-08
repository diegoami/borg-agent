"""Keeps the pins, the plan and the docs consistent, so a new session can trust them."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ('todo', 'in progress', 'in review', 'done')


def plan_rows():
    rows = []
    for line in (ROOT / 'PLAN.md').read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) == 5 and re.fullmatch(r'T\d\d', cells[0]):
            rows.append(cells)
    return rows


def test_pins_are_full_commits():
    data = json.loads((ROOT / 'pins.json').read_text())
    assert data['schema'] == 'borg-agent/pins@1'
    for name, pin in data['pins'].items():
        assert re.fullmatch(r'diegoami/[\w.-]+', pin['repository']), name
        assert re.fullmatch(r'[0-9a-f]{40}', pin['commit']), name
        assert pin['role'], name
    manual = data['manual']
    assert manual['pin'] in data['pins']
    assert manual['paths'] and not any('hacking' in p or 'gamedata' in p for p in manual['paths'])


def test_plan_status_table():
    rows = plan_rows()
    ids = [r[0] for r in rows]
    assert ids == sorted(set(ids)) and ids, ids
    for task, _title, needs, _cloud, status in rows:
        assert status.split(' (')[0] in STATUSES, (task, status)
        for need in re.findall(r'T\d\d', needs):
            assert need in ids and need < task, (task, need)
        assert f'### {task}.' in (ROOT / 'PLAN.md').read_text(), task


def test_local_links_resolve():
    for doc in [ROOT / 'README.md', ROOT / 'AGENTS.md', ROOT / 'RULES.md', ROOT / 'PLAN.md',
                *sorted((ROOT / 'docs').glob('*.md'))]:
        for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)', doc.read_text()):
            if '://' in target:
                continue
            assert (doc.parent / target).exists(), f'{doc.name} links to missing {target}'


def test_session_start_hook_runs_setup():
    settings = json.loads((ROOT / '.claude/settings.json').read_text())
    commands = [h['command'] for entry in settings['hooks']['SessionStart'] for h in entry['hooks']]
    assert any('scripts/setup.sh' in c for c in commands)
    assert (ROOT / 'scripts/setup.sh').stat().st_mode & 0o111
