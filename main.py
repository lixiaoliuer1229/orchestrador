"""orchestrador root entry point.

A small CLI for the orchestrador project:

    python main.py info                              # show project info
    python main.py test                              # run the test suite
    python main.py docker-up                         # start dev dependencies
    python main.py docker-down                       # stop dev dependencies
    python main.py run examples/hello_graph.py       # run any script in the repo
    python main.py shell                             # open a shell at repo root
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


def cmd_info(_: argparse.Namespace) -> int:
    """Print basic info about the project."""
    print(f"orchestrador — root: {REPO_ROOT}")
    print(f"  python : {sys.version.split()[0]}")
    if make := shutil.which("make"):
        print(f"  make   : {make}")
    if docker := shutil.which("docker"):
        print(f"  docker : {docker}")
    return 0


def cmd_test(_: argparse.Namespace) -> int:
    """Run pytest at the repo root."""
    return _run([sys.executable, "-m", "pytest", "tests/", "-v"])


def cmd_docker_up(_: argparse.Namespace) -> int:
    return _run(["docker", "compose", "up", "-d"])


def cmd_docker_down(_: argparse.Namespace) -> int:
    return _run(["docker", "compose", "down"])


def cmd_make(args: argparse.Namespace) -> int:
    """Run a Makefile target."""
    return _run(["make", *args.target])


def cmd_run(args: argparse.Namespace) -> int:
    """Run a Python script inside the repo."""
    script = Path(args.script)
    if not script.is_absolute():
        script = REPO_ROOT / script
    if not script.exists():
        print(f"❌ Script not found: {script}", file=sys.stderr)
        return 2
    return _run([sys.executable, str(script), *args.args])


def cmd_shell(args: argparse.Namespace) -> int:
    """Open an interactive shell at the repo root."""
    shell = shutil.which(args.shell) or shutil.which("bash") or shutil.which("sh")
    if shell is None:
        print("❌ No usable shell found.", file=sys.stderr)
        return 2
    print(f"▶ {shell}   (cwd={REPO_ROOT})")
    return subprocess.call([shell], cwd=REPO_ROOT)


def _run(cmd: list[str]) -> int:
    """Run a subprocess at the repo root, printing what we're doing."""
    pretty = " ".join(str(c) for c in cmd)
    print(f"▶ {pretty}   (cwd={REPO_ROOT})")
    return subprocess.call(cmd, cwd=REPO_ROOT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrador",
        description="orchestrador root CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="show project info").set_defaults(func=cmd_info)

    p_make = sub.add_parser("make", help="run `make <target>` at the repo root")
    p_make.add_argument("target", nargs=argparse.REMAINDER, help="make target(s)")
    p_make.set_defaults(func=cmd_make)

    sub.add_parser("test", help="run pytest tests/").set_defaults(func=cmd_test)
    sub.add_parser("docker-up", help="docker compose up -d").set_defaults(func=cmd_docker_up)
    sub.add_parser("docker-down", help="docker compose down").set_defaults(func=cmd_docker_down)

    p_run = sub.add_parser("run", help="run a Python script in the repo")
    p_run.add_argument("script", help="path to a .py file (relative to repo root)")
    p_run.add_argument("args", nargs=argparse.REMAINDER, help="args passed to the script")
    p_run.set_defaults(func=cmd_run)

    p_shell = sub.add_parser("shell", help="open a shell at the repo root")
    p_shell.add_argument("--shell", default="bash", help="shell to launch (default: bash)")
    p_shell.set_defaults(func=cmd_shell)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())