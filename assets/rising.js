/* ═══════════════════════════════════════════════════════════════
   rising.js — 殻（index.html）とループ頁（LXX.html）の共通 JS

   1本のファイルを両方が読む。先頭の IS_SHELL で、自分がどちらかを見分ける。
     殻   : #loop-frame を持つ → 画面の切り替え・モーダル・トースト・コピー・右ペイン・使い方
     ループ頁 : 持たない       → ボタンを postMessage に変換・グラフの描画

   ★ このファイルは共通部品です。中身（ループ名・数字・パス）を書かないこと。
      値は殻の CONST ブロックと、頁の LOOP_DATA に置く。
   詳しくは ../references/HTML生成.md
   ═══════════════════════════════════════════════════════════════ */
var IS_SHELL = !!document.getElementById('loop-frame');

/* ───────── 共通 ───────── */
//=== 小数の目標（0.45円/人日 など）だと 0.26-0.28 が -0.020000000000000018 になる。
//=== 表示はここを通す。整数はそのまま（7 → "7"）、小数は2桁で丸める（0.02 → "0.02"）。
//=== 4桁以上は桁区切りを入れる（1000 → 1,000）。小数は2桁まで
function fmt(n){ return Number(+Number(n).toFixed(2)).toLocaleString('ja-JP', { maximumFractionDigits: 2 }); }

//=== 押されたボタンから data-* を素で読む。殻でも頁でも同じものを取り、
//===   「どう組み立てるか」は殻の doAction だけが知っている（加工は殻に一本化）
function pickAction(target){
  var el;
  if ((el = target.closest('.add-loop')))  return { kind:'add-loop', d:{} };
  if ((el = target.closest('[data-upd]'))) return { kind:'upd',  d:{ upd: el.getAttribute('data-upd') } };
  if ((el = target.closest('.ins')))       return { kind:'ins',  d:{ id: el.getAttribute('data-id'), text: el.getAttribute('data-text') } };
  if ((el = target.closest('.do')))        return { kind:'do',   d:{ id: el.getAttribute('data-id'), no: el.getAttribute('data-no'), text: el.getAttribute('data-text') } };
  if ((el = target.closest('.cmt')))       return { kind:'cmt',  d:{ id: el.getAttribute('data-id'), loop: el.getAttribute('data-loop'), sec: el.getAttribute('data-sec') } };
  if ((el = target.closest('[data-copy]')))return { kind:'copy', d:{ text: el.getAttribute('data-copy'), foot: el.getAttribute('data-foot') } };
  if ((el = target.closest('[data-go]')))  return { kind:'go',   d:{ id: el.getAttribute('data-go') } };
  return null;
}

/* ═══════════════════════════════════════════════════════════════
   殻（index.html）
   ═══════════════════════════════════════════════════════════════ */
