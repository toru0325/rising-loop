#!/usr/bin/env python3
"""`loops/LXX.md` を `loops/LXX.html` の `LOOP_DATA` に畳む（1.4.x → 1.5.0 の移行）。

  python3 merge-md.py <loops ディレクトリ> <LXX> [--dry-run]

1ループずつ走らせる。やること（機械的に決まるものだけ。判断が要るぶんは子がやる）:
  1. md の frontmatter を読み、`id parent title summary updated metric{name,start,measured,window}` を
     `LOOP_DATA` の先頭に、`trials[]` と空の `records: []` を末尾に入れる
  2. md の `history[]` と `hist.points[]` を `at` で照合。md にしか無い点は足し、値が食い違う点は
     **常に md を採る**（頁に `updated` が無いので新旧を比べられない。頁側が新しいと分かる点は子が戻す。
     食い違いは報告に出す）
  3. md の「日ごと」表の「ホスト」列を `hist.days[].hosts` に足す（days[] に無い日は足さない）
  4. `data-page-schema="1"` → `"2"`
  5. md の数字トークンのうち、書き換え後の頁に現れないものを一覧で出す

`hist` と `funnel` の中身（コメントを含む）は、手を入れる points / days 以外は文字どおり残す。
`points[]` の要素のあいだの `//===` コメントも、`days[]` と同じく隙間ごと残す。

頁に `data-page-schema="1"` が無ければ、**何も書かずに exit 1**（`"2"` なら「移行済み」で正常終了）。
書く前に md を `loops/.tmp/LXX.md` にコピーし（消さない。削除はユーザー）、元の頁を
`loops/.tmp/LXX-before-merge.html` に退避する。**退避先が既にあれば止める**（上書きしない）。
頁の書き込みは同じディレクトリの一時ファイルに書いてから `os.replace` で置き換える。
報告は stdout と `loops/.tmp/LXX-merge-report.md` の両方に出す（子に渡すため）。
eval はしない。依存なし（標準ライブラリのみ）。
"""
import importlib.util
import os
import re
import shutil
import sys

ASSETS = os.path.dirname(os.path.abspath(__file__))


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ASSETS, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mdf = _load('md_front', 'md-front.py')
spl = _load('split_index', 'split-index.py')

parse_object = spl.parse_object
_skip_ws = spl._skip_ws
_skip_string = spl._skip_string
NUM = re.compile(r'\d[\d,\.]*')

WD = ['月', '火', '水', '木', '金', '土', '日']


def js_lit(v):
    """Python の値を JS のリテラルにする（eval なし）"""
    if v is None:
        return 'null'
    if v is True:
        return 'true'
    if v is False:
        return 'false'
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return '[' + ', '.join(js_lit(x) for x in v) + ']'
    s = str(v).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    return '"%s"' % s


js = js_lit


def loop_data_head(lid, fm):
    """frontmatter から `LOOP_DATA` の先頭（id〜metric）を組む。fm が空なら空で埋める"""
    met = fm.get('metric') or {}
    return ('  id: %s, parent: %s,\n'
            '  title: %s,\n'
            '  summary: %s,\n'
            '  updated: %s,\n'
            '  metric: {\n'
            '    name: %s,\n'
            '    start: %s,\n'
            '    measured: %s,\n'
            '    window: %s\n'
            '  },'
            % (js_lit(fm.get('id') or lid), js_lit(fm.get('parent')),
               js_lit(fm.get('title')), js_lit(fm.get('summary')),
               js_lit(str(fm['updated']) if fm.get('updated') else None),
               js_lit(met.get('name')), js_lit(met.get('start')),
               js_lit(str(met['measured']) if met.get('measured') else None),
               js_lit(met.get('window'))))


def loop_data_trials(fm):
    """frontmatter の trials[] を JS リテラルに"""
    trials = fm.get('trials') or []
    if not trials:
        return '  trials: [],'
    out = []
    for t in trials:
        out.append('    { id: %s, title: %s, status: %s,\n      plan: %s }'
                   % (js_lit(t.get('id')), js_lit(t.get('title')),
                      js_lit(t.get('status')), js_lit(t.get('plan') or [])))
    return '  trials: [\n' + ',\n'.join(out) + '\n  ],'


# ── オブジェクトのキーの位置（値を差し替えるため） ─────────────────

