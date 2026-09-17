#!/usr/bin/env python3
"""単一ファイルの loops/index.html（1.2.x）を、殻＋ループ頁に分ける（1.3.0 への移行）。

  python3 split-index.py <loops ディレクトリ> [--dry-run]

出力: <loops>/index.html（殻）、<loops>/LXX.html（ループごと）、<loops>/rising.css、<loops>/rising.js
元の index.html は <loops>/.tmp/index-before-split.html に退避する。

JS は eval しない。`var LOOP_HIST = { … }` を、文字列とコメントを飛ばしながら
括弧の深さを数えて切り出す。書く前に次の3つを検算し、1つでも欠ければ何も書かずに止まる。
  ① 画面があるのに `LOOP_HIST` に該当キーが無いループが無いか
  ② 元の section と、頁に入った section の文字数が一致するか
  ③ 頁に書いた `LOOP_DATA` の数字が、元の `LOOP_HIST[ID]`/`LOOP_FUNNEL[ID]` の数字と一致するか
`LOOP_HIST`/`LOOP_FUNNEL` にあって、どの画面にも対応しないキーは警告だけ出す（止めない）。
依存なし（python3 標準ライブラリのみ）。
"""
import os, re, shutil, sys

ASSETS = os.path.dirname(os.path.abspath(__file__))

# ── JS のオブジェクトリテラルを、括弧の深さを数えて読む ──────────────────

def _skip_ws(s, i):
    """空白と // 行コメント・/* */ ブロックコメントを飛ばす"""
    n = len(s)
    while i < n:
        c = s[i]
        if c in ' \t\r\n':
            i += 1
        elif s.startswith('//', i):
            j = s.find('\n', i)
            i = n if j < 0 else j + 1
        elif s.startswith('/*', i):
            j = s.find('*/', i + 2)
            i = n if j < 0 else j + 2
        else:
            return i
    return i


def _skip_string(s, i):
    """s[i] は ' " ` のどれか。閉じた次の位置を返す"""
    q = s[i]; i += 1; n = len(s)
    while i < n:
        c = s[i]
        if c == '\\':
            i += 2; continue
        if c == q:
            return i + 1
        i += 1
    raise ValueError('文字列が閉じていません（%d 文字目）' % i)


def parse_object(s, open_idx):
    """s[open_idx] == '{' のオブジェクトを読み、{キー: 値の生テキスト} と閉じ括弧の次位置を返す"""
    assert s[open_idx] == '{'
    out = {}
    i = _skip_ws(s, open_idx + 1)
    n = len(s)
    while i < n:
        if s[i] == '}':
            return out, i + 1
        # キー
        if s[i] in '"\'':
            e = _skip_string(s, i)
            key = s[i + 1:e - 1]; i = e
        else:
            m = re.compile(r'[A-Za-z_$][\w$]*').match(s, i)
            if not m:
                raise ValueError('キーが読めません（%d 文字目: %r）' % (i, s[i:i + 20]))
            key = m.group(0); i = m.end()
        i = _skip_ws(s, i)
        if i >= n or s[i] != ':':
            raise ValueError('キー %s のあとに : がありません' % key)
        i = _skip_ws(s, i + 1)
        # 値（括弧の深さを数える。文字列とコメントの中は数えない）
        start = i; depth = 0
        while i < n:
            c = s[i]
            if c in '"\'`':
                i = _skip_string(s, i); continue
            if s.startswith('//', i) or s.startswith('/*', i):
                i = _skip_ws(s, i); continue
            if c in '{[':
                depth += 1; i += 1; continue
            if c in '}]':
                if depth == 0:
                    break
                depth -= 1; i += 1; continue
            if depth == 0 and c == ',':
                break
            i += 1
        out[key] = s[start:i].rstrip()
        i = _skip_ws(s, i)
        if i < n and s[i] == ',':
            i = _skip_ws(s, i + 1)
    raise ValueError('オブジェクトが閉じていません')


def find_var_object(src, name):
    """`var NAME = {` を探し、その中身を {キー: 生テキスト} で返す。無ければ {}"""
    m = re.search(r'\bvar\s+%s\s*=\s*\{' % re.escape(name), src)
    if not m:
        return {}
    obj, _ = parse_object(src, m.end() - 1)
    return obj


def find_var_literal(src, name):
    """`var NAME = <値>;` の値を生テキストで返す（文字列・配列どちらも）。無ければ None"""
    m = re.search(r'\bvar\s+%s\s*=\s*' % re.escape(name), src)
    if not m:
        return None
    i = m.end(); n = len(src); start = i; depth = 0
    while i < n:
        c = src[i]
        if c in '"\'`':
            i = _skip_string(src, i); continue
        if src.startswith('//', i) or src.startswith('/*', i):
            i = _skip_ws(src, i); continue
        if c in '{[(':
            depth += 1; i += 1; continue
        if c in '}])':
            depth -= 1; i += 1; continue
        if depth == 0 and c in ';\n':
            break
        i += 1
    return src[start:i].strip().rstrip(';').strip()


