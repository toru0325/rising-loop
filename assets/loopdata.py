#!/usr/bin/env python3
"""ループ頁 `LXX.html` の `var LOOP_DATA = {…};` の **値だけ** を読み書きする部品。

プロジェクトには `loops/update/common.py` として写される（「合わせて」で上書きされる。プロジェクト側で書き換えない）。
ループごとの `loops/update/LXX.py` が `from common import load, save, merge_days, add_point` で使う。

  load(path) -> dict                 `LOOP_DATA` を Python の dict で返す（JS は eval しない）
  save(path, d, dry_run=False)       dict の値を元の位置に書き戻す。コメント・並び・構造は保つ。差分を表で出す
  merge_days(old, new, key='d', drop=())  日付で突き合わせて days[] を更新する（old だけのキーは保つ。drop=['partial'] で固まった日の印を外す）
  add_point(points, p)               同じ at があれば value だけ上書き、無ければ末尾に足す（note/recs は保つ）
  today() / mmdd(iso) / jlabel(iso)  "2026-09-21" / "9/21" / "9月21日"

`save` が守ること:
  - 変わった値のテキストだけ差し替える。変わっていない部分は 1 バイトも触らない（`//===` コメントは元の位置に残る）
  - キーの並びは元のまま。新しいキー・新しい配列要素は末尾に足す。dict から消えたキー・要素は消す
  - 数値は元が整数なら整数、小数は元の桁数を保つ（0.20 → 0.30。0.32 を 0.320 にしない）
  - 書く前に `<loops>/.tmp/LXX-before-update.html` に退避（既にあれば連番）。一時ファイルに書いて os.replace
  - `LOOP_DATA` の外（`data-page-schema`・`<script>`・markup）は触らない。書いた結果を読み直して dict と一致することを確かめる
  - 読めない構文（テンプレート文字列の ${}・関数・undefined など）があれば例外で止める。黙って捨てない

使い方（`loops/update/L01.py` の形。数字取りは README のコマンドを subprocess で叩く）:

    import subprocess, sys
    from common import load, save, merge_days, add_point, today, mmdd, jlabel

    def fetch():
        raw = subprocess.run(['node', 'scripts/purchases-report.cjs', 'now'],
                             capture_output=True, text=True, check=True).stdout
        ...  # raw を読んで計算する。ここはループごとに違う
        return {'days': [{'d': '9/21', 'v': 170, 'hosts': 61}], 'value': 0.95, 'window': '2026-09-15〜2026-09-21（…）'}

    if __name__ == '__main__':
        page = 'loops/L01.html'
        d = load(page)
        n = fetch()
        d['hist']['days'] = merge_days(d['hist']['days'], n['days'])
        d['hist']['points'] = add_point(d['hist']['points'],
                                        {'at': today(), 'label': jlabel(today()), 'value': n['value'], 'end': mmdd(today())})
        d['metric']['measured'] = today()
        d['metric']['window'] = n['window']
        d['updated'] = today()
        save(page, d, dry_run='--dry-run' in sys.argv)

依存なし（python3 標準ライブラリのみ）。このファイル1つで動く（プロジェクトの `loops/update/common.py` に
写されるので、スキルの場所に依存しない）。JS リテラルの読み手は `assets/split-index.py` と同じもの。
"""
import datetime as _dt
import os
import re
import shutil
import sys
import tempfile
import unicodedata

__all__ = ['load', 'save', 'merge_days', 'add_point', 'today', 'mmdd', 'jlabel']


# ── JS リテラルの読み手（assets/split-index.py と同じもの。このファイルだけで動くように内蔵） ──
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



# ── JS リテラル → Python（位置つきの木） ─────────────────────────────────

class _N(object):
    """構文木の節。scalar / object / array。start・end は元テキストの位置"""
    __slots__ = ('kind', 'start', 'end', 'value', 'entries', 'items')

    def __init__(self, kind, start, end=None, value=None):
        self.kind, self.start, self.end, self.value = kind, start, end, value
        self.entries = []   # object: [(key, key_start, node, comma_pos|None)]
        self.items = []     # array:  [(node, comma_pos|None)]


