#!/bin/sh
# ═══════════════════════════════════════════════════════════════
#  chat-pane.sh — loops/index.html の右ペイン専用ランチャー
#
#  このファイルは rising-loop スキルの assets/chat-pane.sh の写しです。
#  プロジェクトごとに loops/chat-pane.sh として置いて使います（中身は共通・書き換え不要）。
#
#  ● 起動（ユーザーが自分のターミナルで実行する。AI は実行しない）
#      sh /絶対パス/loops/chat-pane.sh claude
#      sh /絶対パス/loops/chat-pane.sh codex
#    7681 番で ttyd を立てます。止めるときは Ctrl-C。
#
#  ● --open（ttyd がブラウザ接続ごとに自動で呼ぶ。人が直接叩くものではない）
#      sh chat-pane.sh --open <claude|codex> <プロジェクトの絶対パス> <画面ID>
#    画面ID ごとのセッションを loops/.chat-sessions から引き、無ければその場で作って
#    追記してから resume します。HTML 側はセッションIDを持ちません。
# ═══════════════════════════════════════════════════════════════
set -u

PORT=7681
SESSFILE="loops/.chat-sessions"

die() { printf '%s\n' "$*" >&2; exit 1; }

# ── 失敗しても即終了しない。ttyd は子が死ぬと繋ぎ直すので、
#    即死すると「即死→再接続→即死」の無限ループになる。止めて見せる。
hold() {
  printf '\n%s\n\n' "$*"
  printf '%s\n' "このタブを閉じて、ターミナル側を直してから開き直してください。"
  exec tail -f /dev/null
}