# ── <section class="screen" id="…"> の切り出し（入れ子を数える） ────────────

def section_bounds(html, sid):
    m = re.search(r'<section class="screen" id="%s">' % re.escape(sid), html)
    if not m:
        return None
    start = m.start(); depth = 0
    for t in re.finditer(r'<section\b|</section>', html[start:]):
        depth += 1 if t.group(0).startswith('<section') else -1
        if depth == 0:
            return start, start + t.end()
    raise ValueError('画面 %s の </section> が見つかりません' % sid)


def section_ids(html):
    return re.findall(r'<section class="screen" id="([^"]+)">', html)


# ── 検算に使う数字の集合 ────────────────────────────────────────────

NUM = re.compile(r'\d[\d,\.]*')

def numbers(text):
    return [n.rstrip('.,') for n in NUM.findall(text)]


def loop_data_text(page):
    """生成した頁から `var LOOP_DATA = { … }` の生テキストを取り出す（検算③に使う）"""
    m = re.search(r'\bvar\s+LOOP_DATA\s*=\s*\{', page)
    if not m:
        sys.exit('生成した頁に var LOOP_DATA = { がありません')
    _, end = parse_object(page, m.end() - 1)
    return page[m.end() - 1:end]


def marker_replace(tpl, name, body):
    """<!-- NAME:BEGIN --> 〜 <!-- NAME:END --> の中身を差し替える"""
    b, e = '<!-- %s:BEGIN -->' % name, '<!-- %s:END -->' % name
    i, j = tpl.find(b), tpl.find(e)
    if i < 0 or j < 0:
        sys.exit('雛形に %s マーカーがありません' % name)
    return tpl[:i + len(b)] + '\n' + body.strip('\n') + '\n' + tpl[j:]


def build_loop_page(tpl, sid, section_html, hist, funnel, title):
    """loop.html の雛形の <section> と LOOP_DATA を差し替える"""
    b = section_bounds(tpl, section_ids(tpl)[0])
    out = tpl[:b[0]] + section_html + tpl[b[1]:]

    m = re.search(r'\bvar\s+LOOP_DATA\s*=\s*\{', out)
    if not m:
        sys.exit('loop.html の雛形に var LOOP_DATA = { がありません')
    _, end = parse_object(out, m.end() - 1)
    parts = []
    if hist:
        parts.append('  hist: %s' % hist)
    if funnel:
        parts.append('  funnel: %s' % funnel)
    data = 'var LOOP_DATA = {\n' + ',\n'.join(parts) + '\n}'
    out = out[:m.start()] + data + out[end:]

    if title:
        out = re.sub(r'<title>.*?</title>', lambda _m: '<title>%s</title>' % title, out, count=1, flags=re.S)
    return out


