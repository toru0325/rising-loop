#!/usr/bin/env python3
"""画面に出す文が長すぎないかを見る（直さない）。

  python3 check-text.py <loops ディレクトリ|ファイル> [--limit 100] [--mark 出力先.html]

規約: **1段落は 100 字以内。超えるなら 3 行までの箇条書きにする。**
段落 ＝ 画面に見える1かたまりの文。区切りは「段落タグ（p li div td summary…）の始まり」と `<br>`。
      途中の <b> <span> <a> などは文の一部として数える。
箇条書きは 1 項目ずつ数え、**4 項目以上**あれば「長い」として出す。
更新の最後に実行し、出たものを直す（長い説明は畳んだ中か logs/ へ移す）。
依存なし（python3 標準ライブラリのみ）。
"""
import html as H
import os, re, sys

#=== 中を見ないタグ
SKIP = ('script', 'style', 'svg', 'title', 'head')
#=== ここで段落が切れる（開始タグ・終了タグとも）
BREAK = ('p', 'li', 'dd', 'dt', 'div', 'td', 'th', 'summary', 'h1', 'h2', 'h3', 'h4',
         'section', 'article', 'details', 'ul', 'ol', 'dl', 'table', 'tr', 'blockquote',
         'figcaption', 'button', 'br', 'header', 'footer', 'nav', 'main', 'aside', 'label', 'option')
MAX_ITEMS = 3
#=== 行数で数えない箇条書き。手順や項目の並びは「文章の塊」ではないので、3行に縛ると壊れる。
#===   ul.checks = 実装のチェックリスト（✅1〜7）。数を削ると手順が抜ける
SKIP_LIST_CLASSES = ('checks',)


def paragraphs(src):
    """(位置, 行, 場所, 段落テキスト, 開始, 終了)。段落タグと <br> で切り、間のテキストを全部つなぐ。"""
    # 見ない範囲: script/style/svg/title/head と、HTML コメント（<!-- … -->）
    dead = [(m.start(), m.end()) for m in
            re.finditer(r'<(%s)\b.*?</\1>' % '|'.join(SKIP), src, re.S)]
    dead += [(m.start(), m.end()) for m in re.finditer(r'<!--.*?-->', src, re.S)]
    h = re.search(r'<head\b.*?</head>', src, re.S)
    if h:
        dead.append((h.start(), h.end()))
    def alive(i):
        return not any(a <= i < b for a, b in dead)

    out = []
    cur, start, where = [], None, ''
    # 「タグ」と「テキスト」を順に見る
    for m in re.finditer(r'<!--.*?-->|<[^>]+>|[^<]+', src, re.S):
        tok = m.group(0)
        if not alive(m.start()):
            continue
        if tok.startswith('<!--'):
            continue
        if tok.startswith('<'):
            name = re.match(r'</?\s*([a-zA-Z0-9]+)', tok)
            name = name.group(1).lower() if name else ''
            if name in BREAK:
                if cur:
                    txt = re.sub(r'\s+', ' ', H.unescape(''.join(c[0] for c in cur))).strip()
                    if txt:
                        out.append((start, src.count('\n', 0, start) + 1, where, txt, start, cur[-1][1]))
                    cur, start = [], None
                if not tok.startswith('</'):      #=== 開始タグなら、そこが次の段落の場所
                    cls = re.search(r'class="([^"]*)"', tok)
                    where = '<%s %s>' % (name, cls.group(1) if cls else '')
            continue
        if tok.strip():
            if start is None:
                start = m.start()
            cur.append((tok, m.end()))
    if cur:
        txt = re.sub(r'\s+', ' ', H.unescape(''.join(c[0] for c in cur))).strip()
        if txt:
            out.append((start, src.count('\n', 0, start) + 1, where, txt, start, cur[-1][1]))
    return out


def in_data(src, limit):
    """LOOP_DATA の中の、画面に出る文を数える。JS が組み立てて出すので markup には無い。
       対象: points[].note / points[].recs の各行 / summary / trials[].status・plan / records[] の文字列"""
    m = re.search(r'var LOOP_DATA\s*=\s*\{', src)
    if not m:
        return []
    #=== 対応する } まで
    i, depth = m.end(), 1
    while i < len(src) and depth:
        c = src[i]
        if c in '"\'':                      #=== 文字列は飛ばす
            q = c; i += 1
            while i < len(src) and src[i] != q:
                i += 2 if src[i] == '\\' else 1
        elif c == '{': depth += 1
        elif c == '}': depth -= 1
        i += 1
    body = src[m.end():i]
    #=== ★ records[] は画面に出ない。rising.js は一度も読まない（頁の markup が表示の正）。
    #===   AI が施策を把握するためのデータなので、画面の 100字ルールの対象にしない
    rec = body.find('records: [')
    out = []
    #=== 文字列リテラルを位置つきで拾い、長いものだけ返す（キー名は 20 字未満なので自然に外れる）
    for sm in re.finditer(r'"((?:[^"\\]|\\.)*)"', body):
        if rec >= 0 and sm.start() > rec:
            continue
        raw = sm.group(1).replace('\\"', '"')
        #=== ★画面での改行で割る。JS の \n（note は改行して出る）と <br>（recs は innerHTML）。
        #===   割らずに1本で数えると、画面では3行に見えているものを「長い」と言ってしまう
        for t in re.split(r'\\n|<br\s*/?>', raw):
            t = re.sub(r'<[^>]+>', '', t).strip()
            if len(t) > limit:
                pos = m.end() + sm.start()
                out.append((pos, src.count('\n', 0, pos) + 1, 'LOOP_DATA', t,
                            pos, m.end() + sm.end()))
    return out


