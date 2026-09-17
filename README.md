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

1. 材料を入れるフォルダを1つ作る（例: `~/rising/自社サービス`）。中に数字の出どころを入れる: GA4 の CSV・売上の表・DB の書き出し・企画書など。多いほどよい
2. そのフォルダで Claude Code（Codex）を起動し、`/rising-loop` と打つ。目標の例が10個出るので、選ぶか自分の言葉で答える

右ペインの AI チャットに `ttyd` が必要です（macOS: `brew install ttyd`）。無ければスキルが止まって案内します。

## 更新したあと

各画面の右ペインのチャットに、この1行を貼って送ってください。

```
rising-loop が X.Y.Z になったので、現行ループを合わせて
```

## 以前 zip で入れた方へ

上の1行を一度実行すれば、以後はこの方法に切り替わります。zip はもう配りません。
