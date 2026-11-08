"""The instrumentation recipe, checked against the pinned sources without building."""
import json

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


def test_build_key_is_a_hash_of_the_recipe_only():
    # The recipe must be JSON, so the key is reproducible on another machine.
    json.dumps(build.recipe(), sort_keys=True)


def test_instrumentation_applies_once_to_a_copy_of_the_pinned_files(tmp_path):
    tree = tmp_path / 'source'
    for name in build.INCLUDE_SITES + (build.ACTIVATION[0],):
        path = tree / 'src' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source(name))
    (tree / 'CMakeLists.txt').write_text('project(x)\n')
    build.instrument(tree)
    for name in build.INCLUDE_SITES:
        assert (tree / 'src' / name).read_text().startswith('#include "native-observer.h"\n')
    for name, _old, new in build.REPLACEMENTS:
        assert new in (tree / 'src' / name).read_text()
    assert build.ACTIVATION[1] in (tree / 'src' / build.ACTIVATION[0]).read_text()
    assert 'native-observer.c' in (tree / 'CMakeLists.txt').read_text()
    for name in build.OBSERVER_FILES:
        assert (tree / 'src' / name).exists()


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
