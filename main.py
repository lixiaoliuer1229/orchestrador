"""orchestrador root entry point.

This script is a tiny CLI dispatcher for the orchestrador monorepo.

It lets you, from the repository root, do things like:

    python main.py list                      # show all subprojects
    python main.py run langgraph-backend-studio test
    python main.py run langgraph-backend-studio docker-up

Each subproject is expected to ship a `Makefile` whose targets you can invoke
through the dispatcher. Add new subprojects by extending SUBPROJECTS below.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Subproject:
    """A self-contained subproject inside this monorepo."""

    name: str
    path: Path
    description: str

    @property
    def exists(self) -> bool:
        return self.path.is_dir()

    @property
    def has_makefile(self) -> bool:
        return (self.path / "Makefile").is_file()


SUBPROJECTS: tuple[Subproject, ...] = (
    Subproject(
        name="langgraph-backend-studio",
        path=REPO_ROOT / "langgraph-backend-studio",
        description=(
            "LangGraph backend engineer workshop — state machines, "
            "tools, human-in-the-loop, multi-agent, observability, deployment."
        ),
    ),
)


def cmd_list(_: argparse.Namespace) -> int:
    """Pretty-print every registered subproject."""
    if not SUBPROJECTS:
        print("No subprojects registered.")
        return 0

    name_w = max(len(s.name) for s in SUBPROJECTS)
    status_w = max(len("ok"), len("missing"), len("no-makefile"))
    print(f"{'name'.ljust(name_w)}  {'status'.ljust(status_w)}  description")
    print(f"{'-' * name_w}  {'-' * status_w}  {'-' * 40}")
    for s in SUBPROJECTS:
        if not s.exists:
            status = "missing"
        elif not s.has_makefile:
            status = "no-makefile"
        else:
            status = "ok"
        print(f"{s.name.ljust(name_w)}  {status.ljust(status_w)}  {s.description}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run a Make target inside a named subproject."""
    target = args.subproject
    sub = next((s for s in SUBPROJECTS if s.name == target), None)
    if sub is None:
        print(f"❌ Unknown subproject: {target}", file=sys.stderr)
        print("   Available:", ", ".join(s.name for s in SUBPROJECTS), file=sys.stderr)
        return 2
    if not sub.exists:
        print(f"❌ Subproject directory missing: {sub.path}", file=sys.stderr)
        return 2
    if not sub.has_makefile:
        print(f"❌ Subproject has no Makefile: {sub.path}", file=sys.stderr)
        return 2

    make = shutil.which("make")
    if make is None:
        print("❌ `make` not found in PATH. Install Xcode CLT or use `python main.py shell ...`.", file=sys.stderr)
        return 2

    cmd = [make, *args.target]
    print(f"▶ {' '.join(cmd)}   (cwd={sub.path.relative_to(REPO_ROOT)})")
    return subprocess.call(cmd, cwd=sub.path)


def cmd_shell(args: argparse.Namespace) -> int:
    """Open an interactive shell inside a subproject directory."""
    target = args.subproject
    sub = next((s for s in SUBPROJECTS if s.name == target), None)
    if sub is None:
        print(f"❌ Unknown subproject: {target}", file=sys.stderr)
        return 2
    if not sub.exists:
        print(f"❌ Subproject directory missing: {sub.path}", file=sys.stderr)
        return 2

    shell = shutil.which(args.shell) or shutil.which("bash") or shutil.which("sh")
    if shell is None:
        print("❌ No usable shell found.", file=sys.stderr)
        return 2

    print(f"▶ {shell}   (cwd={sub.path.relative_to(REPO_ROOT)})")
    return subprocess.call([shell], cwd=sub.path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrador",
        description="orchestrador monorepo root CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list all registered subprojects").set_defaults(func=cmd_list)

    p_run = sub.add_parser("run", help="run `make <target>` inside a subproject")
    p_run.add_argument("subproject", help="subproject name (see `list`)")
    p_run.add_argument(
        "target",
        nargs=argparse.REMAINDER,
        help="make target and args, e.g. `test`, `docker-up`",
    )
    p_run.set_defaults(func=cmd_run)

    p_shell = sub.add_parser("shell", help="open a shell inside a subproject directory")
    p_shell.add_argument("subproject", help="subproject name (see `list`)")
    p_shell.add_argument("--shell", default="bash", help="shell to launch (default: bash)")
    p_shell.set_defaults(func=cmd_shell)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())