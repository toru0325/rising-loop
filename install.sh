#!/bin/sh
# ═══════════════════════════════════════════════════════════════
#  rising-loop インストーラ / アップデータ
#
#  導入も更新も、ターミナルでこの1行だけ:
#    curl -fsSL https://raw.githubusercontent.com/toru0325/rising-loop/main/install.sh | sh
#
#  やること:
#    1. GitHub から最新の tar.gz を落として ~/.claude/skills/rising-loop を置き換える
#    2. 置き換える前の版と新しい版を表示し、CHANGELOG の差分（新しい版の項）を見せる
#  やらないこと:
#    - バックアップは取らない（古い版は GitHub にある）
#    - 各プロジェクトの loops/ には触らない（旧形式の移行は次に /rising-loop を開いたとき、スキルが提案する）
# ═══════════════════════════════════════════════════════════════
set -eu

REPO="toru0325/rising-loop"
BRANCH="main"
DEST="${HOME}/.claude/skills/rising-loop"
TGZ_URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.tar.gz"

# macOS 用。Windows は WSL の中で（PowerShell では動かない）
case "$(uname -s 2>/dev/null)" in
  Darwin|Linux) ;;
  *) printf 'このスクリプトは macOS 用です。Windows の人は WSL の中で実行してください。\n' >&2; exit 1 ;;
esac

need() { command -v "$1" >/dev/null 2>&1 || { printf '%s が見つかりません。入れてから再実行してください。\n' "$1" >&2; exit 1; }; }
need curl; need tar

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

printf '⬇  最新版を取得しています…\n'
# ★zip ではなく tar.gz。macOS の unzip は日本語ファイル名で壊れる
curl -fsSL "$TGZ_URL" -o "$TMP/skill.tgz"
tar -xzf "$TMP/skill.tgz" -C "$TMP"
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d -name 'rising-loop-*' | head -1)"
[ -n "$SRC" ] || { printf 'アーカイブの中身が想定と違います。\n' >&2; exit 1; }

NEW="$(cat "$SRC/VERSION" 2>/dev/null || printf '?')"
OLD="(未導入)"
if [ -d "$DEST" ] || [ -L "$DEST" ]; then
  OLD="$(cat "$DEST/VERSION" 2>/dev/null || printf '1.0.0 より前')"
fi

# 別の場所に古い rising-loop（zip の頃の名前 loop-manager を含む）が残っていないか。案内だけで削除はしない
warn_dupes() {
  found=""
  for base in "$HOME/.claude/skills" "$PWD/.claude/skills"; do
    [ -d "$base" ] || continue
    for d in "$base"/*/; do
      d="${d%/}"
      [ "$d" = "$DEST" ] && continue
      [ -f "$d/SKILL.md" ] || continue
      if grep -qE '^name: *(rising-loop|loop-manager)' "$d/SKILL.md" 2>/dev/null; then found="$found\n   $d"; fi
    done
  done
  if [ -n "$found" ]; then
    printf '\n⚠ 別の場所に古い rising-loop があります。/rising-loop が古い方で動くことがあるので、削除してください:%b\n' "$found"
    printf '   （他の場所に置いた覚えがあれば: find ~ -name SKILL.md -path "*rising-loop*" 2>/dev/null）\n'
  fi
}

hint_update() {
  printf '\n── 次にやること ─────────────────────────\n'
  printf '各画面の右ペインのチャットに、この1行を貼って送る:\n\n'
  printf '    rising-loop が %s になったので、このループを合わせて\n\n' "$NEW"
  printf '──────────────────────────────────────\n'
}

if [ "$OLD" = "$NEW" ]; then
  printf '✔ すでに最新版（%s）です。\n' "$NEW"
  hint_update
  warn_dupes
  exit 0
fi

# 置き換え。開発者のシンボリックリンクは壊さない（リンク先が git 管理なら pull を勧めて終わる）
if [ -L "$DEST" ]; then
  printf '⚠ %s はシンボリックリンクです（開発環境）。リンク先で git pull してください。\n' "$DEST"
  exit 0
fi
mkdir -p "$(dirname "$DEST")"
# ★バックアップは取らない。同じ階層に残すと SKILL.md が拾われて別スキルとして登録される。古い版は GitHub にある
rm -rf "$DEST"
# 以前の版が残した rising-loop.bak-* も片づける（1.1.0 以前の install.sh が作っていた）
for b in "${DEST}".bak-*; do [ -d "$b" ] && rm -rf "$b" && printf '  古いバックアップ %s を削除しました\n' "$b"; done
rm -rf "$SRC/.git" "$SRC/_design"
mv "$SRC" "$DEST"

printf '✔ rising-loop を %s → %s に更新しました。\n\n' "$OLD" "$NEW"

# CHANGELOG の「新しい版」の項だけ表示（先頭の ## から次の ## まで）。初回導入では出さない（前の版が無いので意味が無い）
if [ "$OLD" != "(未導入)" ] && [ -f "$DEST/CHANGELOG.md" ]; then
  printf '── 変わったこと ─────────────────────────\n'
  awk '/^## /{n++} n==1{print} n>1{exit}' "$DEST/CHANGELOG.md"
  printf '──────────────────────────────────────\n'
fi

if [ "$OLD" = "(未導入)" ]; then
  cat <<'HELP'

── ライジング・ループとは ───────────────────────
ひとつの指標を計測し、その数字を上げるための施策を AI と一緒に回し続ける仕組みです。
回すのは4段階: ゴール（動かしたい数字）→ ボトルネック（届かない理由）
              → 施策の実行 → 施策の評価（効いたか A〜E）→ ゴールへ戻る

── はじめかた ────────────────────────────────
1. このサービス専用のフォルダを1つ作る（例: ~/rising/自社サービス）
   企画書や仕様など、サービスの説明になるものがあれば入れておく
2. そのフォルダで Claude Code（Codex）を起動し、/rising-loop と打つ
3. 目標の例を参考に、自分のゴールを答える
   → AI がループの画面（loops/index.html）を作る。以後はこの画面が入口

── 効果を上げるコツ ───────────────────────────
数字が自動で取れる口を、できるだけ多く AI につなぐこと。
GA4・Search Console・Stripe・Shopify・広告管理画面・自社 DB・Google Sheets などの
API や MCP をつなぐほど、AI が自分で数字を取りに行けるようになり、
更新が速く、評価が正確になります。
つなぐ口が無い場合は、都度 CSV を渡したり、
Claude Code にブラウザを操作させて数字を取るのもおすすめです。
──────────────────────────────────────
HELP
else
  hint_update
fi
warn_dupes
