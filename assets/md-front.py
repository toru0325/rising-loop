#!/usr/bin/env python3
"""`loops/LXX.md` の frontmatter と「日ごと」表を読む小さな読み手（1.5.0 の移行用）。

YAML パーサは使わない（標準ライブラリのみ・eval なし）。rising-loop の frontmatter が実際に取る形
だけを読む:

  key: 値                      … 文字列・数値・null
  key:                         … 下にぶら下がる辞書（2段のインデント）または配列
    key2: 値
  key:
    - key3: 値                 … 配列の要素（辞書）。続きは 4 スペース
      key4: 値
      plan:
        - "文字列"             … 文字列だけの配列
  #=== 行コメント               … 値ではないので comments に集める

読めない行が1つでもあれば MdError を投げる（黙って落とさない）。
merge-md.py と split-index.py の両方から import して使う。
"""
import re

__all__ = ['MdError', 'parse_frontmatter', 'split_frontmatter', 'parse_daily_column', 'load_md']


class MdError(Exception):
    pass


_KEY = re.compile(r'([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*))?$')
#=== 素のトークン＝数値・英字・記号だけ。\w だと日本語が通り、note の中の # を切ってしまう
_BARE = re.compile(r'^[0-9A-Za-z.+-]*$')


def _scalar(raw):
    """値1つを Python の値に。引用符・行末の # コメントを外す"""
    s = raw.strip()
    if not s:
        return None
    if s[0] in '"\'' and len(s) >= 2 and s[-1] == s[0]:
        return s[1:-1]
    #=== 行末コメントは「# の前が素のトークン（数値・英数字）のとき」だけ外す。
    #===   日本語の note に出てくる # を切らないため
    m = re.match(r'^(.*?)\s+#(?!==).*$', s)
    if m and _BARE.match(m.group(1).strip()):
        s = m.group(1).strip()
    if s in ('null', '~', 'None'):
        return None
    if s == 'true':
        return True
    if s == 'false':
        return False
    if re.fullmatch(r'-?\d+', s):
        return int(s)
    if re.fullmatch(r'-?\d*\.\d+', s):
        return float(s)
    return s


def split_frontmatter(text):
    """(frontmatter の本文, 残りの本文) を返す。frontmatter が無ければ (None, text)"""
    if not text.startswith('---\n'):
        return None, text
    end = text.find('\n---\n', 3)
    if end < 0:
        raise MdError('frontmatter が閉じていません（2本目の --- がありません）')
    return text[4:end + 1], text[end + 5:]


def parse_frontmatter(text):
    """frontmatter を読む。(data: dict, comments: list[(行番号, 行)]) を返す"""
    body, _ = split_frontmatter(text)
    if body is None:
        raise MdError('frontmatter（先頭の ---）がありません')
    comments = []
    rows = []   # (インデント, 本文, 行番号, 配列の要素の頭か)
    for lineno, line in enumerate(body.split('\n'), start=2):
        if not line.strip():
            continue
        if '\t' in line:
            raise MdError('%d 行目にタブがあります: %r' % (lineno, line))
        indent = len(line) - len(line.lstrip(' '))
        s = line.strip()
        if s.startswith('#'):
            comments.append((lineno, s))
            continue
        if s.startswith('- '):
            rows.append((indent + 2, s[2:].strip(), lineno, True))
        elif s == '-':
            raise MdError('%d 行目: 中身の無い配列の要素です' % lineno)
        else:
            rows.append((indent, s, lineno, False))
    data, i = _parse_map(rows, 0, rows[0][0] if rows else 0)
    if i < len(rows):
        raise MdError('%d 行目でインデントが合わなくなりました: %r' % (rows[i][2], rows[i][1]))
    return data, comments


def _child_indent(rows, i, indent):
    """rows[i] より深いインデントが続くか"""
    return i < len(rows) and rows[i][0] > indent


def _parse_map(rows, i, indent):
    out = {}
    while i < len(rows):
        ind, s, lineno, is_item = rows[i]
        if ind < indent or (ind == indent and is_item and out):
            break
        if ind > indent:
            raise MdError('%d 行目: インデントが深すぎます: %r' % (lineno, s))
        m = _KEY.match(s)
        if not m:
            raise MdError('%d 行目が読めません（key: 値 の形ではありません）: %r' % (lineno, s))
        key, val = m.group(1), m.group(2)
        i += 1
        if val is None or not val.strip():
            if _child_indent(rows, i, indent):
                ci = rows[i][0]
                if rows[i][3]:
                    out[key], i = _parse_seq(rows, i, ci)
                else:
                    out[key], i = _parse_map(rows, i, ci)
            else:
                out[key] = None
        else:
            out[key] = _scalar(val)
    return out, i


def _parse_seq(rows, i, indent):
    out = []
    while i < len(rows):
        ind, s, lineno, is_item = rows[i]
        if ind != indent or not is_item:
            break
        m = _KEY.match(s)
        if m and s[0] not in '"\'':
            v, i = _parse_map(rows, i, indent)
            out.append(v)
        else:
            out.append(_scalar(s))
            i += 1
    return out, i


def _resolve(v):
    return v


def load_md(path):
    """ファイルを読み、(frontmatter の dict, comments, 本文) を返す"""
    text = open(path, encoding='utf-8').read()
    data, comments = parse_frontmatter(text)
    _, body = split_frontmatter(text)
    return _resolve(data), comments, body


# ── 「日ごと」表 ────────────────────────────────────────────────

_DAY = re.compile(r'(\d{1,2})/(\d{1,2})')


def parse_daily_column(body, column='ホスト'):
    """本文の `### 日ごと…` の下の markdown 表から {"9/11": 259} を作る。
    表が無い・その列が無いなら {} を返す。捨てた行は warn（[(理由, 中身)]）に積んで、黙って落とさない"""
    out = {}
    warn = parse_daily_column.warn = []
    for m in re.finditer(r'^### 日ごと.*$', body, re.M):
        chunk = body[m.end():]
        nxt = re.search(r'^#{2,3} ', chunk, re.M)
        if nxt:
            chunk = chunk[:nxt.start()]
        rows = [l.strip() for l in chunk.split('\n') if l.strip().startswith('|')]
        if len(rows) < 3:
            continue
        head = [c.strip() for c in rows[0].strip('|').split('|')]
        if column not in head:
            #=== 列名の揺れ（「ホスト数」など）は警告する。その列がそもそも無い表は対象外なので黙っている
            near = [h for h in head if h and (column in h or h in column)]
            if near:
                warn.append(('「%s」列がありません。似た列名があります: %s' % (column, ', '.join(near)),
                             ' | '.join(head)))
            continue
        ci = head.index(column)
        for r in rows[2:]:
            cells = [c.strip() for c in r.strip('|').split('|')]
            if len(cells) <= ci:
                warn.append(('列が足りません（%d 列しかありません）' % len(cells), r))
                continue
            d = _DAY.match(cells[0].lstrip('*').strip())
            if not d:
                continue  # 合計行など（日付で始まらない行は元から対象外）
            raw = cells[ci].replace(',', '').replace('人', '').replace('*', '').strip()
            if not re.fullmatch(r'-?\d+(\.\d+)?', raw):
                if raw not in ('', '-', '—'):
                    warn.append(('数値として読めません（単位つき？）', '%s: %s' % (cells[0], cells[ci])))
                continue
            key = '%d/%d' % (int(d.group(1)), int(d.group(2)))
            out[key] = int(raw) if raw.isdigit() else float(raw)
    return out
