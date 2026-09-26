#!/usr/bin/env python3
"""画面に出す文が長すぎないか見て、直す仕事を AI に渡す。

  python3 check-text.py <loops ディレクトリ|ファイル> [--limit 100]
  python3 check-text.py <ファイル> --work shigoto.json     ← 直す場所を1つのリストに出す
  python3 check-text.py <ファイル> --apply shigoto.json    ← 書き直したものを流し込む

規約: **1段落は 100 字以内。超えるなら 3 行までの箇条書きにする。**
段落 ＝ 画面に見える1かたまりの文。区切りは「段落タグ（p li div td summary…）の始まり」と `<br>`。
      途中の <b> <span> <a> などは文の一部として数える。
箇条書きは 1 項目ずつ数え、**4 項目以上**あれば「長い」として出す。
**数列**（`1,166 → 767 → 531 → 302 …` のような数字の並び）も出す。
★ 長さだけでは塊は測れない。100字以内の短い行でも、数字が並べば読めない
  （L01 の観測枠は6段落・最長92字で検査を通ったが、画面では壁のままだった）。

★ **この道具は「切る」ことをしない。** 機械で改行を入れても読む量は減らず、
  検査を通すだけになる。**短くするか、箇条書きにするか、畳むかは判断**なので AI がやる。
  この道具の仕事は、**判断すべき場所を全部まとめて1つのリストに出すこと**。
  1件ずつ探して1件ずつ直すと時間がかかる（L01 1頁で31分かかった）。

  使い方:
    1. `--work shigoto.json` で仕事のリストを出す
    2. AI が各項目の `new` に書き直したものを入れる（`old` は触らない）
    3. `--apply shigoto.json` で流し込む。`old` が1件だけ見つかるものだけ書く。`.bak` を残す

依存なし（python3 標準ライブラリのみ）。
"""
import html as H
import json, os, re, sys

#=== 中を見ないタグ
SKIP = ('script', 'style', 'svg', 'title', 'head')
#=== ここで段落が切れる（開始タグ・終了タグとも）
BREAK = ('p', 'li', 'dd', 'dt', 'div', 'td', 'th', 'summary', 'h1', 'h2', 'h3', 'h4',
         'section', 'article', 'details', 'ul', 'ol', 'dl', 'table', 'tr', 'blockquote',
         'figcaption', 'button', 'br', 'header', 'footer', 'nav', 'main', 'aside', 'label', 'option')
#=== セルを <span> で並べる表。CSS grid で1セル＝1マスに見えるので、
#===   span を区切りにしないと表ぜんぶが1段落になる（.dtbl の13行が177字の塊として出た）
CELL_GRIDS = ('dtbl',)
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

    #=== セルが span の表の範囲。この中だけ span も区切り扱いにする
    cells = []
    for m in re.finditer(r'<(\w+)[^>]*class="[^"]*\b(?:%s)\b[^"]*"' % '|'.join(CELL_GRIDS), src):
        tag, d, i = m.group(1), 0, m.start()
        for mm in re.finditer(r'<%s\b|</%s>' % (tag, tag), src[i:]):
            d += 1 if not mm.group(0).startswith('</') else -1
            if d == 0:
                cells.append((i, i + mm.end())); break
    in_cell = lambda i: any(a <= i < b for a, b in cells)

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
            if name in BREAK or (name == 'span' and in_cell(m.start())):
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


#=== 数列 ＝ 数字が「→」や「・」で3つ以上つながっているもの。
#===   SKILL.md の「数字は文章に埋めない。数列を文に書かない」を機械で見るため。
#===   日ごとの数字は図（data-hist / cal / hist）で見せる。文字で並べない
#=== ★区切りに / を入れない。「9/25・9/26 は途中」のような日付が数列に見えてしまう
#===   （子が誤検出を避けて文を言い換えていた。無駄な書き直しをさせる）
SEQ = re.compile(r'[0-9][0-9,.]*\s*[%円人回件]?\s*(?:→|・)\s*'
                 r'[0-9][0-9,.]*\s*[%円人回件]?\s*(?:→|・)\s*'
                 r'[0-9][0-9,.]*\s*[%円人回件]?\s*(?:→|・)\s*[0-9]')


def seqs(src, paras):
    """数列を含む段落。長さの検査とは別に出す"""
    out = []
    for pos, line, where, text, s0, e0 in paras:
        m = SEQ.search(text)
        if not m:
            continue
        n = len(re.findall(r'[0-9][0-9,.]*', text))
        out.append((pos, line, where, n, text[:34], s0, e0))
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


def _plain(x):
    return re.sub(r'<[^>]+>', '', x)


def _near(src, pos):
    """その場所がどの施策・どの節の中か。リストを見た AI が場所を思い出せるように"""
    head = src.rfind('<article class="record-item"', 0, pos)
    if head >= 0:
        m = re.search(r'<h3>(.*?)</h3>', src[head:pos + 1] or src[head:head + 1200], re.S)
        if m:
            return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(1))).replace('✓完了', '').strip()[:40]
    m = None
    for mm in re.finditer(r'<span class="k">(\w+)</span>', src[:pos]):
        m = mm
    return m.group(1) if m else '（ゴール・レポート）'


def _folded(src, pos):
    d = 0
    for m in re.finditer(r'<details\b|</details>', src[:pos]):
        d += 1 if m.group(0) == '<details' else -1
    return d > 0


