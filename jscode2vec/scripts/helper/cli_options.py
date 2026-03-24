from __future__ import annotations

from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CliOptions:
    """ベクトル化 CLI の実行設定を保持する不変データ構造。

    Args:
        mode (str): 実行モード。
        input_path (Path): 入力ファイルまたはディレクトリ。
        output (Path | None): 出力ディレクトリ。
        jobs (int): 並列度。

    Raises:
        None

    Returns:
        CliOptions: 解析済み CLI オプション。
    """
    mode: str
    input_path: Path
    output: Path | None
    jobs: int


def _build_vectorization_argument_parser() -> ArgumentParser:
    """ベクトル化コマンド用の引数パーサーを構築する。

    Args:
        None

    Raises:
        None

    Returns:
        ArgumentParser: ベクトル化 CLI 用 ArgumentParser。
    """
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


def _resolve_execution_mode_and_input_path(args: Namespace) -> tuple[str, Path]:
    """解析済み引数から実行モードと入力パスを決定する。

    Args:
        args (Namespace): argparse の解析結果。

    Raises:
        None

    Returns:
        tuple[str, Path]: 実行モードと入力パス。
    """
    if args.single:
        return "single", Path(args.single).expanduser().resolve()
    if args.project:
        return "project", Path(args.project).expanduser().resolve()
    return "all", Path(args.all_projects).expanduser().resolve()


def parse_vectorization_cli_options(argv: list[str] | None = None) -> CliOptions:
    """CLI 引数を検証しベクトル化実行オプションへ変換する。

    Args:
        argv (list[str] | None): 解析対象のコマンドライン引数。

    Raises:
        SystemExit: argparse のバリデーションエラー時。

    Returns:
        CliOptions: 解析済みオプション。
    """
    parser = _build_vectorization_argument_parser()
    args = parser.parse_args(argv)

    mode, input_path = _resolve_execution_mode_and_input_path(args)

    if args.jobs < 1:
        parser.error("-j/--jobs は1以上を指定してください")

    output_path = Path(args.output).expanduser().resolve() if args.output else None

    return CliOptions(
        mode=mode,
        input_path=input_path,
        output=output_path,
        jobs=args.jobs,
    )
