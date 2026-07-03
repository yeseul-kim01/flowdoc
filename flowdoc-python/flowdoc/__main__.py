"""FlowDoc Python CLI entry point.

Subcommands:
    affects <symbol> <flowdoc.json>   reverse impact analysis
    diff <old.json> <new.json>        compare two flowdoc documents

With no subcommand it runs the scanner (backwards-compatible):
    python -m flowdoc <source_root> <output.json>
"""

import sys


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "affects":
        from flowdoc.commands.affects import main as affects_main
        sys.exit(affects_main(argv[1:]))
    if argv and argv[0] == "diff":
        from flowdoc.commands.diff import main as diff_main
        sys.exit(diff_main(argv[1:]))
    # Default: the static scanner (python -m flowdoc <root> <out>).
    from flowdoc.scanner.cli import main as scan_main
    scan_main()


main()