def object_spans(s, open_idx):
    """parse_object と同じ読み方で {キー: (値の開始, 値の終わり)} を返す"""
    assert s[open_idx] == '{'
    out = {}
    i = _skip_ws(s, open_idx + 1)
    n = len(s)
    while i < n:
        if s[i] == '}':
            return out, i + 1
        if s[i] in '"\'':
            e = _skip_string(s, i)
            key = s[i + 1:e - 1]
            i = e
        else:
            m = re.compile(r'[A-Za-z_$][\w$]*').match(s, i)
            if not m:
                raise ValueError('キーが読めません（%d 文字目）' % i)
            key = m.group(0)
            i = m.end()
        i = _skip_ws(s, i)
        if i >= n or s[i] != ':':
            raise ValueError('キー %s のあとに : がありません' % key)
        i = _skip_ws(s, i + 1)
        start = i
        depth = 0
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
        out[key] = (start, len(s[:i].rstrip()))
        i = _skip_ws(s, i)
        if i < n and s[i] == ',':
            i = _skip_ws(s, i + 1)
    raise ValueError('オブジェクトが閉じていません')


def array_items(s):
    """`[ … ]` の生テキストから、要素ごとの (開始, 終わり) を返す"""
    assert s.lstrip()[0] == '['
    i = s.index('[') + 1
    n = len(s)
    out = []
    i = _skip_ws(s, i)
    while i < n:
        if s[i] == ']':
            return out
        start = i
        depth = 0
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
        out.append((start, len(s[:i].rstrip())))
        i = _skip_ws(s, i)
        if i < n and s[i] == ',':
            i = _skip_ws(s, i + 1)
    raise ValueError('配列が閉じていません')


# ── md の日付 ────────────────────────────────────────────────

def md_label(at):
    y, m, d = at.split('-')
    return '%d月%d日' % (int(m), int(d))


def md_end(at):
    y, m, d = at.split('-')
    return '%d/%d' % (int(m), int(d))


def new_point_text(p):
    return ('{ at: %s, label: %s, value: %s, end: %s,\n'
            '        note: %s,\n'
            '        recs: [] }'
            % (js(p['at']), js(md_label(p['at'])), js(p.get('value')),
               js(md_end(p['at'])), js(p.get('note') or '')))


# ── 本体 ────────────────────────────────────────────────────