def lists(src):
    out = []
    cmt = [(m.start(), m.end()) for m in re.finditer(r'<!--.*?-->', src, re.S)]
    for m in re.finditer(r'<(ul|ol)\b([^>]*)>(.*?)</\1>', src, re.S):
        if any(a <= m.start() < b for a, b in cmt):
            continue
        items = re.findall(r'<li\b[^>]*>(.*?)</li>', m.group(3), re.S)
        cls = re.search(r'class="([^"]*)"', m.group(2))
        if cls and any(c in cls.group(1).split() for c in SKIP_LIST_CLASSES):
            continue
        if len(items) > MAX_ITEMS:
            first = re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', '', items[0]))).strip()[:34]
            out.append((m.start(), src.count('\n', 0, m.start()) + 1,
                        cls.group(1) if cls else '', len(items), first, m.start(), m.end()))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        print(__doc__, file=sys.stderr); sys.exit(2)
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 100
    mark = sys.argv[sys.argv.index('--mark') + 1] if '--mark' in sys.argv else None
    target = args[0]
    files = ([target] if os.path.isfile(target)
             else sorted(f for f in (os.path.join(target, x) for x in os.listdir(target)) if f.endswith('.html')))
    nlong = nlist = 0
    marked = []
    for f in files:
        src = open(f, encoding='utf-8').read()
        long_p = [b for b in paragraphs(src) if len(b[3]) > limit] + in_data(src, limit)
        long_l = lists(src)
        if not (long_p or long_l):
            continue
        print('■ %s' % os.path.basename(f))
        for _, line, where, text, s0, e0 in long_p:
            print('  段落 %4d字  %d行目  %s  %s…' % (len(text), line, where, text[:36]))
            nlong += 1
        for _, line, cls, n, first, s0, e0 in long_l:
            print('  箇条書き %d行  %d行目  <ul %s>  %s…' % (n, line, cls, first))
            nlist += 1
        if mark:
            spans = ([(s0, e0, '%d字' % len(t), 'long') for _, _, _, t, s0, e0 in long_p]
                     + [(s0, e0, '%d行' % n, 'list') for _, _, _, n, _, s0, e0 in long_l])
            #=== 重なりは外側（箇条書き）を優先し、内側は印を付けない
            spans.sort(key=lambda x: (x[0], -(x[1])))
            keep, last_end = [], -1
            for s0, e0, lab, kind in spans:
                if s0 < last_end:
                    continue
                keep.append((s0, e0, lab, kind)); last_end = e0
            out = src
            for s0, e0, lab, kind in sorted(keep, key=lambda x: -x[0]):
                #=== 段落の途中に </b> などの閉じタグがあると span で囲めない（入れ子が壊れる）。
                #===   代わりに、段落の直前に印だけを差し込み、段落の中の全テキストに下線を引く
                inner = out[s0:e0]
                inner = re.sub(r'(>|^)([^<>]+)', lambda m: m.group(1) + '<span class="rl-t">' + m.group(2) + '</span>', inner)
                badge = '<span class="rl-%s" data-n="%s"></span>' % (kind, lab)
                out = out[:s0] + badge + inner + out[e0:]
            marked.append((f, out))
    print('■ 長い段落 %d 件（%d字 超）／ 長い箇条書き %d 件（%d行 超）' % (nlong, limit, nlist, MAX_ITEMS))
    if mark and marked:
        style = ('<style>'
                 '.rl-t{background:rgba(185,84,72,.13);box-shadow:0 0 0 1px rgba(185,84,72,.35) inset;border-radius:2px}'
                 '.rl-long,.rl-list{display:inline-block;vertical-align:middle;margin-right:5px;'
                 'padding:1px 7px;border-radius:999px;color:#fff;font:700 11px ui-monospace,monospace}'
                 '.rl-long{background:#b95448}.rl-list{background:#9b6518}'
                 '.rl-long::before{content:attr(data-n)}.rl-list::before{content:attr(data-n)}'
                 '</style>')
        #=== 頁は丸ごと残す（<head> の <link> を捨てると CSS が死ぬ）。印の style を </head> の前に入れる
        #===   1ファイルなら頁そのもの、複数なら iframe で並べる
        outdir = os.path.dirname(os.path.abspath(mark)) or '.'
        os.makedirs(outdir, exist_ok=True)
        #=== 見た目を保つために、頁が読む共通ファイルを出力先にも置く
        srcdir = os.path.dirname(os.path.abspath(marked[0][0]))
        for nm in ('rising.css', 'project.css', 'rising.js'):
            a, b = os.path.join(srcdir, nm), os.path.join(outdir, nm)
            if os.path.isfile(a) and os.path.abspath(a) != os.path.abspath(b):
                import shutil as _sh; _sh.copy(a, b)
        if len(marked) == 1:
            f, out = marked[0]
            out = out.replace('</head>', style + '</head>', 1) if '</head>' in out else style + out
            open(mark, 'w', encoding='utf-8').write(out)
        else:
            names = []
            for f, out in marked:
                out = out.replace('</head>', style + '</head>', 1) if '</head>' in out else style + out
                n = 'marked-' + os.path.basename(f)
                open(os.path.join(outdir, n), 'w', encoding='utf-8').write(out)
                names.append((os.path.basename(f), n))
            body = ''.join('<h2 style="font:700 14px sans-serif;margin:22px 0 6px">%s</h2>'
                           '<iframe src="%s" style="width:100%%;height:78vh;border:1px solid #c9d3bd;border-radius:10px"></iframe>'
                           % (t, n) for t, n in names)
            open(mark, 'w', encoding='utf-8').write(
                '<!doctype html><meta charset="utf-8"><body style="margin:0;padding:18px;background:#eef1e8">' + body)
        print('印をつけた: %s' % mark)


if __name__ == '__main__':
    main()
