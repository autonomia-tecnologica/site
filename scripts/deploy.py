"""Deploy the production build to the `gh-pages` branch of the site repository.

Usage (from the repository root, or through `npm run deploy`):

    python3 scripts/deploy.py
    python3 scripts/deploy.py --remote /tmp/site.git
    python3 scripts/deploy.py --branch gh-pages --domain autonomiatecnologica.com.br

The command builds the site with the production flag and SITE_URL taken from the domain, copies
`dist/` into a fresh temporary Git repository, writes `CNAME` with the domain, makes a single
parentless commit and force-pushes it to the branch. The branch holds only the built site and
shares no history with `main`, and every deploy replaces the previous commit instead of adding to
it. The photo comes from the private folder named by `SITE_PRIVATE_DIR` (read from `.env` by the
build) and reaches the branch only inside `dist/`; it is never added to the source tree. No CI is
involved, so no secret is stored there.

`--remote` accepts a remote name or any Git URL; the default is `origin`.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from project_python import venv_python

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "gh-pages"
DEFAULT_DOMAIN = "autonomiatecnologica.com.br"
COMMIT_MESSAGE = "Deploy the production build\n\nAI Generated"


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> bool:
    """Run a command and report whether it succeeded."""
    result = subprocess.run(command, cwd=cwd, env=env)
    return result.returncode == 0


def build(site_url: str) -> bool:
    """Run the production build with SITE_URL set for it."""
    print(f"building the site for {site_url}", flush=True)
    env = os.environ.copy()
    env["SITE_URL"] = site_url
    return run([str(venv_python()), "-m", "src.build", "--prod"], ROOT, env)


def remote_url(remote: str) -> str:
    """The URL of a remote name configured in the repository, or the argument itself."""
    result = subprocess.run(["git", "remote", "get-url", remote], cwd=ROOT,
                            capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return remote


def stage(dist: Path, domain: str) -> Path:
    """Copy the built site to a fresh folder and add the CNAME file of the domain."""
    staging = Path(tempfile.mkdtemp(prefix="site-deploy-"))
    shutil.copytree(dist, staging, dirs_exist_ok=True)
    (staging / "CNAME").write_text(f"{domain}\n", encoding="utf-8")
    return staging


def publish(staging: Path, remote: str, branch: str) -> bool:
    """Commit the staged site as an orphan commit and force-push it to the branch."""
    steps = [
        ["git", "init", "--quiet"],
        ["git", "add", "--all"],
        ["git", "commit", "--quiet", "--message", COMMIT_MESSAGE],
        ["git", "push", "--force", remote, f"HEAD:refs/heads/{branch}"],
    ]
    for command in steps:
        if not run(command, staging):
            print(f"error: `{' '.join(command)}` failed", file=sys.stderr)
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the site and publish it to the gh-pages branch.")
    parser.add_argument("--remote", default=DEFAULT_REMOTE, help=f"remote name or URL (default {DEFAULT_REMOTE})")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help=f"branch to publish (default {DEFAULT_BRANCH})")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help=f"domain written to CNAME (default {DEFAULT_DOMAIN})")
    args = parser.parse_args()

    site_url = f"https://{args.domain}"
    if not build(site_url):
        print("error: the production build failed; nothing was published", file=sys.stderr)
        return 1
    if not (DIST / "index.html").is_file():
        print(f"error: {DIST / 'index.html'} is missing; nothing was published", file=sys.stderr)
        return 1

    staging = stage(DIST, args.domain)
    destination = remote_url(args.remote)
    try:
        print(f"publishing {DIST} to {destination} {args.branch}", flush=True)
        if not publish(staging, destination, args.branch):
            print("error: the deploy failed; nothing was published", file=sys.stderr)
            return 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print(f"deployed: {site_url} from the {args.branch} branch of {destination}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
