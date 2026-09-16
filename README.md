# rising-loop（ライジング・ループ）

リリース済みサービスの運営・改善ループを回す、Claude Code / codex 用のスキルです。

## 入れ方・更新のしかた

ターミナルでこの1行。**初回も更新も同じ**です。

```
curl -fsSL https://raw.githubusercontent.com/toru0325/rising-loop/main/install.sh | sh
```

- `~/.claude/skills/rising-loop` に入ります。以前の版は上書きされます（古い版は GitHub にあります）
- 更新すると「何が変わったか」がその場に表示されます（`CHANGELOG.md` の該当の項）
- 新しい版があるときは、`/rising-loop` を使った際にスキルが知らせます

## 使い始め

Claude Code か codex で、プロジェクトを開いて `/rising-loop` と打つか、「運営どうなってる」「数字を見て」と話しかけてください。
右ペインの AI チャットに `ttyd` が必要です（macOS: `brew install ttyd`）。無ければスキルが止まって案内します。

## 以前 zip で入れた方へ

上の1行を一度実行すれば、以後はこの方法に切り替わります。zip はもう配りません。