_IDENT = re.compile(r'[A-Za-z_$][\w$]*')
_NUM = re.compile(r'-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')
_INT = re.compile(r'-?\d+')
_WORDS = {'true': True, 'false': False, 'null': None}
_ESC = {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f', 'v': '\v', '0': '\0',
        '\\': '\\', '"': '"', "'": "'", '`': '`', '/': '/'}


def _where(s, i):
    return '%d 行目: %r' % (s.count('\n', 0, i) + 1, s[i:i + 30])


def _decode_str(raw, s, at):
    """引用符つきの JS 文字列リテラル → Python str"""
    q, body = raw[0], raw[1:-1]
    if q == '`' and '${' in body:
        raise ValueError('テンプレート文字列の ${} は読めません（%s）' % _where(s, at))
    out, i, n = [], 0, len(body)
    while i < n:
        c = body[i]
        if c != '\\':
            out.append(c); i += 1; continue
        i += 1
        if i >= n:
            raise ValueError('文字列の末尾に \\ があります（%s）' % _where(s, at))
        e = body[i]
        if e == 'u':
            if body[i + 1:i + 2] == '{':
                j = body.index('}', i)
                cp = int(body[i + 2:j], 16); i = j + 1
            else:
                cp = int(body[i + 1:i + 5], 16); i += 5
                if 0xD800 <= cp < 0xDC00 and body[i:i + 2] == '\\u':
                    lo = int(body[i + 2:i + 6], 16)
                    if 0xDC00 <= lo < 0xE000:
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00); i += 6
            out.append(chr(cp)); continue
        if e == 'x':
            out.append(chr(int(body[i + 1:i + 3], 16))); i += 3; continue
        if e == '\n':
            i += 1; continue   # 行の継続
        if e in _ESC:
            out.append(_ESC[e]); i += 1; continue
        raise ValueError('読めないエスケープ \\%s があります（%s）' % (e, _where(s, at)))
    return ''.join(out)


def _parse_value(s, i):
    if i >= len(s):
        raise ValueError('値の途中で終わっています')
    c = s[i]
    if c == '{':
        return _parse_obj(s, i)
    if c == '[':
        return _parse_arr(s, i)
    if c in '"\'`':
        e = _skip_string(s, i)
        return _N('scalar', i, e, _decode_str(s[i:e], s, i)), e
    if c == '-' or c == '.' or c.isdigit():
        m = _NUM.match(s, i)
        if m:
            txt = m.group(0)
            v = int(txt) if _INT.fullmatch(txt) else float(txt)
            return _N('scalar', i, m.end(), v), m.end()
    m = _IDENT.match(s, i)
    if m and m.group(0) in _WORDS:
        return _N('scalar', i, m.end(), _WORDS[m.group(0)]), m.end()
    raise ValueError('読めない値です（%s）。文字列・数値・true/false/null・配列・オブジェクトだけ読めます' % _where(s, i))


def _parse_obj(s, i):
    node = _N('object', i)
    n = len(s); seen = set()
    i = _skip_ws(s, i + 1)
    while i < n:
        if s[i] == '}':
            node.end = i + 1
            return node, i + 1
        ks = i
        if s[i] in '"\'':
            e = _skip_string(s, i); key = _decode_str(s[i:e], s, i); i = e
        else:
            m = _IDENT.match(s, i)
            if not m:
                raise ValueError('キーが読めません（%s）' % _where(s, i))
            key = m.group(0); i = m.end()
        if key in seen:
            raise ValueError('キー %s が重複しています（%s）' % (key, _where(s, ks)))
        seen.add(key)
        i = _skip_ws(s, i)
        if i >= n or s[i] != ':':
            raise ValueError('キー %s のあとに : がありません（%s）' % (key, _where(s, i)))
        i = _skip_ws(s, i + 1)
        v, i = _parse_value(s, i)
        i = _skip_ws(s, i)
        comma = None
        if i < n and s[i] == ',':
            comma = i; i = _skip_ws(s, i + 1)
        elif i >= n or s[i] != '}':
            raise ValueError('キー %s のあとに , か } がありません（%s）' % (key, _where(s, i)))
        node.entries.append((key, ks, v, comma))
    raise ValueError('オブジェクトが閉じていません')


