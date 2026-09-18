# rising-loop（ライジング・ループ）

リリース済みサービスの運営・改善ループを回す、Claude Code / codex 用のスキルです。

**▶ 解説動画（まずこれを見るのが早いです）**: https://youtu.be/8pE4ezloXOQ

## 対象

**macOS 用**です。Windows の人は WSL（Ubuntu など）の中で Claude Code とこのスキルを使ってください。WSL の中なら手順はそのまま通ります。

## 入れ方・更新のしかた

ターミナルでこの1行。**初回も更新も同じ**です。

```
curl -fsSL https://raw.githubusercontent.com/toru0325/rising-loop/main/install.sh | sh
```

- `~/.claude/skills/rising-loop` に入ります。以前の版は上書きされます（古い版は GitHub にあります）
- 更新すると「何が変わったか」がその場に表示されます（`CHANGELOG.md` の該当の項）
- 新しい版があるときは、`/rising-loop` を使った際にスキルが知らせます

## ライジング・ループとは

ひとつの指標を計測し、その数字を上げるための施策を AI と一緒に回し続ける仕組みです。
回すのは4段階: ゴール（動かしたい数字）→ ボトルネック（届かない理由）→ 施策の実行 → 施策の評価（効いたか A〜E）→ ゴールへ戻る。

## 使い始め

1. このサービス専用のフォルダを1つ作る（例: `~/rising/自社サービス`）。企画書や仕様など、サービスの説明になるものがあれば入れておく
2. そのフォルダで Claude Code（Codex）を起動し、`/rising-loop` と打つ
3. 目標の例を参考に、自分のゴールを答える。AI がループの画面（`loops/index.html`）を作る。以後はこの画面が入口

右ペインの AI チャットに `ttyd` が必要です（macOS: `brew install ttyd`）。無ければスキルが止まって案内します。

## 効果を上げるコツ

数字が自動で取れる口を、できるだけ多く AI につなぐこと。GA4・Search Console・Stripe・Shopify・広告管理画面・自社 DB・Google Sheets などの API や MCP をつなぐほど、AI が自分で数字を取りに行けるようになり、更新が速く、評価が正確になります。つなぐ口が無い場合は、都度 CSV を渡したり、Claude Code にブラウザを操作させて数字を取るのもおすすめです。

## 更新したあと

各画面の右ペインのチャットに、この1行を貼って送ってください。

```
rising-loop が X.Y.Z になったので、このループを合わせて
```

## 以前 zip で入れた方へ

上の1行を一度実行すれば、以後はこの方法に切り替わります。zip はもう配りません。

## ライセンス

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.ja)（表示・非営利）。© Voice App Lab
個人・社内での利用、改変、再配布は自由です。**商用利用（販売・有償サービスへの組み込み）は不可**。利用の際は「Voice App Lab / rising-loop」のクレジットを残してください。
