"""The pinned repositories: where their clones are, and how to read them.

`scripts/setup.sh` clones every repository named in `pins.json` into `vendor/`,
which git ignores. Nothing here writes to those clones, and no file of theirs is
copied into this repository: a build reads them at the pinned commit.
"""
import functools
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / 'vendor'


@functools.lru_cache(maxsize=1)
def pins():
    return json.loads((ROOT / 'pins.json').read_text())


def pin(name):
    return pins()['pins'][name]


def clone(name):
    """The local clone of the pin's repository, as setup.sh made it."""
    path = VENDOR / pin(name)['repository'].split('/')[1]
    if not (path / 'HEAD').exists() and not (path / '.git').exists():
        raise FileNotFoundError(f'{path} is missing; run scripts/setup.sh')
    return path


def git(name, *args):
    return subprocess.run(['git', '-C', str(clone(name)), *args],
                          check=True, capture_output=True).stdout


def show(name, path, commit=None):
    """One file's bytes at a pinned commit, without checking the tree out."""
    return git(name, 'show', f'{commit or pin(name)["commit"]}:{path}')


def archive(name, destination, commit=None):
    """Extract the pinned tree into `destination`, the way the zoo's runner does."""
    import tarfile
    destination.mkdir(parents=True, exist_ok=True)
    tar_path = destination.parent / (destination.name + '.tar')
    commit = commit or pin(name)['commit']
    with tar_path.open('wb') as out:
        subprocess.run(['git', '-C', str(clone(name)), 'archive', '--format=tar', commit],
                       check=True, stdout=out)
    with tarfile.open(tar_path) as tar:
        tar.extractall(destination, filter='data')
    return tar_path
