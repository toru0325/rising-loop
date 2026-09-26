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
    //=== アップデート（帯のボタン）はコピー後に使い方を閉じる。開いたままだとトースト（z 96）がダイアログ（z 97）の下に隠れる
    var updBtn = document.getElementById('rl-update');
    if(updBtn) updBtn.addEventListener('click', function(){ setTimeout(function(){ howtoOn(false); }, 0); });
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

    //=== 「前の計測から入ったこと」の一覧。★ここは放っておくと文字の塊になる。
    //===   1回の更新で5〜8行増え、どれも同じ重さで並ぶので、どれを読めばいいか分からない。
    //===   ふせぎ方は2つだけ:
    //===     ① 日付が全部同じなら列をやめる（9/26 が7回並んでも読む役に立たない）
    //===     ② 先頭2行だけ出して、残りは畳む
    //===   ★これは「大事な順に書く」規約とセット。1行目に「なぜ動いたか」を書く
    var REC_SHOW = 2;
    function recList(head, rows){
      if (!rows || !rows.length) return "";
      var one = rows.every(function(r){ return r[0] === rows[0][0]; }) ? rows[0][0] : null;
      var li = function(r){
        return '<li>' + (one ? '' : '<b>' + r[0] + '</b>') + '<span>' + r[1] + '</span></li>';
      };
      var top = rows.slice(0, REC_SHOW), rest = rows.slice(REC_SHOW);
      var h = '<div class="hr-head">' + head + (one ? ' <em>' + one + '</em>' : '') + '</div>'
            + '<ul>' + top.map(li).join('') + '</ul>';
      if (rest.length)
        h += '<details class="fold rec-more"><summary>ほか ' + rest.length + ' 件</summary>'
           + '<ul>' + rest.map(li).join('') + '</ul></details>';
      return h;
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
      //=== ★ note の \n は改行として出す。1行が100字を超えると、13px の灰色の塊になる。
      //===   innerHTML は使わない（テキストのまま扱い、<br> だけを自分で足す）
      elNote.textContent = '';
      String(p.note || '').split('\n').forEach(function(line, i){
        if (i) elNote.appendChild(document.createElement('br'));
        elNote.appendChild(document.createTextNode(line));
      });
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


  /* ══════════════════════════════════════════════════════════════════
     図の部品（1.7.0）。data-rl を読んで中身を組み立てる
     ------------------------------------------------------------------
     ★ 頁に書くのは1行だけ。SVG も div の入れ子も書かない。
         <div class="rl" data-rl='{"t":"bullet","max":24,"now":1.37,"aim":24,"unit":"円"}'></div>
     ★ どの t を使うかはデータの形で決まる（references/HTML生成.md の引き金の表）。
       センスで選ばない。表に無い形のときだけ、その場で描いてよい。
     ★ ここに無い図を手で SVG で描くと、版が離れたときに部品とずれる。
       1.6.x では見本・頁・rising.js に3種類のファネルが生えた。だから1本にする。
     ★ 値だけを差し替えるので、update/LXX.py からも触れる（data-rl は JSON）。
     ══════════════════════════════════════════════════════════════════ */
  (function(){
    //=== 並びの色。濃い→薄いの順。SEQ（ファネル）とは別。内訳は「上が多い」が読めればよい
    var C = ['#52751f', '#7d9c48', '#a7c184', '#c9d3bd', '#dfe6d6'];
    var BAD = '#b95448', INK = '#1c2821', DIM = '#7c8b80', SOFT = '#dfe6d6';
    var MONO = 'ui-monospace,SFMono-Regular,Menlo,monospace';

    //=== ★画面に出る文字はここを必ず通す。data-rl は AI が書くので、
    //===   単位やラベルに < や " が混ざると markup が壊れる。' も属性に入るので落とす
    function esc(s){
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    //=== 0除算を出さない。母数が 0 のループは実際にある（初日・0件）
    function pc(v, max){ return !max ? 0 : Math.max(0, Math.min(100, n0(v) / max * 100)); }
    function mx(a){ return a.reduce(function(m, v){ return v > m ? v : m; }, 0); }
    //=== ★数字はここを必ず通す。キーが無い・null・文字列でも 0 になる。
    //===   通さないと fmt(undefined) が画面に "NaN" と出る（ベン図で実際に出た）
    function n0(v){ var x = +v; return isFinite(x) ? x : 0; }
    //=== 単位も esc を通す。通さないと d.unit の "<em>円" がそのまま markup になる
    function num(v, unit){ return fmt(n0(v)) + (unit ? esc(unit) : ''); }
    function ttl(s){ return s ? '<div class="rl-ttl">' + esc(s) + '</div>' : ''; }
    function note(s){ return s ? '<div class="rl-note">' + esc(s) + '</div>' : ''; }
    function key(items){
      return '<div class="rl-key">' + items.map(function(it){
        return '<span><i style="background:' + it.c + '"></i>' + esc(it.k) + '</span>';
      }).join('') + '</div>';
    }
    //=== 目盛りの値。刻みは 4 が既定（0 と max を含めて5本）
    function ticks(max, n, unit){
      var out = '';
      for (var i = 0; i <= n; i++){
        var v = max * i / n;
        out += '<span style="left:' + (i / n * 100) + '%">' + (i ? num(v, unit) : '0') + '</span>';
      }
      return out;
    }

    /* ── 1. bullet（軸つきブレット）いま・目標・まえ を1本の目盛りに ── */
    //=== ①道 と ②軸つき棒 を1つにしたもの。目盛りが入るので差が何倍でも潰れない
    function bullet(d){
      var max = d.max != null ? d.max : Math.max(d.aim || 0, d.now || 0, d.was || 0);
      var n = d.ticks || 4, ok = !!d.ok, h = '';
      h += '<div class="ax">' + ticks(max, n, d.unit) + '</div><div class="tr">';
      for (var i = 1; i < n; i++) h += '<i class="g" style="left:' + (i / n * 100) + '%"></i>';
      h += '<i class="val' + (ok ? ' ok' : '') + '" style="width:' + pc(d.now, max).toFixed(1) + '%"></i>';
      if (d.was != null)
        h += '<i class="was" style="left:' + pc(d.was, max).toFixed(1) + '%"><em>'
           + esc(d.wasLabel || 'まえ') + ' ' + num(d.was, d.unit) + '</em></i>';
      if (d.aim != null)
        //=== 右端ぴったりだとラベルが枠から出る。99% に寄せる（1.6.x の頁で実際にはみ出した）
        h += '<i class="aim" style="left:' + Math.min(99, pc(d.aim, max)).toFixed(1) + '%"><em>'
           + esc(d.aimLabel || '目標') + ' ' + num(d.aim, d.unit) + '</em></i>';
      h += '</div>';
      //=== ★ゴールの枠のように、いまと目標が図の左右に大きく出ている場所では lg:false で凡例を消す。
      //===   同じ数字を2回言わない（1.6.x の頁で「いま」が3か所に出ていた）
      if (d.lg !== false)
        h += '<div class="lg">' + esc(d.nowLabel || 'いま') + ' <b' + (ok ? ' class="ok"' : '') + '>'
           + num(d.now, d.unit) + '</b>' + (d.lead ? '　' + esc(d.lead) : '') + '</div>';
      return h;
    }

    /* ── 2. waffle（100マス）割合を粒で。1〜99% ── */
    function waffle(d){
      var on = Math.round(d.pct), h = '';
      for (var i = 0; i < 100; i++) h += '<i' + (i < on ? ' class="on"' : '') + '></i>';
      return ttl(d.title) + '<div class="gr">' + h + '</div>' + note(d.note);
    }

    /* ── 3. rank（横棒ランキング）0件も行として残る ── */
    //=== ④内訳 と A内訳ランキング を1つにしたもの。0 が消えないのはこの図だけ。
    //===   ★中身は既存の .rv-h をそのまま出す。1.3.x からある横棒で、プレイルームで28か所使っている。
    //===     ここで別の markup を作ると、同じ絵が2通りになる（ファネルで起きたのと同じこと）
    function rank(d){
      var rows = d.rows || [], max = mx(rows.map(function(r){ return n0(r.v); }));
      return ttl(d.title) + '<div class="rv-h">' + rows.map(function(r, i){
        var v = n0(r.v);
        //=== 先頭だけ濃い緑、あとは薄い（.rv-h に赤は無いので bad は見ない）
        return '<div class="k">' + esc(r.k) + '</div>'
             + '<div class="t"><i class="' + (i === 0 && v ? '' : 'dim') + '" style="width:'
             + pc(v, max).toFixed(1) + '%"></i></div>'
             + '<div class="v">' + fmt(v) + esc(d.unit || '') + '</div>';
      }).join('') + '</div>' + note(d.note);
    }

    /* ── 4. stack（帯100%）2つ以上に分ける。帯を並べると前後が見える ── */
    function stack(d){
      return (d.bands || []).map(function(b){
        var parts = b.parts || [], sum = parts.reduce(function(s, p){ return s + (+p.v || 0); }, 0);
        return ttl(b.title) + '<div class="rl-band">' + parts.map(function(p, i){
          var w = pc(p.v, sum);
          //=== 幅が細いと文字が入らない。8% 未満はラベルを落として色だけ残す
          return '<span style="width:' + w.toFixed(1) + '%;background:' + (p.c || C[i % C.length]) + '">'
               + (w >= 8 ? esc(p.k) + ' ' + fmt(n0(p.v)) + (d.unit || '') : '') + '</span>';
        }).join('') + '</div>';
      }).join('') + note(d.note);
    }

    /* ── 5. cal（カレンダー）曜日のクセ。濃いほど多い ── */
    function cal(d){
      var days = d.days || [], max = mx(days.map(function(x){ return n0(x.v); })), h = '';
      (d.head || ['月','火','水','木','金','土','日']).forEach(function(w){ h += '<b>' + esc(w) + '</b>'; });
      days.forEach(function(x){
        var a = max ? n0(x.v) / max : 0;
        h += '<i title="' + esc(x.d) + ' ' + num(x.v, d.unit) + '" style="background:rgba(82,117,31,'
           + (0.10 + a * 0.90).toFixed(2) + ')"></i>';
      });
      return ttl(d.title) + '<div class="gr">' + h + '</div>' + note(d.note);
    }

    /* ── 6. dumbbell（前 → いま）項目ごとに点を2つ置いて線でつなぐ ── */
    function dumbbell(d){
      var rows = d.rows || [];
      var max = d.max != null ? d.max : mx(rows.reduce(function(a, r){ return a.concat([n0(r.a), n0(r.b)]); }, []));
      return ttl(d.title) + rows.map(function(r){
        var A = pc(r.a, max), B = pc(r.b, max), up = n0(r.b) >= n0(r.a);
        return '<div class="r' + (up ? ' up' : '') + '"><span class="k">' + esc(r.k) + '</span>'
             + '<span class="tr"><i class="ln" style="left:' + Math.min(A, B).toFixed(1)
             + '%;width:' + Math.abs(B - A).toFixed(1) + '%"></i>'
             + '<i class="a" style="left:' + A.toFixed(1) + '%"></i>'
             + '<i class="b" style="left:' + B.toFixed(1) + '%"></i></span>'
             + '<span class="v">' + num(r.a, d.unit) + ' → ' + num(r.b, d.unit) + '</span></div>';
      }).join('') + note(d.note);
    }

    /* ── 7. hist（ヒストグラム）ばらつき。平均では消える形 ── */
    //=== ★中身は既存の .rv-bars / .rv-col / .rv-labels をそのまま出す（縦棒。1.3.x からある）。
    //===   いちばん高い山だけ濃くする。どこが多いかを目で拾えるようにする
    function hist(d){
      var bins = d.bins || [], max = mx(bins.map(function(b){ return n0(b.v); }));
      return ttl(d.title)
        + '<div class="rv-bars">' + bins.map(function(b){
            var v = n0(b.v);
            return '<div class="rv-col' + (max && v === max ? ' on' : '') + '"><b>' + fmt(v) + '</b>'
                 + '<i style="height:' + pc(v, max).toFixed(1) + '%"></i></div>';
          }).join('') + '</div>'
        + '<div class="rv-labels">' + bins.map(function(b){
            return '<span' + (max && n0(b.v) === max ? ' class="on"' : '') + '>' + esc(b.k) + '</span>';
          }).join('') + '</div>'
        + note(d.note);
    }

    /* ── 8. queue（待ち行列）段が3〜4。ファネルより軽い ── */
    function queue(d){
      var st = d.steps || [];
      return ttl(d.title) + '<div class="gr">' + st.map(function(s, i){
        return '<div class="st' + (i === st.length - 1 ? ' last' : '') + '"><b>' + fmt(n0(s.v)) + '</b>'
             + '<span>' + esc(s.k) + '</span></div>';
      }).join('') + '</div>' + note(d.note);
    }

    /* ── 9. pie（円）全体を3〜5に分ける ── */
    //=== 三角関数だけ。d3 が読めなくても描ける
    function arc(cx, cy, r, a0, a1){
      var x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
      var x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
      var big = (a1 - a0) > Math.PI ? 1 : 0;
      return 'M' + cx + ' ' + cy + ' L' + x0.toFixed(2) + ' ' + y0.toFixed(2)
           + ' A' + r + ' ' + r + ' 0 ' + big + ' 1 ' + x1.toFixed(2) + ' ' + y1.toFixed(2) + ' Z';
    }
    function pie(d){
      var sl = d.slices || [], sum = sl.reduce(function(s, x){ return s + n0(x.v); }, 0);
      var a = -Math.PI / 2, s = '<svg viewBox="0 0 120 120">', k = [];
      if (!sum) return '<div class="rl-none">まだ数字がありません</div>';
      sl.forEach(function(x, i){
        var c = x.c || C[i % C.length], a2 = a + n0(x.v) / sum * Math.PI * 2;
        s += '<path d="' + arc(60, 60, 54, a, a2) + '" fill="' + c + '"/>';
        k.push({ k: x.k + ' ' + Math.round(n0(x.v) / sum * 100) + '%', c: c });
        a = a2;
      });
      return ttl(d.title) + '<div class="rl-pie">' + s + '</svg>' + key(k) + '</div>' + note(d.note);
    }

    /* ── 10. donut（粒）1%未満。中に母数 ── */
    //=== ⑥点 の置き換え。円周を dasharray で切るだけなので、0.5% でも線が残る
    function donut(d){
      var total = n0(d.total), hit = n0(d.hit), R = 50, L = 2 * Math.PI * R;
      var on = total ? Math.max(1.2, L * hit / total) : 0;   //=== 細すぎて消えないよう最低 1.2
      var s = '<svg viewBox="0 0 130 130">'
        + '<circle cx="65" cy="65" r="' + R + '" fill="none" stroke="' + SOFT + '" stroke-width="17"/>'
        + '<circle cx="65" cy="65" r="' + R + '" fill="none" stroke="' + BAD + '" stroke-width="17"'
        + ' stroke-dasharray="' + on.toFixed(2) + ' ' + L.toFixed(0) + '" transform="rotate(-90 65 65)"/>'
        + '<text x="65" y="62" text-anchor="middle" font-size="25" font-weight="700" fill="' + INK + '" font-family="' + MONO + '">'
        + fmt(total) + '</text>'
        + '<text x="65" y="79" text-anchor="middle" font-size="11" fill="' + DIM + '">' + esc(d.totalLabel || '') + '</text>'
        + '<text x="65" y="97" text-anchor="middle" font-size="12" font-weight="700" fill="' + BAD + '" font-family="' + MONO + '">'
        + esc(d.hitLabel || ('うち ' + fmt(hit))) + '</text></svg>';
      var tx = (d.lines || []).map(function(l){ return esc(l); }).join('<br>');
      return ttl(d.title) + '<div class="rl-donut">' + s + (tx ? '<div class="tx">' + tx + '</div>' : '') + '</div>' + note(d.note);
    }

    /* ── 11. treemap（面積で内訳）大きさの差が激しいとき ── */
    //=== d3.treemap（矩形の敷き詰め）を使う。d3 は loop.html が必ず読むので退避は持たない
    function treemap(d){
      var cells = (d.cells || []).filter(function(c){ return n0(c.v) > 0; });
      if (!cells.length) return '<div class="rl-none">まだ数字がありません</div>';
      var W = 300, H = 150;
      var root = d3.hierarchy({ children: cells }).sum(function(x){ return n0(x.v); })
                   .sort(function(a, b){ return b.value - a.value; });
      d3.treemap().size([W, H]).paddingInner(2)(root);
      var s = '<svg viewBox="0 0 ' + W + ' ' + H + '">';
      root.leaves().forEach(function(n, i){
        var w = n.x1 - n.x0, h = n.y1 - n.y0, c = C[i % C.length], fg = i < 2 ? '#fff' : INK;
        s += '<rect x="' + n.x0.toFixed(1) + '" y="' + n.y0.toFixed(1) + '" width="' + w.toFixed(1)
           + '" height="' + h.toFixed(1) + '" fill="' + c + '"/>';
        //=== 小さい枠に文字を入れると読めない。幅52・高さ30 を下回ったら出さない
        if (w > 52 && h > 30){
          s += '<text x="' + (n.x0 + 7).toFixed(1) + '" y="' + (n.y0 + 18).toFixed(1)
             + '" font-size="11" fill="' + fg + '">' + esc(n.data.k) + '</text>'
             + '<text x="' + (n.x0 + 7).toFixed(1) + '" y="' + (n.y0 + 35).toFixed(1)
             + '" font-size="13" font-weight="700" fill="' + fg + '" font-family="' + MONO + '">'
             + num(n.data.v, d.unit) + '</text>';
        }
      });
      return ttl(d.title) + s + '</svg>' + note(d.note);
    }

    /* ── 12. area（面グラフ）合計の推移と、その内訳 ── */
    function area(d){
      var ser = d.series || [], labels = d.labels || [];
      var n = Math.max.apply(null, ser.map(function(s){ return (s.vals || []).length; }).concat([1]));
      var tot = [], i, j;
      for (i = 0; i < n; i++){
        var t = 0;
        for (j = 0; j < ser.length; j++) t += n0(ser[j].vals && ser[j].vals[i]);
        tot.push(t);
      }
      var max = mx(tot) || 1, W = 300, H = 120, PB = 16;
      var X = function(i){ return n < 2 ? W / 2 : i / (n - 1) * W; };
      var Y = function(v){ return (H - PB) - (H - PB) * (v / max); };
      var base = new Array(n).fill(0), s = '<svg viewBox="0 0 ' + W + ' ' + H + '">', k = [];
      ser.forEach(function(sr, si){
        var up = [], dn = [];
        for (i = 0; i < n; i++){
          var v = base[i] + n0(sr.vals && sr.vals[i]);
          up.push(X(i).toFixed(1) + ' ' + Y(v).toFixed(1));
          dn.unshift(X(i).toFixed(1) + ' ' + Y(base[i]).toFixed(1));
          base[i] = v;
        }
        var c = sr.c || C[si % C.length];
        s += '<polygon points="' + up.concat(dn).join(' ') + '" fill="' + c + '"/>';
        k.push({ k: sr.k, c: c });
      });
      s += '<line x1="0" y1="' + (H - PB) + '" x2="' + W + '" y2="' + (H - PB) + '" stroke="#c9d3bd"/>';
      labels.forEach(function(l, i){
        if (!l) return;
        s += '<text x="' + X(i).toFixed(1) + '" y="' + (H - 4) + '" font-size="9.5" fill="' + DIM
           + '" text-anchor="middle">' + esc(l) + '</text>';
      });
      return ttl(d.title) + s + '</svg>' + key(k) + note(d.note);
    }

    /* ── 13. slope（傾き）2時点だけ。順位が入れ替わったか ── */
    function slope(d){
      var rows = d.rows || [], W = 260, H = 130, PT = 22, PB = 12;
      var max = d.max != null ? d.max
              : mx(rows.reduce(function(a, r){ return a.concat([n0(r.a), n0(r.b)]); }, [])) || 1;
      var Y = function(v){ return PT + (H - PT - PB) * (1 - v / max); };
      var s = '<svg viewBox="0 0 ' + W + ' ' + H + '">'
        + '<text x="70" y="12" font-size="10" fill="' + DIM + '" text-anchor="end">' + esc(d.left || 'まえ') + '</text>'
        + '<text x="190" y="12" font-size="10" fill="' + DIM + '">' + esc(d.right || 'いま') + '</text>';
      rows.forEach(function(r, i){
        var up = n0(r.b) >= n0(r.a), c = up ? C[0] : BAD;
        var y0 = Y(n0(r.a)), y1 = Y(n0(r.b));
        s += '<line x1="70" y1="' + y0.toFixed(1) + '" x2="190" y2="' + y1.toFixed(1)
           + '" stroke="' + c + '" stroke-width="2"/>'
           + '<circle cx="70" cy="' + y0.toFixed(1) + '" r="4" fill="' + c + '"/>'
           + '<circle cx="190" cy="' + y1.toFixed(1) + '" r="4" fill="' + c + '"/>'
           + '<text x="64" y="' + (y0 + 3.5).toFixed(1) + '" font-size="10" fill="' + INK
           + '" text-anchor="end">' + esc(r.k) + ' ' + num(r.a, d.unit) + '</text>'
           + '<text x="197" y="' + (y1 + 3.5).toFixed(1) + '" font-size="10" fill="' + c + '">'
           + num(r.b, d.unit) + '</text>';
      });
      return ttl(d.title) + s + '</svg>' + note(d.note);
    }

    /* ── 14. venn（ベン図）2つの集まりの重なり ── */
    function venn(d){
      var a = d.a || {}, b = d.b || {}, both = n0(d.both);
      var s = '<svg viewBox="0 0 260 120">'
        + '<circle cx="100" cy="60" r="48" fill="' + C[0] + '" opacity=".3"/>'
        + '<circle cx="160" cy="60" r="42" fill="' + BAD + '" opacity=".3"/>'
        + '<text x="60" y="56" font-size="11" fill="' + INK + '" text-anchor="middle">' + esc(a.k) + '</text>'
        + '<text x="60" y="74" font-size="14" fill="' + INK + '" text-anchor="middle" font-family="' + MONO + '">' + fmt(n0(a.v)) + '</text>'
        + '<text x="130" y="64" font-size="14" fill="#8e3c31" text-anchor="middle" font-family="' + MONO + '">' + fmt(both) + '</text>'
        + '<text x="200" y="56" font-size="11" fill="' + INK + '" text-anchor="middle">' + esc(b.k) + '</text>'
        + '<text x="200" y="74" font-size="14" fill="' + INK + '" text-anchor="middle" font-family="' + MONO + '">' + fmt(n0(b.v)) + '</text>'
        + '</svg>';
      return ttl(d.title) + s + note(d.note);
    }

    /* ── 15. scatter（散布図）2つの数字に関係があるか ── */
    //=== 1件ずつの生データが要る。日ごとの集計しか無いループでは使えない
    function scatter(d){
      var p = d.pts || [], W = 280, H = 130, PL = 30, PB = 18, PT = 8, PR = 6;
      if (!p.length) return '<div class="rl-none">まだ数字がありません</div>';
      var xs = p.map(function(o){ return n0(o.x); }), ys = p.map(function(o){ return n0(o.y); });
      var xM = mx(xs) || 1, yM = mx(ys) || 1;
      var X = function(v){ return PL + (W - PL - PR) * (v / xM); };
      var Y = function(v){ return (H - PB) - (H - PB - PT) * (v / yM); };
      var s = '<svg viewBox="0 0 ' + W + ' ' + H + '">'
        + '<line x1="' + PL + '" y1="' + (H - PB) + '" x2="' + (W - PR) + '" y2="' + (H - PB) + '" stroke="#c9d3bd"/>'
        + '<line x1="' + PL + '" y1="' + PT + '" x2="' + PL + '" y2="' + (H - PB) + '" stroke="#c9d3bd"/>'
        + '<text x="2" y="' + (PT + 6) + '" font-size="9" fill="' + DIM + '">' + esc(d.y || '') + '</text>'
        + '<text x="' + (W - PR) + '" y="' + (H - 4) + '" font-size="9" fill="' + DIM + '" text-anchor="end">'
        + esc(d.x || '') + '</text>';
      p.forEach(function(o){
        s += '<circle cx="' + X(n0(o.x)).toFixed(1) + '" cy="' + Y(n0(o.y)).toFixed(1)
           + '" r="' + (o.out ? 5 : 4) + '" fill="' + (o.out ? BAD : C[2]) + '"'
           + (o.k ? ' title="' + esc(o.k) + '"' : '') + '/>';
      });
      return ttl(d.title) + s + '</svg>' + note(d.note);
    }

    var KINDS = {
      bullet: bullet, waffle: waffle, rank: rank, stack: stack, cal: cal,
      dumbbell: dumbbell, hist: hist, queue: queue, pie: pie, donut: donut,
      treemap: treemap, area: area, slope: slope, venn: venn, scatter: scatter
    };
    //=== 一覧を受け取る図は、その一覧が空なら「まだ数字がありません」を出す。
    //===   ★空の箱を出さない。出すと「図が壊れた」のか「数字が無い」のか画面で見分けられない
    var NEED = {
      rank:'rows', stack:'bands', cal:'days', dumbbell:'rows', hist:'bins',
      queue:'steps', pie:'slices', treemap:'cells', area:'series', slope:'rows', scatter:'pts'
    };

    function drawViz(){
      document.querySelectorAll('.rl[data-rl]').forEach(function(el){
        var spec;
        try { spec = JSON.parse(el.getAttribute('data-rl')); }
        catch (e){
          //=== 黙って空にしない。JSON が壊れていることが画面で分かるようにする
          el.className = 'rl';
          el.innerHTML = '<div class="rl-none">data-rl の JSON が読めません（' + esc(e.message) + '）</div>';
          return;
        }
        var f = KINDS[spec && spec.t];
        if (!f){
          el.className = 'rl';
          el.innerHTML = '<div class="rl-none">知らない図です: ' + esc(spec && spec.t) + '</div>';
          return;
        }
        var need = NEED[spec.t];
        if (need && !(spec[need] && spec[need].length)){
          el.className = 'rl rl-' + spec.t;
          el.innerHTML = (spec.title ? '<div class="rl-ttl">' + esc(spec.title) + '</div>' : '')
                       + '<div class="rl-none">まだ数字がありません</div>';
          return;
        }
        //=== クラスは毎回組み直す。t を書き換えたときに前の見た目が残らない
        el.className = 'rl rl-' + spec.t;
        el.innerHTML = f(spec);
      });
    }
    drawViz();
    (window.LOOP_REDRAWS = window.LOOP_REDRAWS || []).push(drawViz);
  })();

  //=== 右ペインの開閉や画面幅の変化で iframe の幅が変わる。実寸で描いた図をまとめて描き直す。
  //===   連続で来るので 120ms 間引く
  var t;
  addEventListener('resize', function(){
    clearTimeout(t);
    t = setTimeout(function(){ (window.LOOP_REDRAWS || []).forEach(function(f){ f(); }); }, 120);
  });
})();
