#!/bin/sh
# ═══════════════════════════════════════════════════════════════
#  rising-loop インストーラ / アップデータ
#
#  導入も更新も、ターミナルでこの1行だけ:
#    curl -fsSL https://raw.githubusercontent.com/toru0325/rising-loop/main/install.sh | sh
#
#  やること:
#    1. GitHub から最新の zip を落として ~/.claude/skills/rising-loop を置き換える
#    2. 置き換える前の版と新しい版を表示し、CHANGELOG の差分（新しい版の項）を見せる
#  やらないこと:
#    - 各プロジェクトの loops/ には触らない（旧形式の移行は次に /rising-loop を開いたとき、スキルが提案する）
# ═══════════════════════════════════════════════════════════════
set -eu

REPO="toru0325/rising-loop"
BRANCH="main"
DEST="${HOME}/.claude/skills/rising-loop"
ZIP_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"

need() { command -v "$1" >/dev/null 2>&1 || { printf '%s が見つかりません。入れてから再実行してください。\n' "$1" >&2; exit 1; }; }
need curl; need unzip

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

printf '⬇  最新版を取得しています…\n'
curl -fsSL "$ZIP_URL" -o "$TMP/skill.zip"
unzip -q "$TMP/skill.zip" -d "$TMP"
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d -name 'rising-loop-*' | head -1)"
[ -n "$SRC" ] || { printf 'zip の中身が想定と違います。\n' >&2; exit 1; }

NEW="$(cat "$SRC/VERSION" 2>/dev/null || printf '?')"
OLD="(未導入)"
if [ -d "$DEST" ] || [ -L "$DEST" ]; then
  OLD="$(cat "$DEST/VERSION" 2>/dev/null || printf '1.0.0 より前')"
fi

if [ "$OLD" = "$NEW" ]; then
  printf '✔ すでに最新版（%s）です。\n' "$NEW"
  exit 0
fi

# 置き換え。開発者のシンボリックリンクは壊さない（リンク先が git 管理なら pull を勧めて終わる）
if [ -L "$DEST" ]; then
  printf '⚠ %s はシンボリックリンクです（開発環境）。リンク先で git pull してください。\n' "$DEST"
  exit 0
fi
mkdir -p "$(dirname "$DEST")"
if [ -d "$DEST" ]; then
  BAK="${DEST}.bak-$(date +%Y%m%d%H%M%S)"
  mv "$DEST" "$BAK"
  printf '  以前の版は %s に残しました（不要なら削除してください）\n' "$BAK"
fi
rm -rf "$SRC/.git" "$SRC/_design"
mv "$SRC" "$DEST"

printf '✔ rising-loop を %s → %s に更新しました。\n\n' "$OLD" "$NEW"

# CHANGELOG の「新しい版」の項だけ表示（先頭の ## から次の ## まで）
if [ -f "$DEST/CHANGELOG.md" ]; then
  printf '── 変わったこと ─────────────────────────\n'
  awk '/^## /{n++} n==1{print} n>1{exit}' "$DEST/CHANGELOG.md"
  printf '──────────────────────────────────────\n'
fi

printf '\n次に Claude Code / codex で /rising-loop を使うと、必要なら loops/ の移行を提案します。\n'
