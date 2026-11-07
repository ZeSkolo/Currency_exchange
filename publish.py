"""Publish reviewed source overlay to a new branch; defaults to plan only."""
import argparse, subprocess, tempfile, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent
REPOSITORY = 'Currency_exchange'
BRANCH = 'completed-web-app'

def run(args, cwd=None, capture=False):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=capture, check=True, timeout=180)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print('Plan only: publish ZeSkolo/' + REPOSITORY + ' branch ' + BRANCH + '. No network or writes. Pass --apply after review.')
        return
    if run(['gh', 'api', 'user', '--jq', '.login'], capture=True).stdout.strip() != 'ZeSkolo':
        raise SystemExit('Expected ZeSkolo account; stopping.')
    run(['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix='source-overlay-') as temporary:
        checkout = Path(temporary) / 'repo'
        url = 'https' + '://' + 'github.com/ZeSkolo/' + REPOSITORY + '.git'
        run(['git', 'clone', url, str(checkout)])
        if run(['git', 'ls-remote', '--heads', 'origin', BRANCH], cwd=checkout, capture=True).stdout.strip():
            raise SystemExit('Target branch already exists. Review it manually; no overwrite or force push.')
        for name in ['core.py', 'server.py', 'index.html', 'app.js', 'styles.css', 'catalog.json']:
            if (checkout / name).exists():
                raise SystemExit('Unreviewed existing file ' + name + '; reconcile manually before publication.')
        run(['git', 'switch', '-c', BRANCH], cwd=checkout)
        for item in ROOT.iterdir():
            if item.name in ['.git', '.data', '__pycache__'] or item.name.endswith(('.pyc', '.log', '.db', '.sqlite3')):
                continue
            if item.is_dir():
                shutil.copytree(item, checkout / item.name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.data', '.git', '*.log', '*.db', '*.sqlite3'))
            else:
                shutil.copy2(item, checkout / item.name)
        run(['git', 'add', '.'], cwd=checkout)
        run(['git', 'commit', '-m', 'Complete tested website and in-depth project documentation'], cwd=checkout)
        run(['git', 'push', 'origin', 'HEAD:' + BRANCH], cwd=checkout)
        print('Source published on ' + BRANCH + '. Existing main history and visibility were preserved. No live website deployment was performed.')
if __name__ == '__main__':
    main()

