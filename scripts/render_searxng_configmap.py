#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


def yaml_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def main() -> int:
    namespace = sys.argv[1] if len(sys.argv) > 1 else os.getenv("NAMESPACE", "default")
    proxies = [
        os.getenv("SEARXNG_OUTBOUND_PROXY_PAR_URL", "").strip(),
        os.getenv("SEARXNG_OUTBOUND_PROXY_AMS_URL", "").strip(),
        os.getenv("SEARXNG_OUTBOUND_PROXY_WAW_URL", "").strip(),
    ]
    proxies = [proxy for proxy in proxies if proxy]

    lines = [
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        "  name: searxng-config",
        f'  namespace: "{yaml_quote(namespace)}"',
        "data:",
        "  settings.yml: |",
        "    use_default_settings:",
        "      engines:",
        "        keep_only:",
        "          - brave",
        "          - startpage",
        "          - qwant",
        "          - mojeek",
        "          - wikipedia",
        "          - bing",
        "          - google",
        "",
        "    general:",
        '      instance_name: "MirAI Search"',
        "      enable_metrics: false",
        "",
        "    search:",
        "      safe_search: 1",
        '      autocomplete: ""',
        "      formats:",
        "        - html",
        "        - json",
        "",
        "    server:",
        "      limiter: false",
        "      image_proxy: true",
        "      public_instance: false",
        "",
        "    ui:",
        '      default_locale: "fr"',
        "      query_in_title: false",
        "",
        "    valkey:",
        "      url: valkey://search-valkey:6379/0",
        "",
        "    outgoing:",
        "      request_timeout: 6.0",
        "      max_request_timeout: 12.0",
        "      retries: 2",
        "      pool_connections: 150",
        "      pool_maxsize: 30",
        "      enable_http2: true",
    ]

    if proxies:
        lines.extend(
            [
                "      proxies:",
                "        all://:",
            ]
        )
        for proxy in proxies:
            lines.append(f"          - {proxy}")

    lines.extend(
        [
            "",
            "    engines:",
            "      - name: brave",
            "        weight: 1.3",
            "      - name: startpage",
            "        weight: 1.2",
            "      - name: qwant",
            "        weight: 1.15",
            "      - name: mojeek",
            "        weight: 1.1",
            "      - name: bing",
            "        weight: 0.7",
            "      - name: google",
            "        weight: 0.6",
        ]
    )

    sys.stdout.write("\n".join(lines))
    if not lines[-1].endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
