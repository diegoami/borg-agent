"""Build the pinned C game headless, instrumented the way the zoo's runner is.

The recipe below is the runner's (`tools/measure-native.py --observe` at the
`runner` pin, see pins.json) written as data, so a test can check every site
against the pinned sources without building, and so the build key can be a hash
of the recipe. Keeping the sites identical to the zoo's keeps this build
comparable with the zoo's specimens.

Nothing of the game is committed here: the tree comes from `git archive` at the
pinned commit, the observer from the runner pin's `tools/`, and everything lands
under `build/`, which git ignores.
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

from . import pins

GAME_PIN = 'better-borg-c'
RUNNER_PIN = 'runner'
BUILD_ROOT = pins.ROOT / 'build'

OBSERVER_FILES = ('native-observer.c', 'native-observer.h')
# The observer's declarations go at the top of each file that calls it.
INCLUDE_SITES = ('main-test.c', 'game-world.c', 'ui-game.c', 'borg/borg.c', 'borg/borg-io.c')
# (file, found exactly once, replacement) — the runner's strings, unchanged.
REPLACEMENTS = (
    ('main-test.c', 'term_data_link(0);', 'measure_init();\n\tterm_data_link(0);'),
    ('game-world.c', '\t\t\tturn++;', '\t\t\tturn++;\n\t\t\tmeasure_tick();'),
    ('ui-game.c', '\t\t\tpre_turn_refresh();', 'measure_boundary();\n\t\t\tpre_turn_refresh();'),
    ('ui-game.c', '\t\tclose_game(true);', '\t\tmeasure_end();\n\t\tclose_game(true);'),
    ('borg/borg.c', 'while (!borg_think())', 'while (!(measure_decision(), borg_think()))'),
    ('borg/borg-io.c', '    /* Log the message */', '    measure_note(what);\n\n    /* Log the message */'),
)
# The observer calls this; the runner adds it for builds that have no UI keys.
ACTIVATION = ('borg/borg-commands.c', 'void measure_activate_borg(void)',
              '\n#ifdef ALLOW_BORG\nvoid measure_activate_borg(void) { borg_cmd_start(); }\n#endif\n')
CMAKE_ARGS = ('-DSUPPORT_BORG=ON', '-DSUPPORT_TEST_FRONTEND=ON',
              '-DSUPPORT_X11_FRONTEND=ON', '-DCMAKE_BUILD_TYPE=Debug')
RECIPE_VERSION = 'borg-agent/observer-build@2'

# The bridge of T03: this repository's own C, in bridge/. It is applied on top
# of the observer, so its site is the observer's own line. With the agent mode
# off (no BORG_AGENT_OBS and BORG_AGENT_ACT) the branch falls through to
# borg_think and play is byte-identical to the stock Borg's (RULES 8).
BRIDGE_DIR = pins.ROOT / 'bridge'
BRIDGE_FILES = ('agent-bridge.c', 'agent-bridge.h')
BRIDGE_INCLUDE_SITES = ('borg/borg.c',)
BRIDGE_REPLACEMENTS = (
    ('borg/borg.c',
     'while (!(measure_decision(), borg_think()))',
     'while (!(measure_decision(), agent_active() ? (agent_think(), true) : borg_think()))'),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def observer_sources():
    """The observer files' bytes at the runner pin."""
    return {name: pins.show(RUNNER_PIN, 'tools/' + name) for name in OBSERVER_FILES}


def bridge_sources():
    """The bridge files' bytes, from this repository."""
    return {name: (BRIDGE_DIR / name).read_bytes() for name in BRIDGE_FILES}


def recipe():
    """Everything that decides what the binary is, for the build key."""
    return {
        'version': RECIPE_VERSION,
        'game_commit': pins.pin(GAME_PIN)['commit'],
        'runner_commit': pins.pin(RUNNER_PIN)['commit'],
        'includes': list(INCLUDE_SITES),
        'replacements': [list(r) for r in REPLACEMENTS],
        'activation': list(ACTIVATION),
        'cmake_args': list(CMAKE_ARGS),
        'observer_sha256': {name: hashlib.sha256(data).hexdigest()
                            for name, data in observer_sources().items()},
        'bridge_includes': list(BRIDGE_INCLUDE_SITES),
        'bridge_replacements': [list(r) for r in BRIDGE_REPLACEMENTS],
        'bridge_sha256': {name: hashlib.sha256(data).hexdigest()
                          for name, data in bridge_sources().items()},
    }


