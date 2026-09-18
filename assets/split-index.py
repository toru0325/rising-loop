#!/usr/bin/env python3
"""単一ファイルの loops/index.html（1.2.x）を、殻＋ループ頁に分ける（1.3.0 への移行）。

  python3 split-index.py <loops ディレクトリ> [--dry-run]
  python3 split-index.py <loops ディレクトリ> --project-css   # 分割済み。退避ファイルから project.css だけ作り直す

頁は schema 1（`LOOP_DATA` が `hist` と `funnel` だけを持つ 1.3.x の形）で作る。frontmatter は読まない。
分割のあとに `merge-md.py` を1ループずつ走らせて schema 2（1.5.0）にする。

出力: <loops>/index.html（殻）、<loops>/LXX.html（ループごと）、<loops>/rising.css、<loops>/rising.js、
      <loops>/project.css（元の <style> のうち rising.css に無い規則。プロジェクト独自の CSS。「合わせて」で上書きされない）
元の index.html は <loops>/.tmp/index-before-split.html に退避する。

JS は eval しない。`var LOOP_HIST = { … }` を、文字列とコメントを飛ばしながら
括弧の深さを数えて切り出す。書く前に次の3つを検算し、1つでも欠ければ何も書かずに止まる。
  ① 画面があるのに `LOOP_HIST` に該当キーが無いループが無いか
  ② 元の section と、頁に入った section の文字数が一致するか
  ③ 元の `LOOP_HIST[ID]`/`LOOP_FUNNEL[ID]` の数字が、頁の `LOOP_DATA` に全部入っているか
    （頁の `LOOP_DATA` は hist/funnel だけなので、数字は元のリテラルと1対1で突き合わせる）
`LOOP_HIST`/`LOOP_FUNNEL` にあって、どの画面にも対応しないキーは警告だけ出す（止めない）。
依存なし（python3 標準ライブラリのみ）。
"""
import importlib.util, os, re, shutil, sys

ASSETS = os.path.dirname(os.path.abspath(__file__))


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ASSETS, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def _css_rules(css):
    """CSS を (セレクタ文字列, 規則全文) の列に。@media などのブロックは中の規則ごとに分けず、ブロック全体を1件として扱う。"""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out = []; i = 0; n = len(css)
    while i < n:
        j = css.find('{', i)
        if j < 0: break
        head = css[i:j].strip()
        depth = 0; k = j
        while k < n:
            if css[k] == '{': depth += 1
            elif css[k] == '}':
                depth -= 1
                if depth == 0: break
            k += 1
        out.append((head, css[i:k+1].strip()))
        i = k + 1
    return out

def project_css(orig_html, rising_css):
    """元の index.html の <style> のうち、rising.css に無いセレクタの規則だけを返す（プロジェクト独自の CSS）。"""
    m = re.search(r'<style>(.*?)</style>', orig_html, re.S)
    if not m: return ''
    have = set(h for h, _ in _css_rules(rising_css))
    keep = []
    for head, rule in _css_rules(m.group(1)):
        if head.startswith('@'):
            # @media 等は、中のセレクタが1つでも rising.css に無ければ丸ごと残す
            inner = re.search(r'\{(.*)\}\s*$', rule, re.S)
            inner_heads = [h for h, _ in _css_rules(inner.group(1))] if inner else []
            if any(h not in have for h in inner_heads): keep.append(rule)
        elif head not in have:
            keep.append(rule)
    if not keep: return ''
    return ('/* project.css — このプロジェクト独自の CSS。分割時に元の index.html から自動で抜き出したもの。\n'
            '   rising.css（共通・「合わせて」で上書きされる）には手を入れず、画面固有の見た目はここに書く。 */\n'
            + '\n'.join(keep) + '\n')

def marker_replace(tpl, name, body):
    """<!-- NAME:BEGIN --> 〜 <!-- NAME:END --> の中身を差し替える"""
    b, e = '<!-- %s:BEGIN -->' % name, '<!-- %s:END -->' % name
    i, j = tpl.find(b), tpl.find(e)
    if i < 0 or j < 0:
        sys.exit('雛形に %s マーカーがありません' % name)
    return tpl[:i + len(b)] + '\n' + body.strip('\n') + '\n' + tpl[j:]


def build_loop_page(tpl, sid, section_html, hist, funnel, title):
    """loop.html の雛形の <section> と LOOP_DATA を差し替える（LOOP_DATA は schema 1: hist と funnel だけ）"""
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
    #=== 分割で作る頁は schema 1。frontmatter を畳むのは merge-md.py（1.5.0 の移行）
    out, n = re.subn(r'(<html[^>]*data-page-schema=")\d+(")', r'\g<1>1\g<2>', out, count=1)
    if not n:
        sys.exit('loop.html の雛形に data-page-schema がありません')

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
    unknown = [a for a in sys.argv[1:] if a.startswith('-') and a not in ('--dry-run', '--project-css')]
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
    rising_css = open(os.path.join(ASSETS, 'rising.css'), encoding='utf-8').read()
    if '--project-css' in sys.argv:
        #=== 分割済みのプロジェクトで、退避した元の index.html から project.css だけ作り直す（1.3.0 で落としていた分）
        bak = os.path.join(loops, '.tmp', 'index-before-split.html')
        if not os.path.isfile(bak):
            sys.exit('%s がありません（分割時の退避ファイルが要ります）' % bak)
        pcss = project_css(open(bak, encoding='utf-8').read(), rising_css)
        n = len(_css_rules(pcss))
        if dry:
            print('project.css に入る規則: %d 件（--dry-run のため書いていません）' % n); return
        open(os.path.join(loops, 'project.css'), 'w', encoding='utf-8').write(pcss)
        print('書きました: project.css（%d 件の規則）' % n); return
    if os.path.isfile(os.path.join(loops, 'rising.js')):
        print('すでに分割済みです（%s/rising.js があります）。何もしません。project.css だけ作り直すなら --project-css' % loops)
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
        only_src = [x for x in src_nums if x not in out_nums]
        if only_src:
            errors.append('%s: LOOP_DATA から数字が落ちました（頁に無い %s）' % (lid, only_src[:10]))
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

    pcss = project_css(src, rising_css)
    open(os.path.join(loops, 'project.css'), 'w', encoding='utf-8').write(pcss)
    print('\n書きました: index.html（殻・頁は schema 1）, %s, rising.css, rising.js, project.css（独自 CSS %d 件）'
          % (', '.join('%s.html' % l for l in pages), len(_css_rules(pcss))))
    print('退避: %s' % os.path.join(tmp, 'index-before-split.html'))
    print('次: 1ループずつ merge-md.py を走らせて 1.5.0（schema 2）にします')


if __name__ == '__main__':
    main()