if (IS_SHELL) (function(){
  var loopFrame = document.getElementById('loop-frame');

  /* ── 定数ブロック（index.html の CONST）から画面に埋める ── */
  //=== ★ベタ書きしない。ここが唯一の差し込み口
  var SERVICE = (typeof SERVICE_NAME === 'string' && SERVICE_NAME) ? SERVICE_NAME : '（サービス名）';
  var PDIR    = (typeof PROJECT_DIR === 'string' && PROJECT_DIR) ? PROJECT_DIR : '/絶対パス/プロジェクト';
  //=== ★PANES は右ペイン専用。どの画面にセッションを立てるかだけを決める。
  //===   画面の切り替え（show）は一覧の行そのもの（[data-go]）を見る。二重管理にしない
  var PANE_IDS= (typeof PANES !== 'undefined' && PANES) ? PANES : ['s-list'];
  var PANE_OK = {}; PANE_IDS.forEach(function(p){ PANE_OK[p] = true; }); PANE_OK['s-list'] = true;
  document.title = 'ライジング・ループ — ' + SERVICE;
  var listTitle = document.querySelector('#s-list h1.goal-name');
  if (listTitle) listTitle.textContent = SERVICE + 'ライジング・ループ';
  //=== #cc-help の起動コマンド。文言（claude / codex）は data-cmd に置いてある
  Array.prototype.forEach.call(document.querySelectorAll('#cc-help .h-cmd'), function(b){
    var cmd = 'sh ' + PDIR + '/loops/chat-pane.sh ' + b.getAttribute('data-cmd');
    b.setAttribute('data-copy', cmd);
    var code = b.querySelector('code'); if (code) code.textContent = cmd;
  });

  /* ── トースト ── */
  var toast=document.getElementById('toast'), toastBody=document.getElementById('toast-body'), toastT;
  function showToast(text, ok, foot){
    toast.classList.toggle('err', !ok);
    toast.querySelector('.t-head').textContent = ok ? 'COPIED' : 'コピーできませんでした';
    //=== foot は貼り先の案内。既定はチャット、右ペインの起動コマンドだけターミナル
    //=== ★貼り先がチャットなら、右ペインを開いて矢印で指す（右ペインの起動コマンドだけは foot が来るので開かない）
    var toChat = ok && !foot;
    toast.querySelector('.t-foot-text').textContent = ok ? (foot || '右のチャットに貼って Enter（⌘V → Enter）') : '下の文をコピーして、AIに伝えてください。';
    toast.classList.toggle('to-chat', toChat);
    if(toChat && window.LOOP_OPEN_PANE) window.LOOP_OPEN_PANE();
    toastBody.textContent = text;
    toast.classList.add('on');
    clearTimeout(toastT);
    toastT = setTimeout(function(){ toast.classList.remove('on'); }, ok ? (toChat ? 7000 : 4200) : 9000);
  }
  toast.addEventListener('click', function(e){ e.stopPropagation(); toast.classList.remove('on'); clearTimeout(toastT); });

  /* ── コピー ── */
  //=== ★ iframe 内のクリックによる user activation は親フレームに伝わるので、
  //===   「頁クリック → postMessage → 殻が writeText」は仕様上通る。
  //===   通らない環境のために legacyCopy を残す
  function copyText(text, foot){
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(function(){ showToast(text,true,foot); },
                                              function(){ legacyCopy(text,foot); });
    } else { legacyCopy(text,foot); }
  }
  function legacyCopy(text, foot){
    try{
      var ta=document.createElement('textarea');
      ta.value=text; ta.setAttribute('readonly','');
      ta.style.cssText='position:fixed;top:0;left:0;opacity:0';
      document.body.appendChild(ta); ta.select();
      var ok=document.execCommand('copy');
      document.body.removeChild(ta);
      showToast(text, ok, foot);
    }catch(e){ showToast(text,false,foot); }
  }

  /* ── 画面の切り替え ── */
  //=== 一覧は殻の中にある。ループは loop-frame に LXX.html を出す。
  //===   ★差し替えは常に contentWindow.location.replace。src 代入は殻の履歴に積まれ、
  //===     戻るボタンで iframe だけ戻って hash とずれる（初回も同じ。Safari で実際に起きた）
  //===   ★履歴は殻の hash 代入だけ。同じ id なら再読込しない
  //=== loaded は「いま loop-frame に入っている頁」。一覧に戻っても忘れない
  //===   （忘れると L01 → 一覧 → L01 で読み直しになる）
  var listScreen = document.getElementById('s-list'), loaded = null;
  //=== 行けるのは「一覧」と「一覧に行がある画面」だけ。PANES は見ない（右ペイン専用）
  function knownId(id){ return id === 's-list' || !!document.querySelector('[data-go="' + id + '"]'); }
  function show(id){
    if (!knownId(id)){
      //=== 知らない #hash は一覧に丸める。hash も揃えないと戻る／再読込で同じ所に戻ってしまう
      id = 's-list';
      if (location.hash !== '#s-list') {
        location.replace(location.pathname + location.search + '#s-list');
        return;                                 //=== hashchange で show('s-list') が来る
      }
    }
    if (id === 's-list'){
      document.body.classList.remove('in-loop');
      if (listScreen) listScreen.classList.add('active');
    } else {
      if (listScreen) listScreen.classList.remove('active');
      document.body.classList.add('in-loop');
      if (loaded !== id){
        //=== ★相対のまま渡すと、iframe の現在地（about:blank 等）を基準にされることがある。
        //===   殻の URL を基準に絶対化して渡す
        loopFrame.contentWindow.location.replace(new URL(id.replace('s-', '') + '.html', location.href).href);
        loaded = id;
      }
    }
    //=== ★幅が変わるので、殻に図があれば描き直す（いまは頁側が持っている）
    (window.LOOP_REDRAWS || []).forEach(function(f){ f(); });
    if (window.CC_SYNC) window.CC_SYNC();
  }

  /* ── モーダル ── */
  var modal=document.getElementById('modal'), mInput=document.getElementById('m-input');
  var mTitle=document.getElementById('m-title'), mSub=document.getElementById('m-sub');
  var PH_CMT='このセクションへのフィードバックをどうぞ。';
  var PH_DO='これを TRIAL に移して手順を出して（実装はしない）／これは消して／この認識は違う、など。そのままどうぞ。';
  var cur=null;
  function openModal(cfg){
    cur=cfg;
    modal.querySelector('.m-kick').textContent = cfg.kick;
    mTitle.textContent = cfg.title;
    mSub.textContent = cfg.sub || '';
    mInput.placeholder = cfg.ph;
    //=== 定型の札。指示のときだけ。施策案は「TRIAL に移す」（本文は「これを TRIAL に移して手順を出して（実装はしない）」）、TRIAL は「完了にして（評価に移す）」が先頭
    var chips = document.getElementById('m-chips'); chips.innerHTML = '';
    (cfg.chips || []).forEach(function(c){
      var b = document.createElement('button'); b.type = 'button'; b.setAttribute('data-chip', c[1]); b.textContent = c[0]; chips.appendChild(b);
    });
    chips.hidden = !(cfg.chips && cfg.chips.length);
    mInput.value=''; modal.classList.add('on');
    setTimeout(function(){ mInput.focus(); }, 30);
  }
  function closeModal(){ modal.classList.remove('on'); }
  function submitModal(){
    var v=mInput.value.trim();
    if(!v){ mInput.focus(); return; }
    var text = cur.compose(v);
    closeModal();
    copyText(text);
  }
  document.getElementById('m-ok').addEventListener('click', submitModal);
  document.getElementById('m-chips').addEventListener('click', function(e){
    var c = e.target.closest('[data-chip]'); if(!c) return;
    mInput.value = c.getAttribute('data-chip'); mInput.focus();   //=== 入れるだけ。送信はしない
  });
  document.getElementById('m-cancel').addEventListener('click', closeModal);
  // ★ドラッグで閉じないようにする。click は mousedown と mouseup の共通祖先で発火するため、
  //   テキストエリアで押して背景で離すと e.target が背景になり、誤って閉じてしまう。
  //   押した場所も背景だったときだけ閉じる。
  var downTarget = null;
  modal.addEventListener('pointerdown', function(e){ downTarget = e.target; });
  modal.addEventListener('click', function(e){
    if(e.target === modal && downTarget === modal) closeModal();
    downTarget = null;
  });
  mInput.addEventListener('keydown', function(e){
    if((e.metaKey||e.ctrlKey) && e.key==='Enter') submitModal();
  });
  document.addEventListener('keydown', function(e){
    if(e.key==='Escape' && modal.classList.contains('on')) closeModal();
  });

  /* ── 指示文の組み立て。殻に1つだけ置く（用途が増えても分岐が増えない） ── */
  //=== コピーする文言は、貼った先で読める形に固定する。
  //===   ★ target は「その項目についての指示」のときだけ出す。セクションへのコメントには出さない
  //===     （画面ぜんたいを見て言っているのに、勝手に対象を狭めないため）
  var SEC = { 'ゴール':'GOAL', 'ボトルネック':'BOTTLENECK', '施策の実行':'TRIAL',
              '施策の評価':'RECORD', 'ループ一覧':'LOOPS' };
  function kickOf(sec){
    for (var k in SEC) if (sec && sec.indexOf(k) === 0) return SEC[k];
    return sec || '';
  }
  function block(loop, sec, target, v, key){
    var s = '---\nloop: ' + (loop || '') + '\nsection: ' + sec + '\n';
    if (target) s += 'target: ' + target + '\n';
    s += 'rule: まず /rising-loop を呼び出して最新の手順を読み、それに従うこと\n' + (key || 'feedback') + ': |\n';
    s += String(v || '').split('\n').map(function(x){ return '  ' + x; }).join('\n');
    return s + '\n---';
  }
  //=== 更新ボタン。人の言葉ではなく命令なので task: にする
  //===   ★手順は書かない。rule: 行で SKILL.md の「数字を更新し、施策を再評価する」に乗る。
  //===   ここに写すと二重持ちになり、スキルを直したときにこちらが古いまま残る
  var TASK = { all: 'loops/ の全ループを更新して', one: 'このループを更新して' };

  //=== 殻の中のクリックも、ループ頁からの postMessage も、ここに集まる。
  //===   受け取るのは生の data-*（d）だけ。加工はここでしかしない
  function doAction(kind, d){
    d = d || {};
    if (kind === 'add-loop'){
      openModal({ kick:'INSTRUCTION', title:'ループを追加', sub:'どんな数字を上げたいですか。ひとことで', ph:'例: 申し込みを増やしたい',
        chips:[['申し込みを増やしたい','申し込みを増やしたい'],['見込み客を増やしたい','見込み客を増やしたい'],['翌日また来る人を増やしたい','翌日また来る人を増やしたい'],['有料に切り替える人を増やしたい','有料に切り替える人を増やしたい'],['解約を減らしたい','解約を減らしたい'],['TOEIC の点を上げたい','TOEIC の点を上げたい'],['YouTube の登録者を増やしたい','YouTube の登録者を増やしたい'],['株の含み益を増やしたい','株の含み益を増やしたい'],['体重を落としたい','体重を落としたい'],['貯金を毎月積みたい','貯金を毎月積みたい']],
        compose:function(v){ return block('', 'LOOPS', '', 'ループを追加して: ' + v, 'task'); } });
      return;
    }
    if (kind === 'upd'){
      var ul = d.upd;
      copyText(block(ul, ul === 'all' ? 'ALL' : 'GOAL', '', ul === 'all' ? TASK.all : TASK.one, 'task'));
      return;
    }
    if (kind === 'ins'){
      var iid = d.id, itx = d.text;
      openModal({ kick:'INSTRUCTION', title:'施策について', sub:itx, ph:PH_DO,
        chips:[['完了にして（評価に移す）','完了にして（評価に移す）'],['これは消して','これは消して'],['この認識は違う','この認識は違う。']],
        compose:function(v){ return block(iid, 'TRIAL', itx, v); } });
      return;
    }
    if (kind === 'do'){
      var did = d.id, dno = d.no, dtx = d.text;
      openModal({ kick:'INSTRUCTION', title:'施策案 '+dno+'について', sub:dtx, ph:PH_DO,
        chips:[['TRIAL に移す','これを TRIAL に移して手順を出して（実装はしない）'],['これは消して','これは消して'],['この認識は違う','この認識は違う。']],
        compose:function(v){ return block(did, 'BOTTLENECK', dtx, v); } });
      return;
    }
    if (kind === 'cmt'){
      var cid = d.id, clp = d.loop, csec = d.sec;
      //=== 施策の評価「◯◯」のときだけ、◯◯ を target にする
      var mt = csec && csec.match(/「(.+)」$/);
      openModal({ kick:'COMMENT', title:csec+'について', sub:(clp===csec?'':clp), ph:PH_CMT,
        compose:function(v){ return block(cid, kickOf(csec), mt ? mt[1] : '', v); } });
      return;
    }
    if (kind === 'copy'){ copyText(d.text, d.foot); return; }
    if (kind === 'go'){ location.hash = d.id; return; }
  }

  document.addEventListener('click', function(e){
    var a = pickAction(e.target);
    if (!a) return;
    e.preventDefault(); e.stopPropagation();
    doAction(a.kind, a.d);
  });

  /* ── ループ頁からのメッセージ ── */
  //=== ★ targetOrigin は '*'（Safari は file:// を毎回別のオリジンにする）。
  //===   送信元は event.source で見る。event.origin は見ない
  window.addEventListener('message', function(e){
    if (!loopFrame.contentWindow || e.source !== loopFrame.contentWindow) return;
    var m = e.data || {};
    if (m.t === 'go')   { doAction('go', { id: m.id }); return; }
    if (m.t === 'copy' || m.t === 'modal') { doAction(m.kind, m.d); return; }
  });

  /* ── hash ── */
  window.addEventListener('hashchange', function(){
    show(location.hash.replace('#','') || 's-list');
  });

  /* ── 右ペイン（ttyd を iframe で出すだけ。ここでは入力を受けない） ── */
  (function(){
    var pane = document.getElementById('cc'), btn = document.getElementById('cc-toggle'),
        stack = pane.querySelector('.cc-stack'),
        //=== ★encodeURIComponent は必須。`+` はクエリ文字列で空白に化けるので %2B にして渡す
        BASE = 'http://localhost:7681/?arg=' + encodeURIComponent(PDIR) + '&arg=';
    var frames = {};                            //=== 画面ID -> iframe。一度作ったら捨てない
    function sync(){
      if(!document.body.classList.contains('pane-on')) return;
      var id = (location.hash || '#s-list').replace('#','');
      if(!PANE_OK[id]) id = 's-list';
      if(!frames[id]){                          //=== 初めて開く画面だけ繋ぐ（ここが10秒）
        var f = document.createElement('iframe');
        f.title = 'Claude Code'; f.setAttribute('allow', 'fullscreen');
        //=== 渡すのは2つだけ: プロジェクトのパス / 画面ID。
        //===   どの AI を出すかは、ターミナルで chat-pane.sh に渡した引数で決まる
        f.src = BASE + id;
        stack.appendChild(f);
        frames[id] = f;
      }
      //=== ★src は二度と触らない。触ると接続が切れて最初からやり直しになる
      for(var k in frames) frames[k].classList.toggle('on', k === id);
    }
    window.CC_SYNC = sync;
    function set(on){
      document.body.classList.toggle('pane-on', on);
      btn.textContent = on ? 'AI ▸' : 'AI ◂';
      if(on) sync();                            //=== 開くまで繋ぎに行かない
      //=== ★ペインの開閉は padding-right が変わるだけで resize が飛ばない。
      //===   実寸で描いている図が古い幅のまま残るので、ここで描き直す
      //===   （ループ頁の図は、iframe の幅が変わるので頁の中の resize で描き直される）
      (window.LOOP_REDRAWS || []).forEach(function(f){ f(); });
      try{ localStorage.setItem('cc-pane', on ? '1' : '0'); }catch(e){}
    }
    var saved = null; try{ saved = localStorage.getItem('cc-pane'); }catch(e){}
    set(saved !== '0');                         //=== 既定は開く
    btn.addEventListener('click', function(){ set(!document.body.classList.contains('pane-on')); });
    window.LOOP_OPEN_PANE = function(){ if(!document.body.classList.contains('pane-on')) set(true); };

    //=== 「この画面の使い方」。初回だけ自動で開く（既読は localStorage。読めない環境では自動で開かない側に倒す）
    var howto = document.getElementById('howto');
    function howtoOn(on){ howto.classList.toggle('on', on); if(!on){ try{ localStorage.setItem('howto-seen','1'); }catch(e){} } }
    document.getElementById('howto-btn').addEventListener('click', function(){ howtoOn(true); });
    document.getElementById('howto-close').addEventListener('click', function(){ howtoOn(false); });
    howto.addEventListener('click', function(e){ if(e.target === howto) howtoOn(false); });
    document.addEventListener('keydown', function(e){ if(e.key === 'Escape' && howto.classList.contains('on')) howtoOn(false); });
    try{ if(localStorage.getItem('howto-seen') !== '1') howtoOn(true); }catch(e){}
    window.addEventListener('hashchange', sync);

    //=== 「15秒たってもチャットが出ない？」の説明。コピー自体は [data-copy] の共通処理に任せる。
    //===   ★トースト(z-index 96)はこのダイアログ(97)より下なので、押したら先に閉じる
    var help = document.getElementById('cc-help');
    function helpOn(on){ help.classList.toggle('on', on); }
    document.getElementById('cc-ask').addEventListener('click', function(){ helpOn(true); });
    document.getElementById('cc-help-close').addEventListener('click', function(){ helpOn(false); });
    help.addEventListener('click', function(e){
      if(e.target === help || e.target.closest('.h-cmd')) helpOn(false);
    });
    document.addEventListener('keydown', function(e){
      if(e.key === 'Escape' && help.classList.contains('on')) helpOn(false);
    });
  })();

  //=== 最初の1回。hashchange は飛ばないので直に呼ぶ
  show(location.hash.replace('#','') || 's-list');
})();