def _parse_arr(s, i):
    node = _N('array', i)
    n = len(s)
    i = _skip_ws(s, i + 1)
    while i < n:
        if s[i] == ']':
            node.end = i + 1
            return node, i + 1
        v, i = _parse_value(s, i)
        i = _skip_ws(s, i)
        comma = None
        if i < n and s[i] == ',':
            comma = i; i = _skip_ws(s, i + 1)
        elif i >= n or s[i] != ']':
            raise ValueError('配列の要素のあとに , か ] がありません（%s）' % _where(s, i))
        node.items.append((v, comma))
    raise ValueError('配列が閉じていません')


def _to_py(node):
    if node.kind == 'object':
        return dict((k, _to_py(v)) for k, _, v, _ in node.entries)
    if node.kind == 'array':
        return [_to_py(v) for v, _ in node.items]
    return node.value


_HEAD = re.compile(r'\bvar\s+LOOP_DATA\s*=\s*\{')


def _parse_page(src):
    """`var LOOP_DATA = {…};` を切り出して木にする。(木, { の位置, } の次の位置)"""
    m = _HEAD.search(src)
    if not m:
        raise ValueError('var LOOP_DATA = { がありません')
    if _HEAD.search(src, m.end()):
        raise ValueError('var LOOP_DATA = { が2つあります')
    open_idx = m.end() - 1
    node, end = _parse_obj(src, open_idx)
    #=== 切り出しの範囲と上位キーを split-index.py の parse_object と突き合わせる（読み手が2つあるので互いに検算）
    keys, end2 = parse_object(src, open_idx)
    if end2 != end or list(keys) != [k for k, _, _, _ in node.entries]:
        raise ValueError('LOOP_DATA の切り出しが split-index.py の parse_object と食い違います')
    j = _skip_ws(src, end)
    if j >= len(src) or src[j] != ';':
        raise ValueError('LOOP_DATA の } のあとに ; がありません')
    return node, open_idx, end


