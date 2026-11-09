"""Prompt packs: what a model is told, and where every word of it came from.

A pack is a directory under `prompts/`, versioned by its name. It holds the
templates and a manifest naming the **extracts** it draws on: each one a
source from `pins.json`, a path, and the headings between which the text was
taken. Nothing in a pack is game knowledge the developer brought from
elsewhere (docs/SOURCES.md): what it says about the game is quoted from a
source, at a pin, and the pack records which — so a claim made from that
prompt can cite it.

The pack's hash covers the templates, the manifest and every extract, so a
run record names exactly what the model was told.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

from . import executor, pins

PACKS = pins.ROOT / 'prompts'
MANIFEST = 'pack.json'
SCHEMA = 'borg-agent/prompt-pack@1'
# How much of the known map to show, around the player. The whole of it is
# often thousands of squares; a prompt gets a window, and says that it is one.
MAP_WIDTH = 61
MAP_HEIGHT = 21


class PromptError(ValueError):
    """A pack is missing, malformed, or draws on something it may not."""


def heading_sections(text):
    """The reStructuredText sections of a manual page, by heading."""
    sections, order = {}, []
    pattern = re.compile(r'^(?P<title>\S.*)\n(?P<rule>[=\-~^"\']{3,})$', re.M)
    marks = [(m.group('title').strip(), m.start()) for m in pattern.finditer(text)]
    for index, (title, start) in enumerate(marks):
        end = marks[index + 1][1] if index + 1 < len(marks) else len(text)
        sections[title] = text[start:end]
        order.append(title)
    return sections, order


@dataclass(frozen=True)
class Extract:
    """One quoted piece of a source, with where it came from."""

    name: str
    source: str
    pin: str
    path: str
    commit: str
    text: str

    @property
    def citation(self):
        return f'{self.path} at {self.pin} {self.commit[:12]}'

    @property
    def sha256(self):
        return hashlib.sha256(self.text.encode()).hexdigest()


@dataclass(frozen=True)
class Pack:
    version: str
    job: str
    templates: dict
    extracts: dict
    sha256: str

    def record(self):
        """What the run record says about the pack (R2.1)."""
        return {'version': self.version, 'sha256': self.sha256}

    def provenance(self):
        """Every extract, with its source and the commit it was read at."""
        return [{'as': extract.name, 'source': extract.source, 'pin': extract.pin,
                 'path': extract.path, 'commit': extract.commit,
                 'sha256': extract.sha256}
                for extract in self.extracts.values()]


def allowed_sources():
    """The sources of `pins.json`, which is what a pack may draw on (D8)."""
    return {name: entry for name, entry in pins.pins()['sources'].items() if name != 'note'}


def load_pack(version='play-1', root=None):
    """Read a pack, resolve its extracts at their pins, and hash the whole."""
    directory = Path(root or PACKS) / version
    manifest_path = directory / MANIFEST
    if not manifest_path.exists():
        raise PromptError(f'no prompt pack at {directory}')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('schema') != SCHEMA:
        raise PromptError(f'{manifest_path} is not a {SCHEMA} manifest')
    if manifest.get('version') != version:
        raise PromptError(f'{manifest_path} calls itself {manifest.get("version")!r}, '
                          f'but it lives in {version!r}')
    sources = allowed_sources()
    digest = hashlib.sha256(manifest_path.read_bytes())
    templates = {}
    for name, filename in manifest['templates'].items():
        text = (directory / filename).read_text()
        templates[name] = text
        digest.update(text.encode())

    extracts = {}
    for spec in manifest.get('extracts', ()):
        source = spec['source']
        if source not in sources:
            raise PromptError(
                f'the pack draws on {source!r}, which is not a source in pins.json '
                f'({", ".join(sorted(sources))})')
        declared = sources[source]
        if declared.get('pin') and declared['pin'] != spec['pin']:
            raise PromptError(f'{source!r} is read at the {declared["pin"]} pin, '
                              f'not {spec["pin"]!r}')
        commit = pins.pin(spec['pin'])['commit']
        text = pins.show(spec['pin'], spec['path'], commit).decode()
        if spec.get('from'):
            sections, _order = heading_sections(text)
            if spec['from'] not in sections:
                raise PromptError(f'{spec["path"]} has no section {spec["from"]!r}')
            text = sections[spec['from']]
            if spec.get('to'):
                # `to` is the next section's heading: quote up to it, exclusive.
                text = text.split(spec['to'])[0]
        text = text.strip()
        extract = Extract(name=spec['as'], source=source, pin=spec['pin'], path=spec['path'],
                          commit=commit, text=text)
        extracts[extract.name] = extract
        digest.update(extract.text.encode())

    return Pack(version=version, job=manifest['job'], templates=templates,
                extracts=extracts, sha256=digest.hexdigest())


# --- what the model is shown about the game ---------------------------------

def primitive_help():
    """The primitives and their arguments, from the executor itself.

    Written from the code rather than by hand, so a prompt cannot promise a
    primitive that does not exist or forget one that does.
    """
    arguments = {
        'walk_to': '`target: {x, y}` — a square the player knows',
        'explore_floor': 'no arguments',
        'fight_nearest': 'no arguments',
        'rest_until_healed': 'no arguments',
        'take_stairs': '`direction: "down"` or `"up"`',
        'flee': '`by: "stairs"` or `"phase_door"`',
        'read_unknown_scroll': 'no arguments',
        'shop_list': '`list: [{label, count, side: "buy"|"sell"}]` — only in a shop',
    }
    missing = set(executor.PRIMITIVES) - set(arguments)
    if missing:
        raise PromptError(f'the pack does not describe {sorted(missing)}')
    lines = []
    for name in sorted(executor.PRIMITIVES):
        stops = ', '.join(sorted(_stops_of(name)))
        lines.append(f'- `{name}` — {arguments[name]}. Stops: {stops}.')
    return '\n'.join(lines)


def _stops_of(name):
    """The stops a primitive reports, read from its own code.

    Only what it actually returns as a stop — `return None, 'arrived'` — so a
    stop word that happens to appear as a command's name is not mistaken for
    one.
    """
    primitive = executor.PRIMITIVES[name]
    returned = set(re.findall(r"return None, '(\w+)'", _source_of(primitive.act)))
    found = {stop for stop in returned if stop in executor.STOPS}
    common = {'prompt', 'changed_level', 'decision_limit'}
    if getattr(primitive, 'stops_on_new_monster', True):
        common.add('new_monster')
    return (found or {'done'}) | common


def _source_of(function):
    import inspect

    try:
        return inspect.getsource(function)
    except OSError:                       # pragma: no cover - only without sources
        return ''


def summarise(observation, width=MAP_WIDTH, height=MAP_HEIGHT):
    """The observation as a prompt sees it: compact, and the same every time.

    The observation holds the whole of the player's known map, which runs to
    thousands of squares. A prompt gets a window around the player and is told
    that it is a window.
    """
    character = observation['character']
    player = observation['map']['player']
    origin = observation['map'].get('origin', {'x': 0, 'y': 0})
    rows = observation['map']['rows']

    top = max(0, player['y'] - origin['y'] - height // 2)
    left = max(0, player['x'] - origin['x'] - width // 2)
    window = []
    for row in rows[top:top + height]:
        line = row[left:left + width]
        window.append(line.replace('\t', ' '))
    # The player's own square, so the window is never ambiguous.
    y, x = player['y'] - origin['y'] - top, player['x'] - origin['x'] - left
    if 0 <= y < len(window) and 0 <= x < len(window[y]):
        window[y] = window[y][:x] + '@' + window[y][x + 1:]

    monsters = observation.get('monsters') or []
    monster_lines = '\n'.join(
        f"- `{m['letter']}` {m.get('name') or 'something'} at ({m['x']}, {m['y']}), "
        f"{max(abs(m['x'] - player['x']), abs(m['y'] - player['y']))} away"
        for m in monsters[:12]) or '- none in sight'
    inventory = '\n'.join(f"- `{item['label']}` {item['description']}"
                          for item in (observation.get('inventory') or [])[:20]) or '- nothing'
    messages = '\n'.join(f'- {message}' for message in (observation.get('messages') or [])[-8:])
    prompt = observation.get('prompt') or {'kind': 'none'}
    shop = observation.get('shop')
    shop_lines = ''
    if shop:
        stock = '\n'.join(f"- `{item['label']}` {item['description']}"
                          f"{(' — ' + str(item['price']) + ' gold') if item.get('price') is not None else ''}"
                          for item in shop['stock'][:20])
        shop_lines = f"\nYou are in the {shop['kind']}. Its stock:\n{stock}\n"

    return {
        'turn': observation['turn'],
        'decision': observation['decision'],
        'last_stop': (f" The last primitive stopped: **{observation['last_stop']}**."
                      if observation.get('last_stop') else ''),
        'character': (
            f"{character.get('race', '?')} {character.get('class', '?')}, level "
            f"{character['level']}, {character['hp']}/{character['max_hp']} hit points, "
            f"depth {character['depth']} "
            f"({'town' if not character['depth'] else str(character['depth'] * 50) + ' feet'}), "
            f"{character['gold']} gold"
            + (f", conditions: {', '.join(character['conditions'])}"
               if character.get('conditions') else '')),
        'map': '\n'.join(window) or '(nothing known)',
        'map_note': f'a {width}x{height} window on what you know; blank is unseen',
        'monsters': 'Monsters you can see:\n' + monster_lines,
        'inventory': 'Carrying:\n' + inventory + shop_lines,
        'messages': ('Since your last decision:\n' + messages) if messages else 'No new messages.',
        'prompt': (f"A prompt is waiting ({prompt['kind']}): {prompt.get('text', '').strip()}"
                   if prompt.get('kind') != 'none' else 'No prompt is waiting.'),
    }


def render(pack, observation, knowledge=None):
    """The chat messages for one decision."""
    commands = pack.extracts.get('movement_and_resting_commands')
    # string.Template, not str.format: the templates show JSON, and braces in
    # an example are not placeholders.
    system = Template(pack.templates['system']).substitute(
        primitives=primitive_help(),
        commands_citation=commands.citation if commands else '(nothing)',
        movement_and_resting_commands=commands.text if commands else '(nothing)')
    if knowledge:
        system += '\n\nWhat you have learned so far, with its evidence:\n' + knowledge
    return [
        {'role': 'system', 'content': system},
        {'role': 'user',
         'content': Template(pack.templates['decision']).substitute(**summarise(observation))},
    ]