/* ═══════════════════════════════════════════════════════════════
   ループ頁（LXX.html）
   ═══════════════════════════════════════════════════════════════ */
if (!IS_SHELL) (function(){
  var screen = document.querySelector('.screen');
  if (screen) screen.classList.add('active');   //=== 頁には1枚しか無いので必ず出す
  var STANDALONE = (window.parent === window);

  //=== 単体で開かれたとき。壊れないことだけ保証する（トーストもモーダルも殻にある）
  if (STANDALONE){
    var note = document.createElement('div');
    note.className = 'standalone-note';
    note.innerHTML = 'この頁は <a href="index.html">index.html</a> から開いてください。'
                   + '（単体で開いているので、ボタンは押しても何も起きません）';
    document.body.insertBefore(note, document.body.firstChild);
  }

  /* ── ボタンは「押されたら殻に頼む」だけ。生の data-* をそのまま送る ── */
  //=== ★ targetOrigin は '*' 一択。Safari は file:// を毎回別のオリジンにする
  function send(m){ window.parent.postMessage(m, '*'); }
  document.addEventListener('click', function(e){
    var a = pickAction(e.target);
    if (!a) return;
    e.preventDefault(); e.stopPropagation();
    if (STANDALONE) return;                     //=== 単体表示では何もしない
    if (a.kind === 'go')   { send({ t:'go', id: a.d.id }); return; }
    if (a.kind === 'upd' || a.kind === 'copy'){ send({ t:'copy', kind:a.kind, d:a.d }); return; }
    send({ t:'modal', kind:a.kind, d:a.d });    //=== add-loop / ins / do / cmt
  });

  /* ── グラフ。この頁のぶんだけ（LOOP_DATA.hist / LOOP_DATA.funnel） ── */
  var DATA = (typeof LOOP_DATA !== 'undefined' && LOOP_DATA) ? LOOP_DATA : {};

  /* ── GOAL の履歴（折れ線＋棒） ── */
  (function(){
    //=== 折れ線。ファネルと同じく D3 で描く（描画の仕方をこのファイルで1通りに揃えている）。
    //===   ★実寸で描くので viewBox の引き伸ばしをしない。丸が楕円に歪まず、目標ラベルも SVG に置ける。
    //===   D3 が読めなかったときは何も描かない（数字は上のゲージと記録に出ている）。
    function drawChart(el, pts, target, unit, cur, days, dayUnit, dayTarget, dayTargetUnit, dual, line, tlabel){
      //=== ★幅を先に見る。幅ゼロ（非表示中）で消すと、描き直しが来るまで図が空になる。
      //===   drawFunnel と同じ順（見られる状態か確かめてから消す）
      var W = el.clientWidth;
      if (!W || !window.d3) return;
      el.innerHTML = '';
      var H = 96, PAD = 10, PAD_R = 78;                       //=== 右は「目標」ラベルのぶん空ける
      //=== 日ごとの数字を持っているループは、棒＋折れ線で描く（下の drawBars）。
      //===   持っていないループはこれまでどおり折れ線だけ。
      if (days && days.length) return drawBars(el, pts, target, unit, cur, days, W, dayUnit, dayTarget, dayTargetUnit, dual, line, tlabel);
      var vals = pts.map(function(p){ return p.value; }).concat([target, 0]);
      var y = d3.scaleLinear()
        .domain([d3.min(vals), d3.max(vals)])
        .range([H - PAD, PAD]);
      var x = d3.scaleLinear()
        .domain([0, Math.max(1, pts.length - 1)])
        .range([PAD, pts.length < 2 ? W / 2 : W - PAD_R]);

      var svg = d3.select(el).append('svg').attr('width', W).attr('height', H);
      drawTarget(svg, W, PAD_R, y(target), target, unit, tlabel);

      if (pts.length > 1) {
        svg.append('path')
          .attr('fill', 'none').attr('stroke', '#52751f').attr('stroke-width', 2)
          .attr('d', d3.line().x(function(p, i){ return x(i); }).y(function(p){ return y(p.value); })(pts));
      }
      svg.selectAll('circle').data(pts).enter().append('circle')
        .attr('cx', function(p, i){ return x(i); })
        .attr('cy', function(p){ return y(p.value); })
        .attr('r', function(p, i){ return i === cur ? 5 : 3.5; })
        .attr('fill', function(p, i){ return i === cur ? '#52751f' : '#a8b3a4'; });
    }

    //=== 目標の破線と、その正体を書くラベル（折れ線でも棒でも同じ見た目にする）
    //===   ★下げたいループ（コストなど）は LOOP_DATA.hist に targetLabel: '上限' を置く。既定は「目標」
    //=== 目標がグラフの外にあるとき。★線は引かない。
    //===   上端に破線を引くと「上端＝目標」に見えて、距離を読みちがえる。
    //===   どれだけ離れているかはゲージ（value / target）が持っているので、ここは在りかだけ示す。
    function drawTargetOff(svg, W, PAD_T, target, unit, tlabel){
      svg.append('text').attr('x', W).attr('y', PAD_T - 5).attr('text-anchor', 'end')
        .attr('font-family', 'ui-monospace,SFMono-Regular,Menlo,monospace')
        .attr('font-size', 12).attr('fill', '#87918b')
        .text('↑ ' + (tlabel || '目標') + ' ' + fmt(target) + unit + '（グラフの外）');
    }

    function drawTarget(svg, W, PAD_R, ty, target, unit, tlabel){
      svg.append('line').attr('x1', 0).attr('x2', W - PAD_R + 6)
        .attr('y1', ty).attr('y2', ty)
        .attr('stroke', '#cbd2cb').attr('stroke-dasharray', '4 4').attr('stroke-width', 1);
      svg.append('text').attr('x', W).attr('y', ty + 4).attr('text-anchor', 'end')
        .attr('font-family', 'ui-monospace,SFMono-Regular,Menlo,monospace')
        .attr('font-size', 12).attr('fill', '#87918b')
        .text((tlabel || '目標') + ' ' + fmt(target) + unit);
    }

    //=== 棒＝その日の数字 ／ 折れ線＝計測点（その窓の最終日の位置に置く）。
    //===   ★折れ線だけだと 44→37→37→39 が 0〜60 の縦軸の中で潰れて水平線に見える。
    //===     棒を下敷きにすると 0 からの高さが出て、日ごとの動きも同じ絵で読める。
    //===   ★3案を並べて比べたモックは docs/260904_UIモック-計測グラフ案.html（A案を採用）
    //=== ★棒が「1日ぶんの実額」で、ゴールが月額のときは、目標線と折れ線も1日ぶんに直す
    //===   （dayTarget と各点の dayValue）。棒だけ月換算にすると「6470円」のような
    //===   実在しない額が並んで読めなくなる（2026-09-05 のフィードバック）。
    function drawBars(el, pts, target, unit, cur, days, W, dayUnit, dayTarget, dayTargetUnit, dual, line, tlabel){
      if (dayTarget != null) { target = dayTarget; unit = dayTargetUnit || unit; }
      var H = 150, PAD_T = 18, PAD_B = 22, PAD_L = 4, PAD_R = 78;
      var svg = d3.select(el).append('svg').attr('width', W).attr('height', H);
      //=== ★縦軸の上端は max(目標, 実測)。目標で切ると、目標を超えた日が
      //===   グラフの外に出て見えなくなる。
      //=== ★ただし目標が実測の5倍を超えるときは、この規則が逆に働く。
      //===   棒が高さ12%まで潰れて、日ごとの動きが読めなくなる（2026-09-10 に実際に起きた）。
      //===   そのときは縦軸をデータに合わせ、目標は「グラフの外」と文字で出す（線は引かない）。
      var dataMax = d3.max(
        days.map(function(d){ return d.v; }).concat(
        (line && line.length) ? line.map(function(q){ return q.v; })
                              : pts.map(function(p){ return p.dayValue != null ? p.dayValue : p.value; })));
      var farTarget = target > dataMax * 5;
      var top = farTarget ? dataMax * 1.15 : d3.max([target, dataMax]);
      var y = d3.scaleLinear().domain([0, top]).range([H - PAD_B, PAD_T]);
      //=== ★dual: 棒（その日の実額）と折れ線（ゴールの数字＝過去30日の合計）で桁が違うとき、
      //===   縦軸を分ける。1本にすると、目標がはるか上にあるぶん**棒も線もぺたんこ**になって
      //===   何も読めない（2026-09-05 に実際にそうなった）。
      var yBar = y, yLine = y, lo = 0, hi = 0;
      if (dual) {
        yBar = d3.scaleLinear()
          .domain([0, d3.max(days.map(function(d){ return d.v; }))])
          .range([H - PAD_B, PAD_T + 26]);
        //=== ★線の縦軸は「実際に描く系列」から取る。line を持つループで pts から取ると、
        //===   計測点が1つしか無いとき domain が潰れて、線がグラフの外へ飛ぶ（2026-09-14）
        var inWin = {}; days.forEach(function(q){ inWin[q.d] = 1; });
        var lvals = (line && line.length)
          ? line.filter(function(q){ return inWin[q.d]; }).map(function(q){ return q.v; })
          : pts.map(function(p){ return p.value; });
        lo = d3.min(lvals);
        hi = d3.max(lvals);
        yLine = d3.scaleLinear()
          .domain([lo - (hi - lo || 1) * 0.8, hi + (hi - lo || 1) * 0.3])
          .range([H - PAD_B, PAD_T]);
      }
      var x = d3.scaleBand().domain(days.map(function(d){ return d.d; }))
        .range([PAD_L, W - PAD_R]).padding(0.34);

      //=== 小数の混ざる系列（0.10円）は桁を揃える。fmt だと 0.10 が "0.1" になって並びが乱れる
      var frac = days.some(function(d){ return d.v % 1 !== 0; });
      var dfmt = function(v){ return frac ? v.toFixed(2) : String(v); };

      if (!dual) {
        if (farTarget) drawTargetOff(svg, W, PAD_T, target, unit, tlabel);
        else drawTarget(svg, W, PAD_R, y(target), target, unit, tlabel);
      }

      svg.selectAll('rect').data(days).enter().append('rect')
        .attr('x', function(d){ return x(d.d); }).attr('width', x.bandwidth())
        .attr('y', function(d){ return yBar(d.v); })
        .attr('height', function(d){ return Math.max(0, yBar(0) - yBar(d.v)); })
        //=== 途中の日（partial）は薄くするだけ。印や注記は付けない（毎日見る人には分かる）
        .attr('fill', function(d){ return d.partial ? '#e1e9cf' : '#c3d29b'; });
      //=== 数字は棒の内側に深めに置く。棒のすぐ上や浅い位置だと折れ線とぶつかる
      //===   （棒と線は近い値なので必ず近くを通る）。低い棒のときだけ棒の上に出す。
      var tall = function(d){ return yBar(0) - yBar(d.v) >= 34; };
      svg.selectAll('text.bv').data(days).enter().append('text').attr('class', 'bv')
        .attr('x', function(d){ return x(d.d) + x.bandwidth() / 2; })
        .attr('y', function(d){ return tall(d) ? yBar(d.v) + 26 : yBar(d.v) - 6; })
        .attr('text-anchor', 'middle').attr('font-size', 11)
        .attr('fill', function(d){ return tall(d) ? '#4c5b3c' : '#87918b'; })
        .attr('font-family', 'ui-monospace,SFMono-Regular,Menlo,monospace')
        .text(function(d){ return dfmt(d.v) + (dayUnit || ''); });

      //=== 計測点。棒に無い日（＝この窓より後の計測）は描かない
      //=== 同じ窓を取り直した点は同じ日に重なり、線が縦になる。選んでいる点を優先し、
      //===   それ以外は新しいほうだけを描く（2026-09-08 のフィードバック）。
      //=== 折れ線は「その日に計測していたらいくつだったか」を日ごとに描く（LOOP_DATA.hist の line）。
      //===   ★単位はゴールの単位のまま。line を持たないループは計測点をつなぐ。
      var seen = [];
      if (line && line.length) {
        line.forEach(function(q){
          var b = x(q.d);
          if (b === undefined) return;
          seen.push({ v: q.v, cur: false, cx: b + x.bandwidth() / 2 });
        });
        if (seen.length) seen[seen.length - 1].cur = true;
      } else {
        var byEnd = {};
        pts.forEach(function(p, i){
          var b = x(p.end);
          if (b === undefined) return;
          var s = { v: p.dayValue != null ? p.dayValue : p.value, cur: i === cur, cx: b + x.bandwidth() / 2 };
          if (byEnd[p.end] != null) {
            if (seen[byEnd[p.end]].cur) return;
            seen[byEnd[p.end]] = s;
          } else { byEnd[p.end] = seen.length; seen.push(s); }
        });
      }
      if (seen.length > 1) {
        svg.append('path').attr('fill', 'none').attr('stroke', '#52751f').attr('stroke-width', 2)
          .attr('d', d3.line().x(function(s){ return s.cx; }).y(function(s){ return yLine(s.v); })(seen));
      }
      svg.selectAll('circle').data(seen).enter().append('circle')
        .attr('cx', function(s){ return s.cx; }).attr('cy', function(s){ return yLine(s.v); })
        .attr('r', function(s){ return s.cur ? 5 : 3.5; })
        .attr('fill', function(s){ return s.cur ? '#52751f' : '#a8b3a4'; });

      //=== dual のときは軸が2本あるので、線の高さは目盛りでは読めない。最新の点に数字を添える。
      if (dual && seen.length) {
        var last = seen[seen.length - 1];
        svg.append('text').attr('x', last.cx - 8).attr('y', yLine(last.v) - 9)
          .attr('text-anchor', 'end').attr('font-size', 11).attr('fill', '#4c5b3c')
          .attr('font-family', 'ui-monospace,SFMono-Regular,Menlo,monospace')
          .text('合計 ' + fmt(last.v) + (unit || ''));
      }
      svg.selectAll('text.xl').data(days).enter().append('text').attr('class', 'xl')
        .attr('x', function(d){ return x(d.d) + x.bandwidth() / 2; }).attr('y', H - 6)
        .attr('text-anchor', 'middle').attr('font-size', 11).attr('fill', '#87918b')
        .attr('font-family', 'ui-monospace,SFMono-Regular,Menlo,monospace')
        .text(function(d){ return d.d; });
    }

    //=== 選んだ計測点の窓の最終日までで棒を切る（レポートを畳むのと同じ理屈で、
    //===   過去の点に戻したときにグラフだけ最新のままにしない）。並べるのは直近10本まで。
    function daysFor(d, p){
      if (!d.days || !d.days.length) return null;
      var k = -1;
      d.days.forEach(function(x, i){ if (x.d === p.end) k = i; });
      var ls = k < 0 ? d.days : d.days.slice(0, k + 1);
      //=== 窓の後ろにある途中の日（partial）も並べる
      if (k >= 0) ls = ls.concat(d.days.slice(k + 1).filter(function(x){ return x.partial; }));
      return ls.slice(-10);
    }

    function recList(head, rows){
      if (!rows || !rows.length) return "";
      return '<div class="hr-head">'+head+'</div><ul>' +
        rows.map(function(r){ return '<li><b>'+r[0]+'</b><span>'+r[1]+'</span></li>'; }).join("") + '</ul>';
    }

    var box = document.querySelector('[data-hist]');
    var d = DATA.hist;
    if (!box || !d) return;
    var id = box.getAttribute('data-hist');
    var cur = d.points.length - 1;
    var elNote = box.querySelector(".hist-note"), elChart = box.querySelector(".hist-chart"),
        elRecs = box.querySelector(".hist-recs"),
        elReport = box.querySelector(".hist-report"),
        elWhen = document.querySelector('[data-goal-when="'+id+'"]'),
        elNow = document.querySelector('[data-goal-now="'+id+'"]'),
        elFill = document.querySelector('[data-goal-fill="'+id+'"]'),
        elDiff = document.querySelector('[data-goal-diff="'+id+'"]'),
        elMoney = document.querySelector('[data-goal-money="'+id+'"]');
    function render(){
      var p = d.points[cur];
      //=== 日付と値は上のゲージが持っている。ここに出すと同じことを2回言うことになる
      elNote.textContent = p.note || "";
      //=== ⚠️ 注意書きは innerHTML の中に入れる。afterend で足すと render のたびに増える
      drawChart(elChart, d.points, d.target, d.unit, cur, daysFor(d, p), d.dayUnit, d.dayTarget, d.dayTargetUnit, d.dualAxis, d.line, d.targetLabel);
      var head = cur === 0 ? "この計測までに入ったこと" : "前の計測から、この計測までに入ったこと";
      elRecs.innerHTML = recList(head, p.recs) +
        recList("この計測のあとに入ったこと（次の計測で判定に使う）", d.after);
      //=== ★上のゲージも選んだ時点に合わせる。ここが動かないと「遡れた」ことにならない。
      if (elNow) elNow.textContent = fmt(p.value);
      //=== 単価を持つループは、金額の下に枚数を添える（1枚250円）
      if (elMoney && d.price) elMoney.textContent = Math.round(p.value / d.price) + '件';
      if (elFill) elFill.style.width = Math.max(0, Math.min(100, p.value / d.target * 100)) + "%";
      if (elDiff) {
        if (cur === 0) { elDiff.textContent = "はじめて取った日"; }
        else {
          var prev = d.points[cur-1], diff = p.value - prev.value;
          elDiff.textContent = prev.label.replace("月","/").replace("日","") + " → " +
            p.label.replace("月","/").replace("日","") + " で " + (diff > 0 ? "＋" : diff < 0 ? "−" : "±") + fmt(Math.abs(diff));
        }
      }
      //=== レポートは「いまの数字の内訳」。常に最新の1窓ぶんだけを出す
      if (elReport) elReport.hidden = false;
      //=== 大きい数字の上は「いま」ではなく、その計測日にする
      if (elWhen) elWhen.textContent = p.label;
    }
    render();
    //=== 幅の変化で描き直す（実寸で描いているので必要）
    (window.LOOP_REDRAWS = window.LOOP_REDRAWS || []).push(render);
  })();

  /* ── 横向きファネル ── */
  (function(){
    //=== 高さは値の**対数**。実数だと先頭と末尾で桁が違い、末尾が線になって消えるため。
    var SEQ = ['#7d9a4e', '#a0a84a', '#c08a2e', '#b06b25', '#8f4a3a'];
    var CSSV = getComputedStyle(document.documentElement);
    var V = function(n){ return CSSV.getPropertyValue(n).trim(); };
    var FONT = getComputedStyle(document.body).fontFamily;

    function drawFunnel(box, d){
      var st = d.stages, n = st.length;
      var rate = st.map(function(s,i){ return i === 0 ? null : Math.round(s.value / st[i-1].value * 100); });
      var label = function(i){ return st[i].value + st[i].unit; };

      //=== D3 が読めなかったとき（オフライン等）。数字だけは必ず出す
      if (!window.d3) {
        box.innerHTML = '<div class="fallback">' + st.map(function(s,i){
          return '<span>' + s.name + '<b>' + label(i) + '</b>' +
                 (rate[i] === null ? '' : ' <span style="font-size:12px">(' + rate[i] + '%)</span>') + '</span>';
        }).join('') + '</div>';
        return;
      }

      var W = box.clientWidth;
      if (!W) return;
      var narrow = W < 560;
      var H = narrow ? 210 : 250, mL = 34, mR = 34, mT = 46, mB = 44;
      var iw = W - mL - mR, ih = H - mT - mB, cy = mT + ih / 2;
      box.innerHTML = '';
      var svg = d3.select(box).append('svg').attr('width', W).attr('height', H);

      var lg = function(v){ return Math.log10(v + 1); };
      var hMax = lg(st[0].value);
      var h = st.map(function(s){ return Math.max(6, ih * lg(s.value) / hMax); });
      var X = st.map(function(_, i){ return mL + iw * i / (n - 1); });

      //=== 段のあいだを台形でつなぐ。中央に通過率
      for (var i = 0; i < n - 1; i++) {
        svg.append('polygon')
          .attr('points', [
            [X[i], cy - h[i]/2], [X[i+1], cy - h[i+1]/2],
            [X[i+1], cy + h[i+1]/2], [X[i], cy + h[i]/2]
          ].join(' '))
          .attr('fill', SEQ[i % SEQ.length]);
        svg.append('text')
          .attr('x', (X[i] + X[i+1]) / 2).attr('y', cy + 4).attr('text-anchor', 'middle')
          .attr('font-size', narrow ? 11 : 13).attr('font-weight', 600)
          .attr('fill', '#fff').attr('font-family', FONT)
          .text(rate[i+1] + '%');
      }
      //=== 境目の縦線と、上に段名・下に値
      st.forEach(function(s, i){
        var anc = i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle';
        svg.append('line').attr('x1', X[i]).attr('x2', X[i])
          .attr('y1', cy - h[i]/2 - 8).attr('y2', cy + h[i]/2 + 8)
          .attr('stroke', V('--line-soft')).attr('stroke-width', 1);
        svg.append('text').attr('x', X[i]).attr('y', mT - 24).attr('text-anchor', anc)
          .attr('font-size', narrow ? 10.5 : 12).attr('fill', V('--sub')).attr('font-family', FONT)
          .text(s.name);
        svg.append('text').attr('x', X[i]).attr('y', mT - 6).attr('text-anchor', anc)
          .attr('font-size', narrow ? 14 : 16).attr('font-weight', 600)
          .attr('fill', V('--ink')).attr('font-family', FONT)
          .text(label(i));
      });
      if (d.note) {
        svg.append('text').attr('x', mL).attr('y', H - 10)
          .attr('font-size', 11.5).attr('fill', V('--dim')).attr('font-family', FONT)
          .text(d.note);
      }
    }

    function drawAll(){
      if (!DATA.funnel) return;
      document.querySelectorAll('[data-funnel]').forEach(function(box){
        drawFunnel(box, DATA.funnel);
      });
    }
    drawAll();
    (window.LOOP_REDRAWS = window.LOOP_REDRAWS || []).push(drawAll);
  })();

  //=== 右ペインの開閉や画面幅の変化で iframe の幅が変わる。実寸で描いた図をまとめて描き直す。
  //===   連続で来るので 120ms 間引く
  var t;
  addEventListener('resize', function(){
    clearTimeout(t);
    t = setTimeout(function(){ (window.LOOP_REDRAWS || []).forEach(function(f){ f(); }); }, 120);
  });
})();