def _read(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def load(path):
    """`LXX.html` の `LOOP_DATA` を dict で返す（JS は eval しない）"""
    node, _, _ = _parse_page(_read(path))
    return _to_py(node)


# ── Python → JS リテラル ───────────────────────────────────────────────

def _is_scalar(v):
    return v is None or isinstance(v, (bool, int, float, str))


def _js_str(s):
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif ord(ch) < 0x20 or ch in '  ':
            out.append('\\u%04x' % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)


def _fmt_num(v, orig=None):
    """数値を JS に。orig（元のテキスト）があれば、その桁数を保つ"""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if v != v or v in (float('inf'), float('-inf')):
        raise ValueError('NaN / Infinity は書けません')
    if orig is not None:
        m = re.fullmatch(r'-?\d+(?:\.(\d+))?', orig)
        if m:
            dec = len(m.group(1) or '')
            if abs(round(v, dec) - v) < 1e-9:
                return '%.*f' % (dec, v)
    r = repr(v)
    if 'e' in r or 'E' in r:
        r = ('%.12f' % v).rstrip('0').rstrip('.')
    return r


def _key(k):
    return k if _IDENT.fullmatch(k) else _js_str(k)


def _has_content(v):
    return isinstance(v, (list, dict)) and len(v) > 0


def _fmt(v, indent='', sep=': ', path='LOOP_DATA'):
    """新しく足す値を JS のテキストに。indent はその値が置かれる行の字下げ、sep は `k: v` か `k:v`"""
    if isinstance(v, str):
        return _js_str(v)
    if v is None:
        return 'null'
    if isinstance(v, (bool, int, float)):
        return _fmt_num(v)
    if isinstance(v, tuple):
        v = list(v)
    if isinstance(v, list):
        if not v:
            return '[]'
        inner = indent + '  '
        parts = [_fmt(x, inner, sep, '%s[%d]' % (path, i)) for i, x in enumerate(v)]
        if all(_is_scalar(x) for x in v):
            return '[' + ', '.join(parts) + ']'
        return '[\n' + ',\n'.join(inner + p for p in parts) + '\n' + indent + ']'
    if isinstance(v, dict):
        if not v:
            return '{}'
        for k in v:
            if not isinstance(k, str):
                raise TypeError('%s のキー %r が文字列ではありません' % (path, k))
        items = list(v.items())
        one = '{ ' + ', '.join(_key(k) + sep + _fmt(x, indent, sep, path + '.' + k) for k, x in items) + ' }'
        if not any(_has_content(x) for _, x in items) or ('\n' not in one and len(one) <= 100):
            return one
        #=== 中に入れ物がある dict は、先頭の短いスカラーを1行目に、残りは1キー1行（points[] の形）
        inner = indent + '  '
        head = []
        while items and _is_scalar(items[0][1]) and not (isinstance(items[0][1], str) and len(items[0][1]) > 40):
            k, x = items.pop(0)
            head.append(_key(k) + sep + _fmt(x, inner, sep, path + '.' + k))
        rest = [inner + _key(k) + sep + _fmt(x, inner, sep, path + '.' + k) for k, x in items]
        lines = (['{ ' + ', '.join(head) + ','] if head else ['{']) + [r + ',' for r in rest]
        lines[-1] = lines[-1][:-1] + ' }'
        return '\n'.join(lines)
    raise TypeError('%s の値 %r（%s）は書けません。文字列・数値・bool・None・list・dict だけ' % (path, v, type(v).__name__))


# ── 差分を当てる（変わったところだけ編集する） ───────────────────────────

def _line_indent(src, pos):
    ls = src.rfind('\n', 0, pos) + 1
    m = re.match(r'[ \t]*', src[ls:pos])
    return m.group(0)


def _at_line_start(src, pos):
    ls = src.rfind('\n', 0, pos) + 1
    return src[ls:pos].strip() == ''


def _sep_style(text):
    """`{ d:"9/20", … }` なら ':'、`{ at: "…" }` なら ': '"""
    m = re.match(r'\{\s*(?:[\w$]+|"[^"]*")\s*:( ?)', text)
    return ': ' if (not m or m.group(1)) else ':'


def _tail(src, vend, comma):
    """値の終わり → 末尾のカンマ、同じ行の // コメントまで含めた位置。(位置, コメントがあったか)"""
    i = comma + 1 if comma is not None else vend
    j = i
    while j < len(src) and src[j] in ' \t':
        j += 1
    if src.startswith('//', j):
        k = src.find('\n', j)
        return (len(src) if k < 0 else k), True
    return i, False


def _same_scalar(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def _same(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if _is_scalar(a) and _is_scalar(b):
        return _same_scalar(a, b)
    return False


def _label(v, idx):
    if isinstance(v, dict):
        for k in ('d', 'at', 'id', 'name'):
            if isinstance(v.get(k), (str, int)):
                return str(v[k])
    return str(idx)


def _show(v, width=44):
    if isinstance(v, str):
        t = _js_str(v)
    elif v is None:
        t = 'null'
    elif isinstance(v, (bool, int, float)):
        t = _fmt_num(v)
    elif isinstance(v, dict):
        t = ' '.join('%s=%s' % (k, _show(x, 24)) for k, x in v.items()) or '{}'
    elif isinstance(v, list):
        t = '[%d 件]' % len(v)
    else:
        t = repr(v)
    return t if _wlen(t) <= width else _wcut(t, width - 1) + '…'


def _patch(src, node, new, path, edits, changes):
    if node.kind == 'object' and isinstance(new, dict):
        _patch_obj(src, node, new, path, edits, changes)
    elif node.kind == 'array' and isinstance(new, (list, tuple)):
        _patch_arr(src, node, list(new), path, edits, changes)
    elif node.kind == 'scalar' and _is_scalar(new):
        if not _same_scalar(node.value, new):
            orig = src[node.start:node.end]
            text = _fmt_num(new, orig) if isinstance(new, (int, float)) and not isinstance(new, bool) else _fmt(new, path=path)
            edits.append((node.start, node.end, text))
            changes.append((path, orig if _wlen(orig) <= 44 else _wcut(orig, 43) + '…', _show(new)))
    elif not (_is_scalar(new) or isinstance(new, (list, tuple, dict))):
        raise TypeError('%s の値 %r（%s）は書けません' % (path, new, type(new).__name__))
    else:
        #=== 型が変わった（スカラー ↔ 入れ物など）。丸ごと差し替える
        edits.append((node.start, node.end, _fmt(new, _line_indent(src, node.start), path=path)))
        changes.append((path, _show(_to_py(node)), _show(new)))


def _append_after(src, vend, comma, pieces, indent, inline, edits):
    """最後の要素のあとに pieces（テキストの列）を足す。カンマ・同じ行のコメントの位置をまたがない"""
    pos, had_comment = _tail(src, vend, comma)
    if inline and not had_comment:
        #=== 同じ行に続ける。値の直後に入れるので、末尾のカンマがあればその前に入る
        edits.append((vend, vend, ''.join(', ' + p for p in pieces)))
        return
    body = ''.join('\n' + indent + p + ',' for p in pieces)[:-1]
    if comma is not None:
        edits.append((pos, pos, body))
    elif pos == vend:
        edits.append((vend, vend, ',' + body))
    else:
        edits.append((vend, vend, ','))
        edits.append((pos, pos, body))


def _patch_obj(src, node, new, path, edits, changes):
    if not node.entries:
        if new:
            edits.append((node.start, node.end, _fmt(new, _line_indent(src, node.start), path=path)))
            for k, v in new.items():
                changes.append((path + '.' + k, '（追加）', _show(v)))
        return
    old_keys = [k for k, _, _, _ in node.entries]
    for idx, (key, ks, vnode, comma) in enumerate(node.entries):
        if key in new:
            _patch(src, vnode, new[key], path + '.' + key, edits, changes)
            continue
        #=== 消すのは `key: value,` まで。その行に他に何も無ければ行ごと、行の途中なら後ろの空白も詰める
        s0, s1 = ks, (comma + 1 if comma is not None else vnode.end)
        ls = src.rfind('\n', 0, s0) + 1
        le = src.find('\n', s1); le = len(src) if le < 0 else le
        whole = src[ls:s0].strip() == '' and src[s1:le].strip() == ''
        if whole:
            s0, s1 = ls, min(le + 1, len(src))
        elif comma is not None:
            while s1 < len(src) and src[s1] in ' \t':
                s1 += 1
        if comma is None and idx > 0:
            #=== 最後の要素を消したら、直前の要素の末尾のカンマも消す（直前も消すならそちらに含まれる）
            pkey, _, _, pcomma = node.entries[idx - 1]
            if pkey in new and pcomma is not None:
                gap = src[pcomma + 1:ks]
                if not whole and gap.strip() == '' and '\n' not in gap:
                    s0 = pcomma   # `, cost:64` をまとめて消す
                else:
                    edits.append((pcomma, pcomma + 1, ''))
        edits.append((s0, s1, ''))
        changes.append((path + '.' + key, _show(_to_py(vnode)), '（削除）'))
    added = [k for k in new if k not in old_keys]
    if added:
        for k in added:
            if not isinstance(k, str):
                raise TypeError('%s のキー %r が文字列ではありません' % (path, k))
        _, last_ks, last_v, last_comma = node.entries[-1]
        indent = _line_indent(src, last_ks)
        sep = ': ' if re.match(r'(?:[\w$]+|"[^"]*")\s*: ', src[node.entries[0][1]:]) else ':'
        pieces = [_key(k) + sep + _fmt(new[k], indent, sep, path + '.' + k) for k in added]
        _append_after(src, last_v.end, last_comma, pieces, indent, False, edits)
        for k in added:
            changes.append((path + '.' + k, '（追加）', _show(new[k])))


def _patch_arr(src, node, new, path, edits, changes):
    n_old, n_new = len(node.items), len(new)
    for idx in range(min(n_old, n_new)):
        inode, _ = node.items[idx]
        _patch(src, inode, new[idx], '%s[%s]' % (path, _label(new[idx], idx)), edits, changes)
    if n_new > n_old:
        added = new[n_old:]
        if n_old == 0:
            edits.append((node.start, node.end, _fmt(new, _line_indent(src, node.start), path=path)))
        else:
            last_node, last_comma = node.items[-1]
            sep = _sep_style(src[last_node.start:last_node.end])
            indent = _line_indent(src, last_node.start)
            inline = not _at_line_start(src, last_node.start)
            pieces = [_fmt(x, indent, sep, '%s[%d]' % (path, n_old + i)) for i, x in enumerate(added)]
            _append_after(src, last_node.end, last_comma, pieces, indent, inline, edits)
        for i, x in enumerate(added):
            changes.append(('%s[%s]' % (path, _label(x, n_old + i)), '（追加）', _show(x)))
    elif n_new < n_old:
        if n_new == 0:
            edits.append((node.start, node.end, '[]'))
        else:
            prev_node, _ = node.items[n_new - 1]
            last_node, _ = node.items[-1]
            edits.append((prev_node.end, last_node.end, ''))
        for i in range(n_new, n_old):
            v = _to_py(node.items[i][0])
            changes.append(('%s[%s]' % (path, _label(v, i)), _show(v), '（削除）'))


def _apply(src, edits):
    edits = sorted(edits, key=lambda e: (e[0], e[1]))
    for a, b in zip(edits, edits[1:]):
        if a[1] > b[0]:
            raise RuntimeError('編集の範囲が重なりました（%d-%d と %d-%d）' % (a[0], a[1], b[0], b[1]))
    out, pos = [], 0
    for s, e, t in edits:
        out.append(src[pos:s]); out.append(t); pos = e
    out.append(src[pos:])
    return ''.join(out)


# ── 表 ─────────────────────────────────────────────────────────────────

def _wlen(s):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in s)


def _wcut(s, width):
    out, w = [], 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in 'WF' else 1
        if w + cw > width:
            break
        out.append(c); w += cw
    return ''.join(out)


def _pad(s, width):
    return s + ' ' * max(0, width - _wlen(s))


def _print_table(path, changes):
    print('■ %s の LOOP_DATA の差分: %d 件' % (os.path.basename(path), len(changes)))
    if not changes:
        return
    rows = [(p.replace('LOOP_DATA.', '', 1) if p.startswith('LOOP_DATA.') else p, a, b) for p, a, b in changes]
    w0 = max(_wlen('場所'), max(_wlen(r[0]) for r in rows))
    w1 = max(_wlen('前'), max(_wlen(r[1]) for r in rows))
    print('  %s  %s  %s' % (_pad('場所', w0), _pad('前', w1), '後'))
    for p, a, b in rows:
        print('  %s  %s  %s' % (_pad(p, w0), _pad(a, w1), b))


# ── save ───────────────────────────────────────────────────────────────

def _backup(path):
    loops = os.path.dirname(os.path.abspath(path))
    stem = os.path.splitext(os.path.basename(path))[0]
    tmp = os.path.join(loops, '.tmp')
    os.makedirs(tmp, exist_ok=True)
    dst = os.path.join(tmp, '%s-before-update.html' % stem)
    n = 2
    while os.path.exists(dst):
        dst = os.path.join(tmp, '%s-before-update-%d.html' % (stem, n)); n += 1
    shutil.copy2(path, dst)
    return dst


def save(path, d, dry_run=False):
    """dict の値を `LXX.html` の `LOOP_DATA` に書き戻す。変わった値だけ差し替え、差分を表で stdout に出す。
    dry_run=True なら表だけ。変更が無ければ何も書かない。戻り値は差分の列 [(場所, 前, 後), …]"""
    if not isinstance(d, dict):
        raise TypeError('save には LOOP_DATA の dict を渡してください（%s）' % type(d).__name__)
    src = _read(path)
    node, o, e = _parse_page(src)
    edits, changes = [], []
    _patch(src, node, d, 'LOOP_DATA', edits, changes)
    out = _apply(src, edits)
    #=== 書く前に、書いた結果を読み直して dict と一致すること、LOOP_DATA の外が変わっていないことを確かめる
    node2, o2, e2 = _parse_page(out)
    if not _same(_to_py(node2), d):
        raise RuntimeError('書き戻した LOOP_DATA を読み直すと dict と一致しません。何も書いていません')
    if out[:o] != src[:o] or out[e2:] != src[e:]:
        raise RuntimeError('LOOP_DATA の外が変わりました。何も書いていません')
    _print_table(path, changes)
    if not changes:
        print('  変更なし。書いていません。')
        return changes
    if dry_run:
        print('  --dry-run のため書いていません。')
        return changes
    bak = _backup(path)
    fd, tmp = tempfile.mkstemp(prefix='.%s.' % os.path.basename(path), suffix='.tmp', dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(out)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    print('  退避: %s' % bak)
    print('  書きました: %s' % os.path.normpath(path))
    return changes


# ── days[] / points[] の突き合わせ ──────────────────────────────────────

def merge_days(old, new, key='d', drop=()):
    """日付（key）で突き合わせる。new にある日は new 側の値で差し替え、old にしかないキー（partial・w・hosts …）は保つ。
    old に無い日は末尾に足す。並びは old の順＋追加分。
    drop に挙げたキー（例: ['partial']）は、new のその日に無ければ old から外す（固まった日の partial を落とすとき）"""
    out = [dict(x) for x in old]
    idx = dict((x.get(key), i) for i, x in enumerate(out))
    for n in new:
        k = n.get(key)
        if k is None:
            raise ValueError('merge_days: %r に %s がありません' % (n, key))
        if k in idx:
            cur = out[idx[k]]
            cur.update(n)
            for dk in drop:
                if dk not in n:
                    cur.pop(dk, None)
        else:
            out.append(dict(n)); idx[k] = len(out) - 1
    return out


def add_point(points, p):
    """同じ at の点があれば value（と end・label など p にあるキー）を上書きし、note・recs は既存を保つ。
    無ければ末尾に足す（note が無ければ ""、recs が無ければ [] を補う）"""
    if 'at' not in p:
        raise ValueError('add_point: p に at がありません')
    out = [dict(x) for x in points]
    for x in out:
        if x.get('at') == p['at']:
            for k, v in p.items():
                if k in ('note', 'recs') and k in x:
                    continue
                x[k] = v
            return out
    q = dict(p)
    q.setdefault('note', '')
    q.setdefault('recs', [])
    out.append(q)
    return out


# ── 日付の小物 ──────────────────────────────────────────────────────────

def today():
    """'2026-09-21'（points[].at・metric.measured・updated の形）"""
    return _dt.date.today().isoformat()


def mmdd(iso):
    """'2026-09-21' → '9/21'（days[].d・points[].end の形）"""
    y, m, d = (int(x) for x in iso.split('-'))
    return '%d/%d' % (m, d)


def jlabel(iso):
    """'2026-09-21' → '9月21日'（points[].label の形）"""
    y, m, d = (int(x) for x in iso.split('-'))
    return '%d月%d日' % (m, d)


if __name__ == '__main__':
    #=== 手で確かめるとき: python3 loopdata.py loops/L01.html → 上位キーと点の数を出す（書かない）
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    _d = load(sys.argv[1])
    print('keys: %s' % ', '.join(_d))
    if isinstance(_d.get('hist'), dict):
        print('days: %d  line: %d  points: %d' % (len(_d['hist'].get('days', [])), len(_d['hist'].get('line', [])), len(_d['hist'].get('points', []))))
