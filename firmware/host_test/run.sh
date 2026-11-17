#!/usr/bin/env bash
# Build and run the host tests for src/logic.c, replaying the in-car captures.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
caps="$here/../../captures/2026-11-12-car-can"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

for f in "$caps"/*.log.xz; do
    xz -dc "$f" > "$work/$(basename "${f%.xz}")"
done
cc -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined \
    -o "$work/test_logic" "$here/test_logic.c" "$here/../src/logic.c"
"$work/test_logic" "$work"
