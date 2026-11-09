"""The knowledge base: claims in JSON Lines, and the views over them (T07).

The knowledge base is the product (R4). A claim is one plain statement with
its evidence, and it lives in `knowledge/claims.jsonl`, appended and never
rewritten: a correction is a new claim that supersedes the old one, which is
the same discipline run records keep (R4.1).

Two things guard the store, and they are not the same thing:

- the **schema** (`claim@1`) checks the shape;
- **`borg_agent.checks`** checks what a schema cannot — that a model has not
  promoted its own claim, that a review came from another family, that a
  counted basis counts (R4.3).

Everything a model writes enters as `hypothesis`, whatever it asked for.
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from . import checks, pins

STORE = pins.ROOT / 'knowledge'
CLAIMS = 'claims.jsonl'
SCHEMA = 'borg-agent/claim@1'
# What a model may claim, however sure it sounds (R4.3).
MODEL_STATUS = 'hypothesis'
# The order a view lists claims in: what is best established first.
STATUS_ORDER = ('corroborated', 'supported', 'documented', 'quantified', 'hypothesis',
                'contested', 'refuted', 'unknown')
AREAS = ('monster', 'item', 'spell', 'class', 'race', 'town', 'dungeon', 'mechanic',
         'danger', 'tactic', 'readiness')


class KnowledgeError(ValueError):
    """A claim cannot enter the store, and why."""


def _write_atomically(path, text):
    """Replace a file in one step, so a crash cannot leave half a store."""
    import os
    import tempfile

    path = Path(path)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + '.')
    try:
        with os.fdopen(handle, 'w') as out:
            out.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def validate(claim):
    """Against `claim@1`, then against the rules a schema cannot express.

    A claim is scanned for credentials first, like a run record (RULES 16). It
    is model words with a worse destination than a log: `knowledge/claims.jsonl`
    is in git, the Markdown views are generated from it, and `for_prompt` reads
    it back into every later prompt. Milestone 3's review found this path
    unscanned (finding 4).
    """
    from jsonschema import Draft202012Validator, FormatChecker

    from .record import secrets_in

    leaks = secrets_in(claim)
    if leaks:
        raise KnowledgeError('; '.join(leaks[:4]))
    schema = json.loads((pins.ROOT / 'schemas' / 'claim@1.json').read_text())
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker())
                    .iter_errors(claim), key=str)
    if errors:
        raise KnowledgeError('; '.join(
            f'{list(e.absolute_path)}: {e.message}' for e in errors[:4]))
    problems = checks.check_claim(claim)
    if problems:
        raise KnowledgeError('; '.join(problems))
    return claim


@dataclass
class Store:
    """The claims on disk, and what may be done to them."""

    root: Path = STORE

    @property
    def path(self):
        return Path(self.root) / CLAIMS

    def all(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def ids(self):
        return {claim['id'] for claim in self.all()}

    def sha256(self):
        return (hashlib.sha256(self.path.read_bytes()).hexdigest()
                if self.path.exists() else None)

    def add(self, claim, by_model=False):
        """Append one claim, or refuse it and say why.

        `by_model` is the honest flag: a claim a model wrote enters as
        `hypothesis` whatever status it asked for (R4.3), and the claim records
        that it was lowered.
        """
        claim = json.loads(json.dumps(claim))        # never hold the caller's object
        claim.setdefault('schema', SCHEMA)
        if by_model and claim.get('status') != MODEL_STATUS:
            asked = claim.get('status')
            claim['status'] = MODEL_STATUS
            if asked:
                claim.setdefault('notes', []).append(
                    f'a model asked for {asked!r}; a model never promotes its own claim past '
                    f'{MODEL_STATUS!r} (R4.3)')
        validate(claim)
        if claim['id'] in self.ids():
            raise KnowledgeError(
                f'a claim with the id {claim["id"]!r} is already in the store; a correction is a '
                f'new claim that supersedes it (R4.1)')
        Path(self.root).mkdir(parents=True, exist_ok=True)
        with self.path.open('a') as claims:
            claims.write(json.dumps(claim, sort_keys=True) + '\n')
        return claim

    def supersede(self, old_id, claim, by_model=False):
        """Add a claim that replaces another, and point the old one at it."""
        if old_id not in self.ids():
            raise KnowledgeError(f'no claim with the id {old_id!r} to supersede')
        added = self.add(claim, by_model=by_model)
        # The store is append-only, so the pointer is written as a rewrite of
        # the file with the one field added -- the only edit allowed, and it
        # adds a pointer rather than changing what a claim says.
        claims = []
        for existing in self.all():
            if existing['id'] == old_id:
                existing = {**existing, 'superseded_by': added['id']}
            claims.append(existing)
        _write_atomically(self.path,
                          ''.join(json.dumps(c, sort_keys=True) + '\n' for c in claims))
        return added

    # --- reading ------------------------------------------------------------

    def by_area(self):
        areas = {}
        for claim in self.all():
            areas.setdefault(claim['area'], []).append(claim)
        for claims in areas.values():
            claims.sort(key=lambda c: (STATUS_ORDER.index(c['status'])
                                       if c['status'] in STATUS_ORDER else len(STATUS_ORDER),
                                       c['id']))
        return areas

    def retrieve(self, observation=None, limit=12):
        """The claims worth putting in a prompt, best established first.

        Relevance is mechanical: a claim whose scope names a class, a race or
        a depth the character does not have is left out. Nothing here judges
        whether a claim is useful — that is the mind's business.
        """
        character = (observation or {}).get('character') or {}
        chosen = []
        for claim in self.all():
            if claim.get('superseded_by'):
                continue
            scope = claim.get('scope') or {}
            if scope.get('class') and character.get('class') and \
                    scope['class'] != character['class']:
                continue
            if scope.get('race') and character.get('race') and scope['race'] != character['race']:
                continue
            for field, value in (('depth', character.get('depth')),
                                 ('character_level', character.get('level'))):
                window = scope.get(field) or {}
                if value is None or not window:
                    continue
                if window.get('min') is not None and value < window['min']:
                    break
                if window.get('max') is not None and value > window['max']:
                    break
            else:
                chosen.append(claim)
        chosen.sort(key=lambda c: (STATUS_ORDER.index(c['status'])
                                   if c['status'] in STATUS_ORDER else len(STATUS_ORDER),
                                   c['id']))
        return chosen[:limit]

    def for_prompt(self, observation=None, limit=12):
        """The retrieved claims as the lines a prompt carries."""
        lines = []
        for claim in self.retrieve(observation, limit):
            basis = claim['basis']
            how = basis['kind']
            if how == 'quantified':
                how = f"quantified {basis.get('successes')} of {basis.get('trials')}"
            lines.append(f"- {claim['statement']} [{claim['status']}, {how}, {claim['id']}]")
        return '\n'.join(lines)

    # --- the views ----------------------------------------------------------

    def render_views(self):
        """A Markdown file per area, which a person can read without tools."""
        root = Path(self.root)
        root.mkdir(parents=True, exist_ok=True)
        areas = self.by_area()
        written = {}
        for area, claims in sorted(areas.items()):
            path = root / f'{area}.md'
            path.write_text(view(area, claims))
            written[area] = path
        index = root / 'README.md'
        index.write_text(index_view(areas, self.path.name))
        written['index'] = index
        # An area with nothing left in it keeps no view.
        for stale in root.glob('*.md'):
            if stale.name != 'README.md' and stale.stem not in areas:
                stale.unlink()
        return written


def view(area, claims):
    """One area's claims, generated. Never edited by hand."""
    lines = [f'# {area.capitalize()} claims', '',
             '*Generated from `claims.jsonl` by `python -m borg_agent knowledge views`. '
             'Do not edit: a claim changes by being superseded, never by being rewritten.*', '']
    for claim in claims:
        basis = claim['basis']
        how = basis['kind']
        if how == 'quantified':
            how = f"quantified, {basis.get('successes')} of {basis.get('trials')}"
        lines += [f"## {claim['statement']}", '',
                  f"- **id** `{claim['id']}` · **status** {claim['status']}"
                  + (f" · **superseded by** `{claim['superseded_by']}`"
                     if claim.get('superseded_by') else ''),
                  f"- **basis** {how}"
                  + (f" — {basis['reference']}" if basis.get('reference') else ''),
                  f"- **scope** {scope_line(claim.get('scope') or {})}",
                  f"- **engine** {claim['engine']} · **phase** {claim['phase']}"
                  f" · **sources** {', '.join(claim['sources'])}",
                  f"- **rests on** {claim['confidence']['rests_on']}"]
        ruled_out = claim['confidence'].get('alternatives_ruled_out') or []
        if ruled_out:
            lines.append('- **ruled out**: ' + '; '.join(ruled_out))
        if claim.get('test'):
            lines.append(f"- **how to test it** {claim['test']['how']}")
        lines.append('- **evidence**')
        for piece in claim['evidence']:
            if piece['kind'] == 'run':
                lines.append(f"  - run `{piece['run_id']}`, seed {piece.get('seed')}, "
                             f"turn {piece['turn']}"
                             + (f" — {piece['note']}" if piece.get('note') else ''))
            else:
                lines.append(f"  - {piece['kind']}: {piece.get('reference')}")
        for review in claim.get('reviews') or []:
            lines.append(f"- **review** by {review['by']}"
                         f" ({review.get('family') or 'a probe'}): {review['verdict']}"
                         + (f" — {review['note']}" if review.get('note') else ''))
        for note in claim.get('notes') or []:
            lines.append(f'- **note** {note}')
        lines.append('')
    return '\n'.join(lines) + '\n'


def scope_line(scope):
    parts = []
    for field in ('class', 'race', 'gear', 'version'):
        if scope.get(field):
            parts.append(f'{field} {scope[field]}')
    for field in ('character_level', 'depth'):
        window = scope.get(field) or {}
        if window:
            low, high = window.get('min'), window.get('max')
            parts.append(f'{field.replace("_", " ")} {low if low is not None else "any"}'
                         f'–{high if high is not None else "any"}')
    return ', '.join(parts) or 'anything'


def index_view(areas, source):
    lines = ['# The knowledge base', '',
             f'*Generated from `{source}`. The claims themselves are the JSON Lines; '
             'these pages are for reading.*', '',
             '| Area | Claims | Best established |', '|---|---|---|']
    for area, claims in sorted(areas.items()):
        best = min((claim['status'] for claim in claims),
                   key=lambda status: (STATUS_ORDER.index(status)
                                       if status in STATUS_ORDER else len(STATUS_ORDER)),
                   default='—')
        lines.append(f'| [{area}]({area}.md) | {len(claims)} | {best} |')
    if not areas:
        lines.append('| — | 0 | — |')
    return '\n'.join(lines) + '\n'
