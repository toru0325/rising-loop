#!/usr/bin/env python3
"""殻（loops/index.html）を雛形と入れ替える。「このループを合わせて」で使う。

  python3 shell-update.py <loops ディレクトリ> [--dry-run]

いまの殻から保存する2か所（CONST ブロック・LOOPS ブロック）を取り、
assets/index.html の同じマーカーの中に入れて書き直す。
共通ファイル rising.css / rising.js / chat-pane.sh は assets/ のもので上書きする。
ループ頁 LXX.html は触らない。ただし data-page-schema が雛形と違えば警告を出す。
元の殻は <loops>/.tmp/index-before-update.html に退避する。
依存なし（python3 標準ライブラリのみ）。
"""
import glob, os, re, shutil, sys

ASSETS = os.path.dirname(os.path.abspath(__file__))
#=== 共通ファイル。値を埋めずに、そのままコピーする
COMMON = ('rising.css', 'rising.js', 'chat-pane.sh')


def block(html, name):
    """<!-- NAME:BEGIN --> 〜 <!-- NAME:END --> の中身。無ければ None"""
    b, e = '<!-- %s:BEGIN -->' % name, '<!-- %s:END -->' % name
    i, j = html.find(b), html.find(e)
    if i < 0 or j < 0 or j < i:
        return None
    return html[i + len(b):j].strip('\n')


def put(html, name, body):
    b, e = '<!-- %s:BEGIN -->' % name, '<!-- %s:END -->' % name
    i, j = html.find(b), html.find(e)
    if i < 0 or j < 0:
        sys.exit('雛形に %s マーカーがありません' % name)
    return html[:i + len(b)] + '\n' + body.strip('\n') + '\n' + html[j:]


def page_schema(html):
    """<html … data-page-schema="N"> の N。無ければ '（無し）'"""
    m = re.search(r'<html[^>]*\bdata-page-schema="([^"]*)"', html)
    return m.group(1) if m else '（無し）'


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
    path = os.path.join(loops, 'index.html')
    if not os.path.isfile(path):
        sys.exit('%s がありません' % path)

    cur = open(path, encoding='utf-8').read()
    const, loopsblk = block(cur, 'CONST'), block(cur, 'LOOPS')
    if const is None or loopsblk is None:
        sys.exit('マーカーがありません。1.2.x 形式です。先に split-index.py を実行してください。')

    print('■ 保存した CONST')
    for name in ('PROJECT_DIR', 'SERVICE_NAME', 'PANES'):
        m = re.search(r'\bvar\s+%s\s*=\s*([^\n]*?);\s*$' % name, const, re.M)
        print('  %-12s = %s' % (name, m.group(1) if m else '（見つかりません）'))
    print('■ LOOPS ブロック = %d 文字' % len(loopsblk))

    #=== ループ頁の構造版。ここでは直さない（止めない）。違えば版ごとの移行手順を見てもらう
    want = page_schema(open(os.path.join(ASSETS, 'loop.html'), encoding='utf-8').read())
    old = []
    for f in sorted(glob.glob(os.path.join(loops, 'L*.html'))):
        got = page_schema(open(f, encoding='utf-8').read())
        if got != want:
            old.append((os.path.basename(f), got))
    print('■ ループ頁の構造版（data-page-schema）= %s（雛形）' % want)
    if old:
        for name, got in old:
            print('  ⚠ %s: ループ頁の構造が古い（schema %s → %s）。この版の移行手順を SKILL.md で確認してください'
                  % (name, got, want))

    if dry:
        print('\n--dry-run のため書いていません。')
        return

    tpl = open(os.path.join(ASSETS, 'index.html'), encoding='utf-8').read()
    out = put(put(tpl, 'CONST', const), 'LOOPS', loopsblk)

    tmp = os.path.join(loops, '.tmp')
    os.makedirs(tmp, exist_ok=True)
    shutil.copy2(path, os.path.join(tmp, 'index-before-update.html'))
    open(path, 'w', encoding='utf-8').write(out)
    for f in COMMON:
        shutil.copy2(os.path.join(ASSETS, f), os.path.join(loops, f))

    print('\n上書き: index.html（殻）, %s' % ', '.join(COMMON))
    print('退避: %s' % os.path.join(tmp, 'index-before-update.html'))


if __name__ == '__main__':
    main()