def build_key(recipe_data=None):
    text = json.dumps(recipe_data or recipe(), sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def build_dir(recipe_data=None):
    return BUILD_ROOT / build_key(recipe_data)


def binary(out):
    return Path(out) / 'build/game/angband'


def replace_once(path, old, new):
    text = path.read_text()
    found = text.count(old)
    if found != 1:
        raise ValueError(f'expected one instrumentation site in {path.name}, found {found}: {old!r}')
    path.write_text(text.replace(old, new))


def instrument(source):
    """Apply the recipe to an extracted tree."""
    for name, data in observer_sources().items():
        (source / 'src' / name).write_bytes(data)
    for name in INCLUDE_SITES:
        path = source / 'src' / name
        path.write_text('#include "native-observer.h"\n' + path.read_text())
    for name, old, new in REPLACEMENTS:
        replace_once(source / 'src' / name, old, new)
    name, marker, addition = ACTIVATION
    path = source / 'src' / name
    if marker not in path.read_text():
        with path.open('a') as handle:
            handle.write(addition)
    # The bridge goes on top of the observer, and its site is the line the
    # observer just wrote, so the order of these two layers is fixed.
    for name, data in bridge_sources().items():
        (source / 'src' / name).write_bytes(data)
    for name in BRIDGE_INCLUDE_SITES:
        path = source / 'src' / name
        path.write_text('#include "agent-bridge.h"\n' + path.read_text())
    for name, old, new in BRIDGE_REPLACEMENTS:
        replace_once(source / 'src' / name, old, new)
    with (source / 'CMakeLists.txt').open('a') as handle:
        handle.write('\ntarget_sources(OurExecutable PRIVATE src/native-observer.c)\n')
        handle.write('\ntarget_sources(OurExecutable PRIVATE src/agent-bridge.c)\n')
        handle.write(f'\nadd_compile_definitions(PRIVATE_USER_PATH="{source.parent / "private-user"}")\n')


def is_current(out, recipe_data):
    """True when `out` holds a finished build of exactly this recipe."""
    manifest_path = Path(out) / 'build.json'
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return False
    return bool(manifest.get('complete')
                and manifest.get('recipe') == recipe_data
                and binary(out).exists()
                and sha(binary(out)) == manifest.get('binary_sha256'))


def prepare(out=None, force=False, log=print):
    """Build the instrumented game, reusing a finished build of the same recipe."""
    recipe_data = recipe()
    out = Path(out) if out else build_dir(recipe_data)
    if not force and is_current(out, recipe_data):
        log(f'build: cached {out}')
        return out
    source = out / 'source'
    if out.exists():
        import shutil
        # Only ever replace a directory that is one of our builds: `--output`
        # could name anything, and a stale build is no reason to delete it.
        if not any((out / name).exists() for name in ('build.json', 'source', 'build')):
            raise ValueError(f'{out} exists and is not a build directory; '
                             'choose another --output or empty it yourself')
        shutil.rmtree(out)
    out.mkdir(parents=True)
    archive = pins.archive(GAME_PIN, source)
    manifest = {
        'schema': 'borg-agent/build@1',
        'recipe': recipe_data,
        'build_key': build_key(recipe_data),
        'source_archive_sha256': sha(archive),
        'compiler': subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
        'platform': subprocess.check_output(['uname', '-sm'], text=True).strip(),
        'complete': False,
    }
    instrument(source)
    (source / 'version').write_text(recipe_data['game_commit'] + '-observer')
    (out / 'build.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    env = os.environ.copy()
    env.update(LC_ALL='C.UTF-8', LANG='C.UTF-8', GIT_CEILING_DIRECTORIES=str(source))
    for key in ('FORCE_PATH', 'VERBOSE'):
        env.pop(key, None)
    commands = [
        ('configure', ['cmake', '-S', str(source), '-B', str(out / 'build'), *CMAKE_ARGS]),
        ('build', ['cmake', '--build', str(out / 'build'), '--target', 'OurExecutable',
                   '--parallel', str(os.cpu_count() or 2)]),
    ]
    for label, command in commands:
        log(f'build: {label} {out}')
        with (out / (label + '.log')).open('w') as handle:
            subprocess.run(command, env=env, stdout=handle, stderr=subprocess.STDOUT, check=True)
    manifest.update(
        commands=[c for _, c in commands],
        binary_sha256=sha(binary(out)),
        data_sha256={str(p.relative_to(source)): sha(p)
                     for directory in ('gamedata', 'customize', 'screens', 'help')
                     for p in sorted((source / 'lib' / directory).rglob('*')) if p.is_file()},
        complete=True,
    )
    (out / 'build.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    log(f'build: ready {binary(out)}')
    return out
