#!/usr/bin/env bash
# Build the minimal Java runtime that tabula-java runs on (TECH_SPECS §16.2).
#
# Usage:  JAVA_HOME=/path/to/jdk-21 bash packaging/jre/build_jre.sh
# Output: src/mimufs/_runtime/jre/ (git-ignored), bundled by Briefcase like any source file.
# Run once per OS/architecture (CI matrix) BEFORE `briefcase create`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ROOT/src/mimufs/_runtime/jre"

if [[ -z "${JAVA_HOME:-}" ]]; then
    echo "JAVA_HOME must point to a JDK 21 (e.g. Eclipse Temurin 21)" >&2
    exit 1
fi
JLINK="$JAVA_HOME/bin/jlink"
JDEPS="$JAVA_HOME/bin/jdeps"

# The tabula-java jar shipped inside tabula-py.
JAR="$(cd "$ROOT" && uv run --no-sync python -c \
    "import pathlib, tabula; print(next(pathlib.Path(tabula.__file__).parent.glob('tabula-*.jar')))")"
echo "tabula jar: $JAR"

# Modules the jar needs, plus a fixed baseline (TECH_SPECS §16.2), de-duplicated.
DETECTED="$("$JDEPS" --print-module-deps --ignore-missing-deps --multi-release 21 "$JAR" | tr -d '\r')"
MODULES="$(printf '%s\n' "$DETECTED" java.base java.desktop java.xml java.logging \
    | tr ',' '\n' | sed '/^$/d' | sort -u | paste -sd, -)"
echo "modules: $MODULES"

rm -rf "$OUT"
mkdir -p "$(dirname "$OUT")"
"$JLINK" \
    --add-modules "$MODULES" \
    --strip-debug --no-header-files --no-man-pages --compress=zip-6 \
    --output "$OUT"

"$OUT/bin/java" -version
du -sh "$OUT"
