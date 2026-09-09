#!/usr/bin/env python3
"""Run a small, verified maintenance task for FlowSight.

This script is intentionally conservative: it never generates placeholder
modules or rewrites existing work. It only reports whether the repository is
ready for a real, manually reviewed change.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_PATH = Path(__file__).parent


def run_command(cmd: list[str], cwd: Path = None) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr)."""
    result = subprocess.run(cmd, cwd=cwd or REPO_PATH, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def get_git_status() -> str:
    """Get git status."""
    _, stdout, _ = run_command(["git", "status", "--porcelain"])
    return stdout.strip()


def has_changes() -> bool:
    """Check if there are uncommitted changes."""
    return bool(get_git_status())


def main():
    """Main entry point."""
    print(f"FlowSight Daily Commit - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check if we're in a git repo - use the script's directory
    repo_path = Path(__file__).parent.parent
    if not (repo_path / ".git").exists():
        print(f"Error: Not a git repository at {repo_path}")
        sys.exit(1)

    # Change to repo directory
    os.chdir(repo_path)

    # Never commit changes without an explicit, reviewed change set.
    if has_changes():
        print("Uncommitted changes detected; review and commit them manually:")
        print(get_git_status())
        return

    print("No pending changes. No automatic placeholder commit created.")
    print("Make a real change, test it, then commit and push it explicitly.")


if __name__ == "__main__":
    main()
