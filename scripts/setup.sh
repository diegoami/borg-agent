#!/usr/bin/env bash
# Tools check and pinned clones into vendor/. Safe to rerun.
# In a Claude Code cloud session (CLAUDE_CODE_REMOTE=true) it also installs
# missing build packages. It never fails the session start: problems are
# printed, and the exit status is 0 unless --strict is given.
set -u
cd "$(dirname "$0")/.."
strict=0
[ "${1:-}" = "--strict" ] && strict=1
problems=0
say() { printf 'setup: %s\n' "$*"; }

missing=()
command -v cc >/dev/null 2>&1 || missing+=(build-essential)
command -v cmake >/dev/null 2>&1 || missing+=(cmake)
[ -e /usr/include/X11/Xlib.h ] || missing+=(libx11-dev)
command -v python3 >/dev/null 2>&1 || missing+=(python3)
if [ ${#missing[@]} -gt 0 ]; then
    if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
        sudo_cmd=""
        [ "$(id -u)" -ne 0 ] && sudo_cmd="sudo -n"
        say "installing ${missing[*]}"
        if ! { $sudo_cmd apt-get update -qq && $sudo_cmd apt-get install -y -qq "${missing[@]}"; } >/dev/null 2>&1; then
            say "could not install ${missing[*]}"; problems=1
        fi
    else
        say "missing packages: ${missing[*]} (install them, e.g. sudo apt-get install ${missing[*]})"
        problems=1
    fi
fi

if command -v python3 >/dev/null 2>&1; then
    mkdir -p vendor
    python3 - <<'EOF' || problems=1
import json, subprocess, sys
from pathlib import Path

pins = json.loads(Path('pins.json').read_text())['pins']
ok = True
for repo in sorted({p['repository'] for p in pins.values()}):
    dest = Path('vendor') / repo.split('/')[1]
    if not dest.exists():
        print(f'setup: cloning {repo}', flush=True)
        subprocess.run(['git', 'clone', '-q', '--filter=blob:none', '--no-checkout',
                        f'https://github.com/{repo}.git', str(dest)], check=False)
    for name, pin in pins.items():
        if pin['repository'] != repo:
            continue
        have = subprocess.run(['git', '-C', str(dest), 'cat-file', '-e', pin['commit'] + '^{commit}'],
                              capture_output=True).returncode == 0
        if not have:
            subprocess.run(['git', '-C', str(dest), 'fetch', '-q', 'origin', pin['commit']], check=False)
            have = subprocess.run(['git', '-C', str(dest), 'cat-file', '-e', pin['commit'] + '^{commit}'],
                                  capture_output=True).returncode == 0
        print(f"setup: {name} {pin['commit'][:12]} {'ok' if have else 'MISSING'}")
        ok &= have
sys.exit(0 if ok else 1)
EOF
fi

if [ $problems -ne 0 ]; then
    say "finished with problems (see above)"
    [ $strict -eq 1 ] && exit 1
else
    say "ready"
fi
exit 0
