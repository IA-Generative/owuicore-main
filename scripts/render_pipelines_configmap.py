#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINES_DIR = ROOT / "pipelines"


def yaml_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main() -> int:
    namespace = sys.argv[1] if len(sys.argv) > 1 else "default"
    pipeline_files = sorted(PIPELINES_DIR.glob("*.py"))
    if not pipeline_files:
        raise SystemExit(f"No pipeline files found under {PIPELINES_DIR}")

    lines = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        "  name: pipelines-config",
        f"  namespace: {yaml_quote(namespace)}",
        "data:",
    ]

    for pipeline_file in pipeline_files:
        lines.append(f"  {pipeline_file.name}: |")
        for raw_line in pipeline_file.read_text(encoding="utf-8").splitlines():
            lines.append(f"    {raw_line}")
        if pipeline_file.read_text(encoding='utf-8').endswith('\n'):
            lines.append("    ")

    sys.stdout.write("\n".join(lines))
    if not lines[-1].endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