def work(path, limit):
    """直す場所を1つのリストにする。★切らない。判断は AI がやる"""
    src = open(path, encoding='utf-8').read()
    items = []
    for _, line, where, text, s0, e0 in paragraphs(src):
        if len(text) <= limit:
            continue
        items.append(dict(id=len(items) + 1, kind='段落', chars=len(text), line=line,
                          where=where, place=_near(src, s0), folded=_folded(src, s0),
                          js=False, old=src[s0:e0], new=''))
    for _, line, where, text, s0, e0 in in_data(src, limit):
        items.append(dict(id=len(items) + 1, kind='段落（LOOP_DATA）', chars=len(text), line=line,
                          where=where, place='LOOP_DATA', folded=False,
                          js=True, old=src[s0 + 1:e0 - 1], new=''))
    for _, line, cls, n, first, s0, e0 in lists(src):
        items.append(dict(id=len(items) + 1, kind='箇条書き %d行' % n, chars=n, line=line,
                          where='<ul %s>' % cls, place=_near(src, s0), folded=_folded(src, s0),
                          js=False, old=src[s0:e0], new=''))
    #=== ★数列もリストに入れる。100字以内なら段落としては出ないので、
    #===   入れないと「数列だけで引っかかっている項目」を手で探すことになる
    seen = set((x['old']) for x in items)
    for _, line, where, n, first, s0, e0 in seqs(src, paragraphs(src)):
        if src[s0:e0] in seen:
            continue
        items.append(dict(id=len(items) + 1, kind='数列 %d個' % n, chars=n, line=line,
                          where=where, place=_near(src, s0), folded=_folded(src, s0),
                          js=False, old=src[s0:e0], new=''))
    return dict(file=os.path.abspath(path), limit=limit,
                rule='new に書き直したものを入れる。old は触らない。'
                     '段落は100字以内にするか3行までの箇条書きにする。'
                     'あふれた中身は消さずに <details class="fold"> の中へ移す。'
                     '数列（数字の並び）は文から消して図に移す（data-hist / cal / hist / rank）。'
                     'LOOP_DATA（js:true）の中では <br> は文字として出るので、note は \\n を使う',
                items=items)


def apply_work(job):
    """AI が書いた new を流し込む。old が1件だけ見つかるものだけ書く"""
    path = job['file']
    src = open(path, encoding='utf-8').read()
    done, skip = 0, []
    for it in job['items']:
        new = it.get('new') or ''
        if not new.strip() or new == it['old']:
            continue
        if it.get('js') and re.search(r'(?<!\\)"', new):
            skip.append('#%d JS の文字列に裸の " がある' % it['id']); continue
        n = src.count(it['old'])
        if n != 1:
            skip.append('#%d old が %d 件見つかった（file が変わっている）' % (it['id'], n)); continue
        src = src.replace(it['old'], new)
        done += 1
    if done:
        open(path + '.bak', 'w', encoding='utf-8').write(open(path, encoding='utf-8').read())
        open(path, 'w', encoding='utf-8').write(src)
    return done, skip


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        print(__doc__, file=sys.stderr); sys.exit(2)
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 100
    mark = sys.argv[sys.argv.index('--mark') + 1] if '--mark' in sys.argv else None
    target = args[0]
    files = ([target] if os.path.isfile(target)
             else sorted(f for f in (os.path.join(target, x) for x in os.listdir(target)) if f.endswith('.html')))
    if '--work' in sys.argv:
        out = sys.argv[sys.argv.index('--work') + 1]
        job = work(files[0], limit)
        json.dump(job, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('仕事のリスト: %s に %d 件' % (out, len(job['items'])))
        for it in job['items']:
            print('  #%-3d %-16s %4d  %-22s %s%s'
                  % (it['id'], it['kind'], it['chars'], it['place'][:22],
                     '（畳んだ中）' if it['folded'] else '', ''))
        print('※ 各項目の new に書き直したものを入れて、--apply で流し込みます')
        return
    if '--apply' in sys.argv:
        job = json.load(open(sys.argv[sys.argv.index('--apply') + 1], encoding='utf-8'))
        d, skip = apply_work(job)
        print('流し込み %d 件%s' % (d, '（%s.bak に退避）' % os.path.basename(job['file']) if d else ''))
        for m in skip:
            print('  ★ 入れなかった: %s' % m)
        return
    nlong = nlist = nseq = 0
    marked = []
    for f in files:
        src = open(f, encoding='utf-8').read()
        paras = paragraphs(src)
        long_p = [b for b in paras if len(b[3]) > limit] + in_data(src, limit)
        long_l = lists(src)
        long_s = seqs(src, paras)
        if not (long_p or long_l or long_s):
            continue
        print('■ %s' % os.path.basename(f))
        for _, line, where, text, s0, e0 in long_p:
            print('  段落 %4d字  %d行目  %s  %s…' % (len(text), line, where, text[:36]))
            nlong += 1
        for _, line, cls, n, first, s0, e0 in long_l:
            print('  箇条書き %d行  %d行目  <ul %s>  %s…' % (n, line, cls, first))
            nlist += 1
        for _, line, where, n, first, s0, e0 in long_s:
            print('  数列 %3d個  %d行目  %s  %s…' % (n, line, where, first))
            nseq += 1
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
    print('■ 長い段落 %d 件（%d字 超）／ 長い箇条書き %d 件（%d行 超）／ 数列 %d 件'
          % (nlong, limit, nlist, MAX_ITEMS, nseq))
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