# ══════════════ --open モード（ttyd の子）══════════════
if [ "${1-}" = "--open" ]; then
  AI="${2-}"; PROJ="${3-}"; PANE="${4-}"

  # ★起動元が Claude Code の Bash だった場合の保険。これらが付いたままだと
  #   対話モードの claude が「子セッション」とみなされ、会話が保存されない。
  unset CLAUDECODE CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_SESSION_ID CLAUDE_PID

  [ -n "$AI" ] && [ -n "$PROJ" ] && [ -n "$PANE" ] || hold "引数が足りません（--open <ai> <パス> <画面ID>）。"
  cd "$PROJ" 2>/dev/null || hold "プロジェクトのディレクトリが開けません: $PROJ"

  # 実体。起動側が解決して env で渡してくる。素で来たら名前のまま使う
  BIN="${CHAT_PANE_AI_BIN:-$AI}"

  mkdir -p loops
  [ -f "$SESSFILE" ] || : > "$SESSFILE"

  # 「<画面ID> <ai> <セッションID>」の1行を探す
  ID=$(awk -v p="$PANE" -v a="$AI" '$1==p && $2==a {print $3; exit}' "$SESSFILE" 2>/dev/null)

  if [ -z "$ID" ]; then
    # ── 窓口プロンプトを組む ──
    PNAME=$(basename "$PROJ")
    WHERE="$PANE"
    case "$PANE" in
      s-list) ;;
      s-*)
        LID=${PANE#s-}
        if [ -f "loops/$LID.md" ]; then
          TITLE=$(sed -n 's/^title:[[:space:]]*//p' "loops/$LID.md" | head -n 1)
          [ -n "${TITLE:-}" ] && WHERE="${PANE}（${LID}「${TITLE}」）"
        fi
        ;;
    esac
    PROMPT="これは ${PNAME} の loops/index.html 右ペイン（${WHERE}）専用の窓口です。返事は「了解」だけ。"

    printf '%s\n' "${AI} のセッションがまだありません。いま作ります（30秒ほど）…" >&2
    case "$AI" in
      claude)
        U=$(uuidgen 2>/dev/null | tr 'A-Z' 'a-z')
        [ -n "${U:-}" ] || hold "uuidgen が使えません。セッションIDを作れませんでした。"
        "$BIN" --session-id "$U" -p "$PROMPT" >/dev/null 2>&1
        # 実体（会話ログ）ができているかを確かめてから採用する
        if ls "$HOME"/.claude/projects/*/"$U".jsonl >/dev/null 2>&1; then
          ID="$U"
        fi
        ;;
      codex)
        ID=$("$BIN" exec --json --skip-git-repo-check "$PROMPT" </dev/null 2>/dev/null \
             | grep 'thread\.started' \
             | sed -n 's/.*"thread_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
             | head -n 1)
        ;;
      *) hold "知らない AI です: $AI" ;;
    esac

    [ -n "${ID:-}" ] || hold "${AI} のセッションを作れませんでした。ターミナルで ${BIN} が動くかを確かめてください。"
    printf '%s %s %s\n' "$PANE" "$AI" "$ID" >> "$SESSFILE"
  fi

  # ★ --resume はセッションに記録されたモデルを優先するので、settings.json の model を明示して揃える。
  #   （別モデルで動いていた時期があるセッションは、これが無いと毎回そのモデルに戻る）
  MODEL=$(sed -n 's/^[[:space:]]*"model"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$HOME/.claude/settings.json" 2>/dev/null | head -1)
  case "$AI" in
    claude) if [ -n "$MODEL" ]; then exec "$BIN" --resume "$ID" --model "$MODEL"; else exec "$BIN" --resume "$ID"; fi ;;
    codex)  exec "$BIN" resume "$ID" ;;
    *)      hold "知らない AI です: $AI" ;;
  esac
fi

# ══════════════ 起動モード（ユーザーのターミナル）══════════════
AI="${1-}"
case "$AI" in
  claude|codex) ;;
  *) die "使い方: sh $0 claude   /   sh $0 codex" ;;
esac

# 自分の絶対パス（ttyd に渡すので相対だと開けない）
SELF=$0
case "$SELF" in
  /*) ;;
  *)  SELF="$(cd "$(dirname "$SELF")" && pwd)/$(basename "$SELF")" ;;
esac
LOOPS=$(dirname "$SELF")

# ★ cd する前に道具の実体を解決する（--open の中は cwd が変わっているため）
TTYD=$(command -v ttyd 2>/dev/null) || TTYD=""
[ -n "$TTYD" ] || die "ttyd が見つかりません。brew install ttyd を実行してください。"
AIBIN=$(command -v "$AI" 2>/dev/null) || AIBIN=""
[ -n "$AIBIN" ] || die "${AI} が見つかりません。${AI} をインストールするか PATH を確認してください。"

# nodenv のシム経由なら版を固定する。版は loops/README.md の node_version: 行、
# または環境変数 CHAT_PANE_NODE_VERSION から。無ければ素のまま。
NODEV="${CHAT_PANE_NODE_VERSION:-}"
if [ -z "$NODEV" ] && [ -f "$LOOPS/README.md" ]; then
  NODEV=$(sed -n 's/^[[:space:]]*[-*]\{0,1\}[[:space:]]*node_version:[[:space:]]*//p' "$LOOPS/README.md" \
          | head -n 1 | tr -d '`' | awk '{print $1}')
fi
# シム経由でないなら版の固定は要らない
case "$AIBIN" in
  *nodenv*|*/shims/*) ;;
  *) NODEV="" ;;
esac

# 7681 番が空いているか。使われていたら勝手に kill しない
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    die "${PORT} 番は既に使われています。先に動いている ttyd を止めてから実行してください（そのターミナルで Ctrl-C）。"
  fi
fi

printf '%s\n' "ttyd を ${PORT} 番で立てます（${AI}）。止めるときは Ctrl-C。"
printf '%s\n' "loops/index.html をリロードすると右ペインに出ます。"

if [ -n "$NODEV" ]; then
  exec env CHAT_PANE_AI_BIN="$AIBIN" NODENV_VERSION="$NODEV" \
    "$TTYD" -W -a -p "$PORT" -s 9 sh "$SELF" --open "$AI"
else
  exec env CHAT_PANE_AI_BIN="$AIBIN" \
    "$TTYD" -W -a -p "$PORT" -s 9 sh "$SELF" --open "$AI"
fi