def merge(loops, lid, dry):
    md_path = os.path.join(loops, '%s.md' % lid)
    html_path = os.path.join(loops, '%s.html' % lid)
    for p in (md_path, html_path):
        if not os.path.isfile(p):
            sys.exit('%s がありません' % p)

    html = open(html_path, encoding='utf-8').read()
    if re.search(r'data-page-schema="2"', html):
        print('%s: 移行済み（data-page-schema="2"）。何もしません。' % lid)
        return
    #=== schema 1 でなければ、どんな頁か分からない。書かずに止まる
    if not re.search(r'data-page-schema="1"', html):
        sys.exit('%s に data-page-schema="1" がありません。'
                 '1.3.x の形の頁ではないので、何も書かずに止まります。' % html_path)

    tmp = os.path.join(loops, '.tmp')
    keep_md = os.path.join(tmp, '%s.md' % lid)
    keep_html = os.path.join(tmp, '%s-before-merge.html' % lid)
    #=== 退避先が残っていたら上書きしない（前回の移行の元がここにしか無いことがある）
    if not dry:
        old = [q for q in (keep_md, keep_html) if os.path.exists(q)]
        if old:
            sys.exit('前回の退避が残っています: %s\n'
                     '確認してから消すか別名にしてください。何も書いていません。' % ' / '.join(old))

    fm, comments, body = mdf.load_md(md_path)
    md_text = open(md_path, encoding='utf-8').read()

    m = re.search(r'\bvar\s+LOOP_DATA\s*=\s*\{', html)
    if not m:
        sys.exit('%s に var LOOP_DATA = { がありません' % html_path)
    open_idx = m.end() - 1
    spans, data_end = object_spans(html, open_idx)
    hist_raw = html[spans['hist'][0]:spans['hist'][1]] if 'hist' in spans else None
    funnel_raw = html[spans['funnel'][0]:spans['funnel'][1]] if 'funnel' in spans else None
    other = [k for k in spans if k not in ('hist', 'funnel')]

    report = {'added': [], 'conflict': [], 'note_diff': [], 'hosts': [], 'hosts_same': [],
              'hosts_have': [], 'hosts_skip': [], 'warn': []}
    if other:
        report['warn'].append('LOOP_DATA に hist/funnel 以外のキーがあります: %s（そのまま残します）' % ', '.join(other))

    # ── hist.points[] を md の history[] と照合 ──
    if hist_raw:
        hs, _ = object_spans(hist_raw, 0)
        hist_new = hist_raw

        # days[] に hosts を足す（先に長さの変わらない後ろから触る）
        edits = []   # (開始, 終わり, 置き換え後)
        hosts = mdf.parse_daily_column(body, 'ホスト')
        #=== 「日ごと」表で捨てた行・列名の揺れを報告に出す（サイレントに捨てない）
        for why, what in getattr(mdf.parse_daily_column, 'warn', []):
            report['warn'].append('日ごと表: %s → %s' % (why, what))
        if hosts and 'days' in hs:
            ds, de = hs['days']
            darr = hist_raw[ds:de]
            seen = set()
            parts = []
            for a, b in array_items(darr):
                el = darr[a:b]
                dm = re.search(r'd\s*:\s*"([^"]+)"', el)
                if not dm:
                    parts.append((a, b, el)); continue
                key = dm.group(1)
                seen.add(key)
                vm = re.search(r'\bv\s*:\s*(-?[\d.]+)', el)
                same = vm and key in hosts and abs(float(vm.group(1)) - hosts[key]) < 1e-9
                if same:
                    #=== 棒そのものがホスト数のループ（L07）。同じ値を2か所に置かない
                    report['hosts_same'].append((key, hosts[key]))
                elif key in hosts and re.search(r'\bhosts\s*:', el):
                    #=== 既に hosts がある日。上書きしない
                    report['hosts_have'].append((key, hosts[key]))
                elif key in hosts:
                    el = el.rstrip()
                    assert el.endswith('}')
                    el = el[:-1].rstrip().rstrip(',') + ', hosts:%d }' % hosts[key]
                    report['hosts'].append((key, hosts[key]))
                parts.append((a, b, el))
            for k in hosts:
                if k not in seen:
                    report['hosts_skip'].append((k, hosts[k]))
            if report['hosts']:
                out = []
                pos = 0
                for a, b, el in parts:
                    out.append(darr[pos:a]); out.append(el); pos = b
                out.append(darr[pos:])
                edits.append((ds, de, ''.join(out)))

        # points[]
        md_hist = fm.get('history') or []
        md_updated = str(fm.get('updated') or '')
        if 'points' in hs:
            ps, pe = hs['points']
            parr = hist_raw[ps:pe]
            items = array_items(parr)
            have = {}
            texts = []
            prev = parr.index('[') + 1
            for a, b in items:
                el = parr[a:b]
                #=== 要素のあいだの //=== コメントを、その要素の前書きとして持ち回る（days[] と同じで捨てない）
                gap = '\n'.join('      ' + l.strip().lstrip(',').strip()
                                 for l in parr[prev:a].split('\n')
                                 if l.strip().lstrip(',').strip().startswith('//'))
                prev = b
                at = re.search(r'at\s*:\s*"([^"]+)"', el)
                at = at.group(1) if at else None
                vm = re.search(r'value\s*:\s*(-?[\d.]+)', el)
                nm = re.search(r'note\s*:\s*"((?:[^"\\]|\\.)*)"', el)
                have[at] = {'value': float(vm.group(1)) if vm else None,
                            'note': nm.group(1) if nm else None, 'i': len(texts)}
                texts.append({'at': at, 'text': el, 'gap': gap})
            for p in md_hist:
                at = str(p.get('at'))
                v = p.get('value')
                if at not in have:
                    texts.append({'at': at, 'text': new_point_text(p), 'gap': ''})
                    report['added'].append((at, v))
                    continue
                h = have[at]
                if v is not None and h['value'] is not None and abs(float(v) - h['value']) > 1e-9:
                    #=== 常に md を採る（頁に updated が無いので新旧を比べられない）。頁側が新しい点は子が戻す
                    report['conflict'].append((at, h['value'], v, md_updated))
                    t = texts[h['i']]['text']
                    texts[h['i']]['text'] = re.sub(r'(value\s*:\s*)-?[\d.]+', lambda _m: _m.group(1) + repr(v), t, count=1)
                mdn = (p.get('note') or '').strip()
                hn = (h['note'] or '').strip()
                if mdn and hn and mdn != hn:
                    report['note_diff'].append((at, hn, mdn))
            texts.sort(key=lambda t: t['at'] or '')
            body_txt = ',\n'.join((t['gap'] + '\n' if t['gap'] else '') + '      ' + t['text'].lstrip()
                                  for t in texts)
            edits.append((ps, pe, '[\n' + body_txt + '\n    ]'))
        elif md_hist:
            report['warn'].append('hist に points[] がありません。md の履歴 %d 点は入れていません' % len(md_hist))

        for a, b, rep in sorted(edits, key=lambda e: -e[0]):
            hist_new = hist_new[:a] + rep + hist_new[b:]
        hist_raw = hist_new

    # ── 新しい LOOP_DATA を組む ──
    parts = [loop_data_head(lid, fm)]
    if hist_raw is not None:
        parts.append('  hist: %s,' % hist_raw)
    if funnel_raw is not None:
        parts.append('  funnel: %s,' % funnel_raw)
    for k in other:
        parts.append('  %s: %s,' % (k, html[spans[k][0]:spans[k][1]]))
    parts.append(loop_data_trials(fm))
    parts.append('  records: []')
    new_data = 'var LOOP_DATA = {\n' + '\n'.join(parts) + '\n}'
    out = html[:m.start()] + new_data + html[data_end:]
    out, n = re.subn(r'(<html[^>]*data-page-schema=")1(")', r'\g<1>2\g<2>', out, count=1)
    if not n:
        report['warn'].append('<html … data-page-schema="1"> が見つからず、2 にできませんでした')

    # ── md の数字で頁に出てこないもの ──
    missing = []
    seen = set()
    page_nums = set(x.rstrip('.,') for x in NUM.findall(out))
    for tok in NUM.findall(md_text):
        tok = tok.rstrip('.,')
        if tok in page_nums or tok in seen:
            continue
        seen.add(tok)
        missing.append(tok)

    text = build_report(lid, fm, comments, report, missing)
    print(text)

    if dry:
        print('  --dry-run のため書いていません。')
        return
    os.makedirs(tmp, exist_ok=True)
    shutil.copy2(md_path, keep_md)
    shutil.copy2(html_path, keep_html)
    #=== 同じディレクトリの一時ファイルに書いてから置き換える（途中で落ちても頁が壊れない）
    write_atomic(html_path, out)
    report_path = os.path.join(tmp, '%s-merge-report.md' % lid)
    write_atomic(report_path, text + '\n')
    print('  書きました: %s' % html_path)
    print('  報告: %s' % report_path)
    print('  退避: %s / %s' % (keep_md, keep_html))
    print('  ※ md はまだ消していません。中身を確かめてから消してください。')


