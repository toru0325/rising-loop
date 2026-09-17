#!/usr/bin/env python3
"""loops/index.html の画面（<section class="screen" id="s-XXX"> … </section>）を切り出す／差し替える。

  python3 splice-section.py extract loops/index.html s-L01 > loops/.tmp/s-L01.html
  python3 splice-section.py replace loops/index.html s-L01 loops/.tmp/s-L01.html
  python3 splice-section.py list    loops/index.html

「全ループ更新」で、ループごとの子エージェントが画面の断片を書き、親がここで差し戻す。
6つの子が同じ index.html を同時に書くと壊れるので、子は断片だけを書く（SKILL.md「数字を更新し、施策を再評価する」）。
依存なし。差し替えは断片の先頭と末尾が同じ <section id> / </section> であることを確かめてから行う。
"""
import re, sys

def bounds(html, sid):
    m = re.search(r'<section class="screen" id="%s">' % re.escape(sid), html)
    if not m:
        sys.exit('画面 %s が見つかりません' % sid)
    start = m.start()
    # 同じ深さの </section> を探す（screen の中に section は入れない前提だが、念のため入れ子を数える）
    depth = 0; i = start
    for t in re.finditer(r'<section\b|</section>', html[start:]):
        depth += 1 if t.group(0).startswith('<section') else -1
        if depth == 0:
            return start, start + t.end()
    sys.exit('画面 %s の </section> が見つかりません' % sid)

def main():
    if len(sys.argv) < 3: sys.exit(__doc__)
    cmd, path = sys.argv[1], sys.argv[2]
    html = open(path, encoding='utf-8').read()
    if cmd == 'list':
        print('\n'.join(re.findall(r'<section class="screen" id="([^"]+)">', html))); return
    sid = sys.argv[3]
    s, e = bounds(html, sid)
    if cmd == 'extract':
        sys.stdout.write(html[s:e] + '\n'); return
    if cmd == 'replace':
        frag = open(sys.argv[4], encoding='utf-8').read().strip()
        if not frag.startswith('<section class="screen" id="%s">' % sid) or not frag.endswith('</section>'):
            sys.exit('断片は <section class="screen" id="%s"> で始まり </section> で終わること' % sid)
        open(path, 'w', encoding='utf-8').write(html[:s] + frag + html[e:])
        print('差し替え: %s（%d → %d 文字）' % (sid, e - s, len(frag))); return
    sys.exit('extract / replace / list のどれか')

if __name__ == '__main__':
    main()
