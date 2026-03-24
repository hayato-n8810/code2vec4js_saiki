from __future__ import annotations

from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CliOptions:
    mode: str
    input_path: Path
    output: Path | None
    jobs: int


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        description="JSファイルをcode2vecでベクトル化する",
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("-s", "--single", dest="single", help="単一JSファイルのパス")
    mode_group.add_argument("-p", "--project", dest="project", help="JSファイルを含む単一フォルダのパス")
    mode_group.add_argument("--all", dest="all_projects", help="複数プロジェクトを含む親フォルダのパス")

    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help="出力先ベースパス。未指定時は入力パスのtargetをoutputs/vecに置換したパス",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        dest="jobs",
        type=int,
        default=1,
        help="並列処理数（-p, --all で有効）",
    )

    return parser


def _resolve_mode(args: Namespace) -> tuple[str, Path]:
    if args.single:
        return "single", Path(args.single).expanduser().resolve()
    if args.project:
        return "project", Path(args.project).expanduser().resolve()
    return "all", Path(args.all_projects).expanduser().resolve()


def parse_cli(argv: list[str] | None = None) -> CliOptions:
    parser = _build_parser()
    args = parser.parse_args(argv)

    mode, input_path = _resolve_mode(args)

    if args.jobs < 1:
        parser.error("-j/--jobs は1以上を指定してください")

    output_path = Path(args.output).expanduser().resolve() if args.output else None

    return CliOptions(
        mode=mode,
        input_path=input_path,
        output=output_path,
        jobs=args.jobs,
    )