def write_atomic(path, text):
    """同じディレクトリの一時ファイルに書いてから os.replace で置き換える"""
    tmp_path = path + '.tmp-write'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp_path, path)


def build_report(lid, fm, comments, r, missing):
    """報告の全文を作る（stdout と .tmp/LXX-merge-report.md の両方に同じものを出す）"""
    L = []
    def add(line=''):
        L.append(line)
    add('■ %s  %s' % (lid, fm.get('title') or ''))
    add('  updated: %s / metric: %s' % (fm.get('updated'), (fm.get('metric') or {}).get('name')))
    add('  ● 足した点（md にしか無かった履歴）: %s'
        % (', '.join('%s=%s' % (a, v) for a, v in r['added']) if r['added'] else 'なし'))
    if r['conflict']:
        add('  ● 値の食い違い（常に md を採用。頁側が新しいと分かる点は子が戻す）:')
        for at, hv, mv, up in r['conflict']:
            add('      %s  頁 %s / md %s → md を採用（md の updated %s）' % (at, hv, mv, up))
    else:
        add('  ● 値の食い違い: なし')
    if r['note_diff']:
        add('  ● note が違う点（統合は子の仕事・どちらも消していません。全文）:')
        for at, hn, mn in r['note_diff']:
            add('      %s' % at)
            add('        頁: %s' % hn.replace('\n', '\n            '))
            add('        md: %s' % mn.replace('\n', '\n            '))
    else:
        add('  ● note の食い違い: なし')
    add('  ● hosts を足した日: %s'
        % (', '.join('%s=%s' % (d, v) for d, v in r['hosts']) if r['hosts'] else 'なし'))
    if r['hosts_have']:
        add('  ● 既に hosts があるので足さなかった日: %s'
            % ', '.join('%s=%s' % (d, v) for d, v in r['hosts_have']))
    if r['hosts_same']:
        add('  ● 棒の値（v）と同じなので足さなかった日: %s'
            % ', '.join('%s=%s' % (d, v) for d, v in r['hosts_same']))
    if r['hosts_skip']:
        add('  ● days[] に無いので足さなかった日: %s'
            % ', '.join('%s=%s' % (d, v) for d, v in r['hosts_skip']))
    if comments:
        add('  ● md の #=== コメント %d 行（頁の //=== との統合は子の仕事）' % len(comments))
    for w in r['warn']:
        add('  ⚠ %s' % w)
    add('  ● 頁に出てこない md の数字（%d 個）:' % len(missing))
    if missing:
        for i in range(0, len(missing), 12):
            add('      ' + ' '.join(missing[i:i + 12]))
    else:
        add('      なし')
    return '\n'.join(L)


def main():
    argv = sys.argv[1:]
    unknown = [a for a in argv if a.startswith('-') and a != '--dry-run']
    if unknown:
        print(__doc__, file=sys.stderr)
        print('知らないフラグです: %s' % ' '.join(unknown), file=sys.stderr)
        sys.exit(2)
    args = [a for a in argv if not a.startswith('-')]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    loops = os.path.abspath(args[0])
    lid = args[1]
    if not re.fullmatch(r'L\d{2,}', lid):
        sys.exit('ループのIDは L01 の形で指定してください（受け取った値: %s）' % lid)
    merge(loops, lid, '--dry-run' in argv)


if __name__ == '__main__':
    main()
