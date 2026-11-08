"""The instrumentation recipe, checked against the pinned sources without building."""
import ast
import json
import re

import pytest

from borg_agent import build, pins


def source(name):
    return build.pins.show(build.GAME_PIN, 'src/' + name).decode()


def test_observer_comes_from_the_runner_pin():
    sources = build.observer_sources()
    assert set(sources) == set(build.OBSERVER_FILES)
    assert b'void measure_init(void);' in sources['native-observer.h']
    assert b'measure_activate_borg' in sources['native-observer.c']


@pytest.mark.parametrize('name,old,new', build.REPLACEMENTS)
def test_every_replacement_site_is_unique_in_the_pinned_source(name, old, new):
    assert source(name).count(old) == 1
    assert old in new or 'measure_' in new


@pytest.mark.parametrize('name', build.INCLUDE_SITES)
def test_include_sites_exist_and_call_the_observer(name):
    text = source(name)
    assert text
    assert 'native-observer.h' not in text


def test_activation_is_missing_at_the_pin_so_it_has_to_be_added():
    name, marker, addition = build.ACTIVATION
    assert marker not in source(name)
    assert 'borg_cmd_start' in addition


def test_build_key_covers_the_whole_recipe():
    recipe = build.recipe()
    assert recipe['game_commit'] == pins.pin('better-borg-c')['commit']
    assert recipe['runner_commit'] == pins.pin('runner')['commit']
    key = build.build_key(recipe)
    assert build.build_key(recipe) == key and len(key) == 16
    for change in ({'cmake_args': []}, {'game_commit': '0' * 40},
                   {'observer_sha256': {}}, {'replacements': []}):
        assert build.build_key({**recipe, **change}) != key


def test_the_build_key_is_a_hash_of_the_recipe_and_nothing_else():
    # It must be reproducible: JSON, order-independent, and stable.
    recipe = build.recipe()
    text = json.dumps(recipe, sort_keys=True)
    assert json.loads(text) == recipe
    shuffled = dict(reversed(list(recipe.items())))
    assert build.build_key(shuffled) == build.build_key(recipe)
    assert build.build_key(recipe) == build.build_key(json.loads(text))


def pinned_tree(tmp_path):
    tree = tmp_path / 'source'
    for name in set(build.INCLUDE_SITES) | {build.ACTIVATION[0]} | set(build.BRIDGE_INCLUDE_SITES):
        path = tree / 'src' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source(name))
    (tree / 'CMakeLists.txt').write_text('project(x)\n')
    return tree


def test_instrumentation_applies_once_to_a_copy_of_the_pinned_files(tmp_path):
    tree = pinned_tree(tmp_path)
    build.instrument(tree)
    for name in build.INCLUDE_SITES:
        assert '#include "native-observer.h"\n' in (tree / 'src' / name).read_text()
    superseded = {old for _name, old, _new in build.BRIDGE_REPLACEMENTS}
    for name, _old, new in build.REPLACEMENTS:
        text = (tree / 'src' / name).read_text()
        if new in superseded:
            # The bridge layer rewrote this very line; its own test checks it.
            continue
        assert new in text
    assert build.ACTIVATION[1] in (tree / 'src' / build.ACTIVATION[0]).read_text()
    for name in build.OBSERVER_FILES:
        assert (tree / 'src' / name).exists()
    cmake = (tree / 'CMakeLists.txt').read_text()
    assert 'native-observer.c' in cmake and 'agent-bridge.c' in cmake


def test_the_bridge_goes_on_top_of_the_observer(tmp_path):
    # The bridge's site is the line the observer writes, so the order of the
    # two layers is part of the recipe, not an accident.
    tree = pinned_tree(tmp_path)
    build.instrument(tree)
    for name in build.BRIDGE_INCLUDE_SITES:
        assert (tree / 'src' / name).read_text().startswith('#include "agent-bridge.h"\n')
    for name, _old, new in build.BRIDGE_REPLACEMENTS:
        text = (tree / 'src' / name).read_text()
        assert new in text
        # The Borg's own thinking is still there, behind the agent-mode branch.
        assert 'borg_think()' in new and 'agent_active()' in new
    for name in build.BRIDGE_FILES:
        assert (tree / 'src' / name).exists()


def test_the_bridge_replacement_needs_the_observer_first(tmp_path):
    tree = pinned_tree(tmp_path)
    name, old, new = build.BRIDGE_REPLACEMENTS[0]
    # Without the observer layer the site does not exist, and that must fail
    # loudly rather than quietly leave the bridge unreachable.
    with pytest.raises(ValueError):
        build.replace_once(tree / 'src' / name, old, new)