def goal_name(section_html):
    m = re.search(r'<h1 class="goal-name[^"]*"[^>]*>(.*?)</h1>', section_html, re.S)
    if not m:
        return ''
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(1))).strip()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    #=== 知らないフラグを黙って無視しない（--dryrun のつもりが本番で走るのを防ぐ）
    unknown = [a for a in sys.argv[1:] if a.startswith('-') and a != '--dry-run']
    if unknown:
        print(__doc__, file=sys.stderr)
        print('知らないフラグです: %s' % ' '.join(unknown), file=sys.stderr)
        sys.exit(2)
    dry = '--dry-run' in sys.argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    loops = os.path.abspath(args[0])
    src_path = os.path.join(loops, 'index.html')
    if not os.path.isfile(src_path):
        sys.exit('%s がありません' % src_path)
    if os.path.isfile(os.path.join(loops, 'rising.js')):
        print('すでに分割済みです（%s/rising.js があります）。何もしません。' % loops)
        return

    src = open(src_path, encoding='utf-8').read()
    shell_tpl = open(os.path.join(ASSETS, 'index.html'), encoding='utf-8').read()
    loop_tpl = open(os.path.join(ASSETS, 'loop.html'), encoding='utf-8').read()

    ids = [s for s in section_ids(src) if s != 's-list']
    if not ids:
        sys.exit('ループの画面（<section class="screen" id="s-LXX">）が見つかりません')

    hist = find_var_object(src, 'LOOP_HIST')
    funnel = find_var_object(src, 'LOOP_FUNNEL')
    project_dir = find_var_literal(src, 'PROJECT_DIR')
    panes = find_var_literal(src, 'PANES')

    lb = section_bounds(src, 's-list')
    if not lb:
        sys.exit('一覧（s-list）が見つかりません')
    list_section = src[lb[0]:lb[1]]
    svc = goal_name(list_section).replace('ライジング・ループ', '').strip() or '（サービス名）'

    # ── 頁を組む＋検算 ──
    #=== 検算は3つ。①キーの取りこぼし ②section の文字数 ③頁の LOOP_DATA に入った数字
    rows, pages, errors = [], {}, []
    for sid in ids:
        lid = sid[2:]  # s-L01 → L01
        b = section_bounds(src, sid)
        sec = src[b[0]:b[1]]
        h, f = hist.get(lid), funnel.get(lid)
        #=== ① 画面があるのに LOOP_HIST にキーが無い（切り出しが失敗している）
        if h is None:
            errors.append('%s: LOOP_HIST に %s のキーがありません（グラフのデータが頁に入りません）' % (lid, lid))
        page = build_loop_page(loop_tpl, sid, sec, h, f, goal_name(sec))
        pb = section_bounds(page, sid)
        out_sec = page[pb[0]:pb[1]]
        npts = len(re.findall(r'\{\s*d\s*:', h)) if h else 0
        #=== ③ 頁に書いた LOOP_DATA の数字と、元のリテラルの数字を突き合わせる
        src_nums = sorted(numbers((h or '') + '\n' + (f or '')))
        out_nums = sorted(numbers(loop_data_text(page)))
        if src_nums != out_nums:
            only_src = [x for x in src_nums if x not in out_nums]
            only_out = [x for x in out_nums if x not in src_nums]
            errors.append('%s: LOOP_DATA の数字が元と違います（頁に無い %s / 元に無い %s）'
                          % (lid, only_src[:10], only_out[:10]))
        rows.append((lid, len(sec), len(out_sec), npts, len(out_nums), 'あり' if f else '—'))
        pages[lid] = page

    #=== ② どの画面にも対応しないキー（消えた画面の残骸。止めずに知らせるだけ）
    known = set(s[2:] for s in ids)
    orphans = sorted((set(hist) | set(funnel)) - known)

    print('■ ループ（%d 本）' % len(rows))
    print('  %-6s %12s %12s %8s %14s %8s' % ('ID', 'section(元)', 'section(頁)', 'hist点', 'LOOP_DATAの数字', 'funnel'))
    for lid, a, b_, np_, nn, fk in rows:
        print('  %-6s %12d %12d %8d %14d %8s %s'
              % (lid, a, b_, np_, nn, fk, '' if a == b_ else '← 文字数が違う'))
    print('  ※ section(元)=section(頁) で本文が、LOOP_DATAの数字 が元の LOOP_HIST/LOOP_FUNNEL と一致していれば数字は落ちていません')
    if orphans:
        print('  ⚠ どの画面にも対応しないキー: %s（そのまま捨てられます）' % ', '.join(orphans))
    print('■ 殻')
    print('  PROJECT_DIR  = %s' % project_dir)
    print('  SERVICE_NAME = %s' % svc)
    print('  PANES        = %s' % (panes or '').replace('\n', ' '))
    print('  LOOPS ブロック = %d 文字' % len(list_section))

    #=== 殻の cwd。空のまま書くと右ペインが別プロジェクトで動く
    if not project_dir or project_dir.strip("'\"") in ('', '/絶対パス/プロジェクト'):
        errors.append('元の index.html から PROJECT_DIR が取れませんでした（右ペインの cwd が決まりません）')
    if any(a != b_ for _, a, b_, _, _, _ in rows):
        errors.append('section の文字数が変わりました')
    if errors:
        for e in errors:
            print('ERROR %s' % e, file=sys.stderr)
        sys.exit('検算に失敗しました。何も書いていません。')
    if dry:
        print('\n--dry-run のため書いていません。')
        return

    # ── 書く ──
    tmp = os.path.join(loops, '.tmp')
    os.makedirs(tmp, exist_ok=True)
    shutil.copy2(src_path, os.path.join(tmp, 'index-before-split.html'))

    const = ('<script>\n'
             '  //=== このプロジェクトの絶対パス（loops/ の親）。右ペインの AI はここを cwd にして動く\n'
             '  var PROJECT_DIR = %s;\n'
             '  //=== サービス名。<title> と一覧の見出しに入る\n'
             "  var SERVICE_NAME = '%s';\n"
             '  //=== 画面IDの一覧。ループを足したらここにも足す\n'
             '  var PANES = %s;\n'
             '</script>') % (project_dir or "''", svc.replace("'", "\\'"), panes or "['s-list']")
    shell = marker_replace(shell_tpl, 'CONST', const)
    shell = marker_replace(shell, 'LOOPS', list_section)
    open(os.path.join(loops, 'index.html'), 'w', encoding='utf-8').write(shell)
    for lid, page in pages.items():
        open(os.path.join(loops, '%s.html' % lid), 'w', encoding='utf-8').write(page)
    for f in ('rising.css', 'rising.js'):
        shutil.copy2(os.path.join(ASSETS, f), os.path.join(loops, f))

    print('\n書きました: index.html（殻）, %s, rising.css, rising.js'
          % ', '.join('%s.html' % l for l in pages))
    print('退避: %s' % os.path.join(tmp, 'index-before-split.html'))


if __name__ == '__main__':
    main()
