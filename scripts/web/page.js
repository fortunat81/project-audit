(function(){
 var D=JSON.parse(document.getElementById('data').textContent), root=document.documentElement;
 var KEY='audit-ui:'+D.project+':'+D.run;
 function load(k,d){try{var v=localStorage.getItem(k);return v===null?d:v}catch(e){return d}}
 function save(k,v){try{localStorage.setItem(k,v)}catch(e){}}
 var lang=load('audit-ui:lang',(navigator.language||'en').slice(0,2)==='fr'?'fr':'en'); if(!D.i18n[lang])lang='en';
 var theme=load('audit-ui:theme','auto');
 function t(k,v){var s=(D.i18n[lang]&&D.i18n[lang][k])||D.i18n.en[k]||k;if(v)Object.keys(v).forEach(function(x){s=s.replace('{'+x+'}',v[x])});return s}
 function L(o){if(o==null)return '';if(typeof o==='string')return o;return o[lang]||o.en||o.fr||''}
 function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
 function dark(){return theme==='dark'||(theme==='auto'&&window.matchMedia&&matchMedia('(prefers-color-scheme: dark)').matches)}
 function applyTheme(){root.setAttribute('data-theme',theme==='auto'?'auto':theme);
  document.getElementById('theme').textContent=dark()?t('theme_light'):t('theme_dark')}

 // ---- fixes state
 var picked={},notes={};
 try{var st=JSON.parse(load(KEY+':fixes','{}'));picked=st.picked||{};notes=st.notes||{}}catch(e){}
 function saveFixes(){save(KEY+':fixes',JSON.stringify({picked:picked,notes:notes}))}

 var order={critical:0,high:1,medium:2,low:3,info:4}, sortKey='severity', sortDir=1;

 function renderStatic(){
  root.lang=lang;
  document.querySelectorAll('[data-i18n]').forEach(function(n){n.textContent=t(n.dataset.i18n)});
  document.querySelectorAll('[data-i18n-ph]').forEach(function(n){n.placeholder=t(n.dataset.i18nPh)});
  document.getElementById('lang').textContent=t('lang_btn');
  applyTheme();
  document.getElementById('project').textContent=D.project;
  document.getElementById('meta').textContent=t('meta_line',D.meta);
  var v=document.getElementById('verdict');v.textContent='';
  var vk=D.verdict||'none', box=el('div','verdict v-'+vk), b=el('span',null,t('verdict_'+vk));box.appendChild(b);
  box.appendChild(document.createTextNode(D.verdict?t('mode_line',{n:D.level,mode:t(D.mode||'full')}):t('verdict_none_hint')));v.appendChild(box);
  var nb=document.getElementById('notices');nb.textContent='';
  D.notices.forEach(function(n){nb.appendChild(el('div','notice',(n.n!=null?n.n+' ':'')+t(n.key)))});
  var counts={};D.findings.forEach(function(f){counts[f.severity]=(counts[f.severity]||0)+1});
  var cards=document.getElementById('cards');cards.textContent='';
  ['critical','high','medium','low','info'].forEach(function(s){var c=el('div','card s-'+s);c.appendChild(el('b',null,String(counts[s]||0)));c.appendChild(el('span',null,t('sev_'+s)));cards.appendChild(c)});
  var ran=D.manifest.filter(function(m){return m.cls==='ok'||m.cls==='find'}).length, c2=el('div','card');
  c2.appendChild(el('b',null,ran+' / '+D.manifest.length));c2.appendChild(el('span',null,t('checks_ran')));cards.appendChild(c2);
  var sc=document.getElementById('scores');sc.textContent='';
  var names=Object.keys(D.scores);
  if(names.length){var sec=el('section');sec.appendChild(el('h2',null,t('scores')));var bars=el('div','bars');
   names.forEach(function(k){var val=D.scores[k],row=el('div','bar');row.appendChild(el('b',null,t('dim_'+k)));
    if(val==null){row.appendChild(el('span'));row.appendChild(el('i',null,t('not_assessed')))}
    else{var tr=el('div','track'),f=el('div','fill');f.style.width=Math.max(0,Math.min(100,val))+'%';tr.appendChild(f);row.appendChild(tr);
     row.appendChild(el('i',null,val+(D.confidence[k]?' ('+D.confidence[k]+')':'')))}
    bars.appendChild(row)});sec.appendChild(bars);sc.appendChild(sec)}
  // filters
  var sel=document.getElementById('source'),cur=sel.value;sel.textContent='';
  var o=el('option',null,t('all_tools'));o.value='';sel.appendChild(o);
  Array.from(new Set(D.findings.map(function(f){return f.source}))).sort().forEach(function(s){var op=el('option',null,s);op.value=s;sel.appendChild(op)});sel.value=cur;
  // coverage
  var cb=document.querySelector('#coverage tbody');cb.textContent='';
  D.manifest.forEach(function(m){var tr=el('tr','c-'+m.cls);tr.appendChild(el('td',null,m.tool));tr.appendChild(el('td',null,L(m.status_i18n)));tr.appendChild(el('td',null,L(m.dim_i18n)));cb.appendChild(tr)});
  // checklist
  var ck=document.getElementById('checklist-sec');ck.hidden=!D.checklist.length;
  var kb=document.querySelector('#checklist tbody');kb.textContent='';
  D.checklist.forEach(function(r){var tr=el('tr');[String(r.n),L(r.item),r.mark,r.by,L(r.evidence)].forEach(function(x){tr.appendChild(el('td',null,x))});kb.appendChild(tr)});
  // report
  var rf=document.getElementById('report-formatted'),rs=document.getElementById('report-source'),nr=document.getElementById('no-report');
  var rep=D.reports[lang]||D.reports[D.primary]||D.reports.en||D.reports.fr, has=!!rep, note=document.getElementById('report-note');
  nr.hidden=has;document.getElementById('seg').hidden=!has;
  rf.innerHTML=has?rep.html:'';   // built and escaped by the generator (no raw HTML from the report passes through)
  rs.textContent=has?rep.source:'';
  var missing=has&&!D.reports[lang];note.hidden=!missing;
  if(missing){document.getElementById('report-note-text').textContent=t('not_translated');
   var tb=document.getElementById('translate-btn');tb.hidden=!(window.AUDIT_SERVER&&window.AUDIT_SERVER.translate);
   if(!window.AUDIT_SERVER)document.getElementById('report-note-text').textContent=t('not_translated')+' '+t('translate_hint')}
  renderFindings();renderFixes();
 }

 function renderFindings(){
  var body=document.querySelector('#findings tbody'),none=document.getElementById('none'),count=document.getElementById('count');
  var on={};document.querySelectorAll('#filters input[data-sev]').forEach(function(c){on[c.dataset.sev]=c.checked});
  var term=document.getElementById('q').value.toLowerCase(),s=document.getElementById('source').value;
  var rows=D.findings.filter(function(f){return on[f.severity]&&(!s||f.source===s)&&(!term||(f.file+' '+f.rule+' '+f.id+' '+f.source).toLowerCase().indexOf(term)>=0)});
  rows.sort(function(a,b){var x=sortKey==='severity'?order[a.severity]:String(a[sortKey]),y=sortKey==='severity'?order[b.severity]:String(b[sortKey]);return(x<y?-1:x>y?1:0)*sortDir});
  body.textContent='';
  rows.forEach(function(f){var tr=el('tr'),td=el('td'),p=el('span','pill p-'+f.severity,t('sev_'+f.severity));td.appendChild(p);tr.appendChild(td);
   tr.appendChild(el('td',null,f.id));tr.appendChild(el('td',null,f.source));var wt=el('td',null,f.rule+(f.count>1?'  (x'+f.count+')':''));
   if(f.desc){wt.appendChild(el('br'));wt.appendChild(el('small','muted',L(f.desc)))}tr.appendChild(wt);
   tr.appendChild(el('td','file',f.file+(f.line!==''&&f.line!=null?':'+f.line:'')));body.appendChild(tr)});
  count.textContent=rows.length+' '+t('of')+' '+D.findings.length+' '+t('shown');none.hidden=rows.length>0;
 }

 function renderFixes(){
  var box=document.getElementById('fixlist');box.textContent='';
  if(!D.fixes.length){box.appendChild(el('div','empty',D.fixes_error||t('fixes_none')))}
  D.fixes.forEach(function(f){
   var card=el('div','fix'+(picked[f.id]?' on':'')),h=el('h3',null,f.id+'  '+L(f.title));card.appendChild(h);
   var meta=el('div','meta');
   if(f.severity){meta.appendChild(el('span','pill p-'+f.severity,t('sev_'+f.severity)||f.severity))}
   if(f.finding)meta.appendChild(el('span','badge',f.finding));
   if(f.file)meta.appendChild(el('span','file',f.file));
   meta.appendChild(el('span','badge',f.who==='you'?t('who_you'):t('who_claude')));
   if(f.risk)meta.appendChild(el('span',null,t('risk')+': '+f.risk));
   card.appendChild(meta);
   [['why',f.why],['change',f.change],['verify',f.verify]].forEach(function(p){
    var txt=L(p[1]);if(!txt)return;var d=el('details'),s=el('summary',null,t(p[0]));d.appendChild(s);
    var body=p[0]==='change'?el('pre','source',txt):el('div',null,txt);d.appendChild(body);if(p[0]!=='verify')d.open=true;card.appendChild(d)});
   var lab=el('label','ok'),cb=el('input');cb.type='checkbox';cb.checked=!!picked[f.id];
   cb.addEventListener('change',function(){picked[f.id]=cb.checked;saveFixes();card.className='fix'+(cb.checked?' on':'');updateBar()});
   lab.appendChild(cb);lab.appendChild(el('span',null,f.who==='you'?t('myself'):t('approve')));card.appendChild(lab);
   var ta=el('textarea');ta.placeholder=t('note');ta.value=notes[f.id]||'';
   ta.addEventListener('input',function(){notes[f.id]=ta.value;saveFixes()});card.appendChild(ta);
   box.appendChild(card)});
  updateBar();
 }
 function chosen(){return D.fixes.filter(function(f){return picked[f.id]})}
 function updateBar(){var n=chosen().length;document.getElementById('selcount').textContent=n;document.getElementById('sendbar').hidden=!D.fixes.length;
  document.getElementById('copy').disabled=!n;document.getElementById('dl').disabled=!n}
 function message(){
  var c=chosen();if(!c.length)return t('msg_none');
  var mine=c.filter(function(f){return f.who==='you'}),todo=c.filter(function(f){return f.who!=='you'});
  var L=[t('msg_head')+' audit/'+D.run+' ('+D.project+'):',''];
  function line(f,i){var s=(i+1)+'. '+f.id+(f.finding?' ('+f.finding+')':'')+' - '+L(f.title)+(f.file?' ['+f.file+']':'');
   if(notes[f.id]&&notes[f.id].trim())s+='\n   '+t('msg_note')+': '+notes[f.id].trim();return s}
  todo.forEach(function(f,i){L.push(line(f,i))});
  if(mine.length){L.push('','** '+t('msg_mine')+':');mine.forEach(function(f,i){L.push(line(f,i))})}
  L.push('',t('msg_rules'),'',JSON.stringify({run:D.run,approved:todo.map(function(f){return{id:f.id,finding:f.finding||null,note:(notes[f.id]||'').trim()}}),
   mine:mine.map(function(f){return f.id})}));
  return L.join('\n');
 }
 function flash(msg){var c=document.getElementById('copied');c.textContent=msg;setTimeout(function(){c.textContent=''},3000)}
 document.getElementById('copy').addEventListener('click',function(){
  var m=message();
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(m).then(function(){flash(t('copied'))},function(){fallback(m)})}else{fallback(m)}});
 function fallback(m){var ta=el('textarea');ta.value=m;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');flash(t('copied'))}catch(e){}document.body.removeChild(ta)}
 document.getElementById('dl').addEventListener('click',function(){
  var c=chosen(),data={run:D.run,project:D.project,approved:c.filter(function(f){return f.who!=='you'}).map(function(f){return{id:f.id,finding:f.finding||null,title:L(f.title),note:(notes[f.id]||'').trim()}}),
   mine:c.filter(function(f){return f.who==='you'}).map(function(f){return f.id})};
  var a=el('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.download='approved-fixes.json';document.body.appendChild(a);a.click();document.body.removeChild(a)});
 document.getElementById('selall').addEventListener('click',function(){D.fixes.forEach(function(f){picked[f.id]=true});saveFixes();renderFixes()});
 document.getElementById('clearsel').addEventListener('click',function(){picked={};saveFixes();renderFixes()});

 document.getElementById('lang').addEventListener('click',function(){lang=lang==='en'?'fr':'en';save('audit-ui:lang',lang);renderStatic()});
 document.getElementById('theme').addEventListener('click',function(){theme=dark()?'light':'dark';save('audit-ui:theme',theme);applyTheme()});
 if(window.matchMedia)matchMedia('(prefers-color-scheme: dark)').addEventListener&&matchMedia('(prefers-color-scheme: dark)').addEventListener('change',applyTheme);
 document.querySelectorAll('#filters input[data-sev]').forEach(function(c){c.addEventListener('change',renderFindings)});
 document.getElementById('q').addEventListener('input',renderFindings);document.getElementById('source').addEventListener('change',renderFindings);
 document.querySelectorAll('#findings th').forEach(function(th){th.addEventListener('click',function(){var k=th.dataset.k;if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=1}renderFindings()})});
 document.querySelectorAll('#seg button').forEach(function(b){b.addEventListener('click',function(){
  document.querySelectorAll('#seg button').forEach(function(x){x.classList.toggle('on',x===b)});
  document.getElementById('report-formatted').hidden=b.dataset.view!=='formatted';document.getElementById('report-source').hidden=b.dataset.view!=='source'})});
 // ---- start Claude from this page (only when served by scan.sh --serve)
 var S=window.AUDIT_SERVER||null, timer=null;
 function api(path,opts){opts=opts||{};opts.headers={'X-Audit-Token':S.token,'Content-Type':'application/json'};
  return fetch(path,opts).then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}})})}
 function claudeFixes(){return chosen().filter(function(f){return f.who!=='you'})}
 function showState(st){var b=document.getElementById('state');b.textContent=t('state_'+st.state);
  document.getElementById('progress-sec').hidden=(st.state==='idle');
  document.getElementById('log').textContent=st.log&&st.log.length?st.log.join('\n\n'):t('log_empty');
  document.getElementById('reportready').textContent=st.report?t('report_ready',{run:D.run}):'';
  document.getElementById('fixbtn').disabled=(st.state==='running')||!claudeFixes().length}
 function poll(){api('/api/status').then(function(r){if(r.ok){showState(r.j);if(r.j.state==='running'){clearTimeout(timer);timer=setTimeout(poll,2000)}}})}
 function initServer(){
  var hint=document.getElementById('serverhint');
  if(!S){hint.hidden=!D.fixes.length;hint.textContent=t('server_hint');return}
  if(!S.fixable){hint.hidden=false;hint.textContent=S.reason;return}
  hint.hidden=true;document.getElementById('fixbtn').hidden=false;poll()}
 document.getElementById('fixbtn').addEventListener('click',function(){
  var c=claudeFixes();if(!c.length||!S)return;
  if(!confirm(t('confirm_fix',{n:c.length})))return;
  api('/api/start',{method:'POST',body:JSON.stringify({ids:c.map(function(f){return f.id}),notes:notes})}).then(function(r){
   if(r.ok){flash(t('started'));poll()}else{flash(t('start_failed')+': '+(r.j&&r.j.error||''))}})});
 var _upd=updateBar;updateBar=function(){_upd();if(S&&S.fixable){document.getElementById('fixbtn').disabled=!claudeFixes().length}};
 function translateNow(){
  if(!S)return;var b=document.getElementById('translate-btn');b.disabled=true;flash(t('translating'));
  api('/api/translate',{method:'POST',body:JSON.stringify({})}).then(function(r){
   if(!r.ok){b.disabled=false;flash(t('translate_failed')+': '+(r.j&&r.j.error||''));return}
   (function wait(){api('/api/status').then(function(s){
     if(s.j.state==='running'){setTimeout(wait,2000)}
     else if(s.j.state==='done'){flash(t('translated'));setTimeout(function(){location.reload()},800)}
     else{b.disabled=false;flash(t('translate_failed'))}})})()})}
 document.getElementById('translate-btn').addEventListener('click',translateNow);
 document.getElementById('tools').hidden=false;
 renderStatic();initServer();
})();