def test_the_bridge_sources_are_this_repositorys_own(tmp_path):
    sources = build.bridge_sources()
    assert set(sources) == set(build.BRIDGE_FILES)
    assert b'agent_active' in sources['agent-bridge.h']
    body = sources['agent-bridge.c'].decode()
    # It reads state and writes keys, and holds no tactics of its own
    # (docs/SOURCES.md): the only Borg functions it may call are the key queue,
    # the note log and the screen reader.
    allowed = {'borg_keypress', 'borg_keypresses', 'borg_note', 'borg_what_text'}
    code = re.sub(r'/\*.*?\*/', '', body, flags=re.S)  # comments may name anything
    called = set(re.findall(r'\b(borg_\w+)\s*\(', code))
    assert called <= allowed, called - allowed


def test_a_moved_site_is_an_error_not_a_silent_skip(tmp_path):
    path = tmp_path / 'file.c'
    path.write_text('a\n')
    with pytest.raises(ValueError):
        build.replace_once(path, 'missing', 'x')
    path.write_text('a\na\n')
    with pytest.raises(ValueError):
        build.replace_once(path, 'a\n', 'b\n')


def test_cached_build_is_reused_only_when_it_matches_the_recipe(tmp_path):
    recipe = build.recipe()
    out = tmp_path / 'build'
    (out / 'build/game').mkdir(parents=True)
    binary = build.binary(out)
    binary.write_bytes(b'not really a game')
    manifest = {'complete': True, 'recipe': recipe, 'binary_sha256': build.sha(binary)}
    (out / 'build.json').write_text(json.dumps(manifest))
    assert build.is_current(out, recipe)
    # A different recipe, an unfinished build or a changed binary all miss.
    assert not build.is_current(out, {**recipe, 'cmake_args': []})
    (out / 'build.json').write_text(json.dumps({**manifest, 'complete': False}))
    assert not build.is_current(out, recipe)
    (out / 'build.json').write_text(json.dumps(manifest))
    binary.write_bytes(b'rebuilt')
    assert not build.is_current(out, recipe)
    (out / 'build.json').write_text('{ truncated')
    assert not build.is_current(out, recipe)


def test_build_directory_is_under_the_ignored_build_root():
    assert build.build_dir().parent == build.BUILD_ROOT
    assert build.BUILD_ROOT.name == 'build'


def runner_source():
    return build.pins.show(build.RUNNER_PIN, 'tools/measure-native.py').decode()


def runner_replacements():
    """The replace(...) calls of the runner's observer branch, at its pin."""
    source = runner_source()
    observe = source[source.index("if args.observe:"):source.index("def refresh_observer")]
    found = []
    for match in re.finditer(
            r"replace\(source / 'src/([^']+)',\s*('(?:[^'\\]|\\.)*'),\s*('(?:[^'\\]|\\.)*')\)",
            observe, re.S):
        name, old, new = match.groups()
        found.append((name, ast.literal_eval(old), ast.literal_eval(new)))
    return found


def test_the_recipe_is_the_runners_at_the_pin():
    """Finding 6 of the milestone-1 review: parity, not a hand copy."""
    theirs = runner_replacements()
    assert len(theirs) == 6, theirs
    assert list(build.REPLACEMENTS) == theirs


def test_the_include_sites_are_the_runners():
    source = runner_source()
    observe = source[source.index("if args.observe:"):source.index("def refresh_observer")]
    listed = re.search(r"for file in \(([^)]*)\):", observe).group(1)
    assert [ast.literal_eval(part.strip()) for part in listed.split(',') if part.strip()] \
        == list(build.INCLUDE_SITES)


def test_the_cmake_arguments_are_the_runners():
    source = runner_source()
    configure = source[source.index("('configure', ['cmake'"):source.index("('build', ['cmake'")]
    theirs = re.findall(r"'(-D[^']+)'", configure)
    assert theirs == list(build.CMAKE_ARGS)


def test_the_activation_block_is_the_runners():
    source = runner_source()
    bridge = source[source.index('def named_play_bridge'):source.index('def recording_profile')]
    marker = re.search(r"if '([^']+)' not in path.read_text\(\)", bridge).group(1)
    assert marker == build.ACTIVATION[1]
    assert 'borg_cmd_start' in bridge


def test_the_build_key_covers_the_lines_the_recipe_writes_and_the_toolchain():
    # Finding 10: a changed include line, CMake line, version suffix, compiler
    # or platform must not be served from the cache.
    recipe = build.recipe()
    key = build.build_key(recipe)
    for change in ({'include_line': '/* nothing */\n'},
                   {'cmake_lines': []},
                   {'version_suffix': '-other'},
                   {'compiler': 'cc (some other compiler)'},
                   {'platform': 'Linux aarch64'},
                   {'bridge_sha256': {}}):
        assert build.build_key({**recipe, **change}) != key, change
    assert set(build.toolchain()) == {'compiler', 'platform'}
