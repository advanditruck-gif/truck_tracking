const K='trk1',$=s=>document.querySelector(s);
let S;try{S=JSON.parse(localStorage.getItem(K))}catch(e){}S=S||{run:null,ev:[]};
const keep=()=>{try{localStorage.setItem(K,JSON.stringify(S))}catch(e){}};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let sample=null;(async()=>{try{if(window.claude)sample=await claude.use('sample')}catch(e){}})();
const FIELDS={cluster:['km','date','time'],geo:['date','time','road','location','district','state','gps'],fuel:['date','time','receipt_no','product','rate','volume','amount','vehicle_no'],visit:['business_name','area','amount_collected']};
const P={cluster:'Read the vehicle instrument cluster. Prioritize the odometer value shown beside or above "ODO" (usually near the bottom of the display); ignore people, hands, reflections, and other dashboard values. Transcribe the odometer digits exactly as a number, without units or separators. Also read the displayed date and time if legible. Always return all three keys, using null only for a value that is genuinely unreadable. Return valid JSON only, in this shape: {"km": 7148, "date": "2026-10-28", "time": "20:00"}. Use null for unreadable values and 24-hour time.',
geo:'GPS-stamped camera photo. Read the overlay text. Return JSON {"date":"YYYY-MM-DD","time":"HH:MM" 24h,"road":"street line","location":"locality line","district":"","state":"","gps":"lat,lng if visible else empty"}.',
fuel:'Fuel pump bill, layout varies. Return JSON {"date":"YYYY-MM-DD","time":"HH:MM" 24h,"receipt_no":"receipt/voucher no, the unique id","product":"","rate":number,"volume":number,"amount":number,"vehicle_no":""}.'};
async function extract(kind,blob){try{
 if(sample)return await sample.json(P[kind]+' Reply with JSON only; null if unreadable.',{images:[blob]});
 const f=new FormData();f.append('kind',kind);f.append('image',blob,'p.jpg');
 const r=await fetch('/api/extract',{method:'POST',body:f});if(!r.ok)return{_error:'Server error '+r.status+' (see the terminal running app.py)'};return await r.json();}catch(e){return{_error:'Cannot reach server: '+e.message}}}
async function reverseGeocode(coords){try{const [lat,lon]=coords.split(',').map(Number);if(!Number.isFinite(lat)||!Number.isFinite(lon))return{_error:'Phone GPS coordinates are unavailable.'};
 const r=await fetch('/api/reverse-geocode?'+new URLSearchParams({lat:String(lat),lon:String(lon)}));const d=await r.json();if(!r.ok)return{_error:d.error||'Address lookup failed.'};return d;
 }catch(e){return{_error:'Address lookup failed: '+e.message}}}
function modal(h,kind=''){const m=document.createElement('div');m.className='md '+kind;m.innerHTML='<div class="bx">'+h+'</div>';document.body.append(m);return m}
const busy=t=>{const m=modal('<h3>'+t+'</h3><div class="mu">Please wait…</div>','md-loading');return()=>m.remove()};
async function shrink(src){const bm=await createImageBitmap(src),r=Math.min(1,1920/Math.max(bm.width,bm.height)),c=document.createElement('canvas');
 c.width=bm.width*r;c.height=bm.height*r;c.getContext('2d').drawImage(bm,0,0,c.width,c.height);
 return new Promise(ok=>c.toBlob(ok,'image/jpeg',.92))}
const thumb=async b=>{const bm=await createImageBitmap(b),c=document.createElement('canvas');c.width=c.height=96;
 const s=Math.min(bm.width,bm.height);c.getContext('2d').drawImage(bm,0,0,s,s,0,0,96,96);return c.toDataURL('image/jpeg',.6)};
const gpsNow=()=>new Promise(ok=>navigator.geolocation?navigator.geolocation.getCurrentPosition(p=>ok(p.coords.latitude.toFixed(5)+','+p.coords.longitude.toFixed(5)),()=>ok(''),{timeout:6000}):ok(''));
// Live camera only: no gallery picker. Fallback = native camera intent (capture) if getUserMedia is blocked.
function shoot(title){return new Promise(res=>{
 const m=modal('<span class="sheet-kicker">CAMERA</span><h3>'+title+'</h3><video autoplay playsinline muted></video><input type="file" accept="image/*" capture="environment" hidden><div class="row"><button class="g" id="x">Cancel</button><button id="c">📷 Capture</button></div>','md-camera');
 const v=m.querySelector('video'),fb=m.querySelector('input');let st=null,cam=false;
 const end=b=>{st&&st.getTracks().forEach(t=>t.stop());m.remove();res(b)};
 navigator.mediaDevices?.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}},audio:false}).then(s=>{st=s;cam=true;v.srcObject=s}).catch(()=>{v.hidden=true});
 m.querySelector('#x').onclick=()=>end(null);
 m.querySelector('#c').onclick=async()=>{if(!cam)return fb.click();const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;
  c.getContext('2d').drawImage(v,0,0);c.toBlob(async b=>end(await shrink(b)),'image/jpeg',.95)};
 fb.onchange=async()=>fb.files[0]&&end(await shrink(fb.files[0]));})}
function review(title,kind,vals,th,note){return new Promise(res=>{
 const m=modal('<span class="sheet-kicker">REVIEW DETAILS</span><h3>'+title+'</h3>'+(th?'<img class="th" src="'+th+'">':'')+(note?'<p class="mu" style="color:var(--wr)">'+note+'</p>':'')+'<div id="fl"></div><div class="row"><button class="g" id="x">Cancel</button><button id="ok">Save</button></div>','md-review'),ins={};
 FIELDS[kind].forEach(k=>{const l=document.createElement('label');l.textContent=k.replace(/_/g,' ');const i=document.createElement('input');i.value=vals[k]??'';
  if(/amount_collected|km|rate|volume|amount$/.test(k))i.inputMode='decimal';ins[k]=i;l.append(i);m.querySelector('#fl').append(l)});
 m.querySelector('#x').onclick=()=>{m.remove();res(null)};
 m.querySelector('#ok').onclick=()=>{const o={};for(const k in ins)o[k]=ins[k].value.trim();m.remove();res(o)}})}
function add(t,d,th){const e={t,at:new Date().toISOString(),d,th};S.ev.push(e);keep();
 if(!sample)fetch('/api/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run:S.run&&S.run.id,t,at:e.at,d})}).catch(()=>{});render()}
async function snap(kind,title,extra={}){const b=await shoot(title);if(!b)return null;const capturedAt=new Date(),done=busy('Reading image…');
 const [d,th,g]=await Promise.all([extract(kind,b),thumb(b),kind==='geo'?gpsNow():'']);done();
 const v=Object.assign({},d,extra);if(kind==='geo')v.device_gps=g;if(kind==='geo'&&!v.gps)v.gps=g;
 const coordinates=g||v.gps;let geoError='';if(kind==='geo'&&coordinates){const address=await reverseGeocode(coordinates);geoError=address._error||'';for(const key of ['road','location','state'])if(!v[key]&&address[key])v[key]=address[key];if(address.district)v.district=address.district;}
 if(kind==='geo'&&String(v.state||'').trim().toLowerCase()==='kerala'&&String(v.district||'').trim().toLowerCase()==='ernad')v.district='Malappuram';
 if(kind==='cluster'||kind==='geo'){const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  v.date=String(capturedAt.getDate()).padStart(2,'0')+'-'+months[capturedAt.getMonth()]+'-'+capturedAt.getFullYear();
  v.time=capturedAt.toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});}
 const err=d&&d._error;if(d)delete d._error;const hasValues=FIELDS[kind].some(k=>v&&v[k]!=null&&String(v[k]).trim()!=='');const note=kind==='geo'?'Address lookup uses phone GPS via OpenStreetMap (© OpenStreetMap contributors).'+(geoError?' '+geoError:''):(err&&!hasValues?'Reading failed: '+err:(hasValues?'':'No values returned. Server replied: '+JSON.stringify(d)+' (open /api/ping to check the server version)'));
 const o=await review(title,kind,v,URL.createObjectURL(b),note);return o&&{o,th}}
// ---- actions
async function start(){try{Notification.requestPermission()}catch(e){}
 const r=await snap('cluster','UPLOAD CLUSTER IMAGE');if(!r)return;
 S.run={id:Date.now(),start:new Date().toISOString(),due:null,end:null};add('start_km',r.o,r.th);await visit()}
async function visit(){const o=await review('Business details','visit',{});if(!o)return;add('visit',o);await loc('CAPTURE LOCATION IMAGE')}
async function loc(t){const r=await snap('geo',t||'UPLOAD CURRENT LOCATION IMAGE');if(!r)return;
 S.run.due=Date.now()+30*60000;S.run.notified=false;add('location',r.o,r.th)}
function fuel(){const m=modal('<span class="sheet-kicker">FUEL ENTRY</span><h3>Choose fuel type</h3><p class="mu">Select the category for this refuel.</p><button class="fuel-option" id="p"><span class="fuel-icon">P</span><span><b>Petrol</b><small>Generator · ₹1000 preset</small></span><span class="fuel-arrow">›</span></button><button class="fuel-option" id="d"><span class="fuel-icon">D</span><span><b>Diesel</b><small>Vehicle · ₹1500 preset</small></span><span class="fuel-arrow">›</span></button><button class="g" id="x">Cancel</button>','md-choice');
 const go=async(type,preset)=>{m.remove();const r=await snap('fuel','UPLOAD FUEL BILL',{});if(!r)return;
  const rc=r.o.receipt_no;if(!rc)return alert('Receipt/voucher number is required.');
  if(S.ev.some(e=>e.t==='fuel'&&e.d.receipt_no===rc))return alert('Duplicate bill: receipt '+rc+' was already uploaded.');
  if(!r.o.product)r.o.product=type.split(' - ')[0];
  r.o.fuel_for=type;r.o.preset=preset;r.o.flag=Number(r.o.amount)!==preset?'Amount differs from ₹'+preset:'';
  add('fuel',r.o,r.th)};
 m.querySelector('#p').onclick=()=>go('Petrol - Generator',1000);m.querySelector('#d').onclick=()=>go('Diesel - Vehicle',1500);m.querySelector('#x').onclick=()=>m.remove()}
async function stop(){if(!confirm('Stop today’s run?'))return;const r=await snap('cluster','UPLOAD CLUSTER IMAGE');if(!r)return;
 S.run.end=new Date().toISOString();add('stop_km',r.o,r.th)}
function reset(){if(confirm('Clear today’s data from this device? Export CSV first.')){S={run:null,ev:[]};keep();render()}}
async function csv(){const rows=[['type','recorded_at','details']].concat(S.ev.map(e=>[e.t,e.at,JSON.stringify(e.d)]));
 const data=rows.map(r=>r.map(c=>'"'+String(c).replace(/"/g,'""')+'"').join(',')).join('\n'),name='truck-'+new Date().toISOString().slice(0,10)+'.csv';
 try{const d=window.claude&&await claude.use('downloads');if(d)return await d.save({filename:name,data})}catch(e){}
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([data],{type:'text/csv'}));a.download=name;a.click()}
// ---- render
const N={start_km:'Start KM',visit:'Business visit',location:'Location',fuel:'Fuel bill',stop_km:'Stop KM'};
const ev=t=>S.ev.filter(e=>e.t===t);
function render(){const r=S.run,A=$('#app');
 if(!r){A.innerHTML='<section class="welcome"><div class="welcome-copy"><span class="section-kicker">YOUR FLEET, IN FOCUS</span><h2>Every mile,<br>accounted for.</h2><p>Start your shift with an odometer photo. Track distance, visits, fuel, and location updates from one simple daily log.</p><button class="big" id="s">▶ &nbsp; Start today’s run</button><span class="welcome-foot">A clearer view of every working day.</span></div><div class="welcome-visual"><div class="route-orbit orbit-one"></div><div class="route-orbit orbit-two"></div><div class="truck-illustration">🚚</div><div class="route-chip"><span class="route-dot"></span><span><b>READY WHEN YOU ARE</b><small>Daily tracking starts here</small></span></div><div class="visual-caption">TRIP <b>01</b><span> / &nbsp;TODAY</span></div></div></section>'+(S.ev.length?'<button class="g" id="rs">Clear old data</button>':'');
  $('#s').onclick=start;$('#rs')&&($('#rs').onclick=reset);return}
 const sk=+ev('start_km')[0].d.km,ek=ev('stop_km')[0]?+ev('stop_km')[0].d.km:null,sum=(t,k)=>ev(t).reduce((a,e)=>a+(+e.d[k]||0),0);
 const over=!r.end&&r.due&&Date.now()>r.due,min=r.due?Math.max(0,Math.ceil((r.due-Date.now())/60000)):0;
 const timeline='<aside class="card timeline"><div class="timeline-heading"><div><span class="section-kicker">ACTIVITY</span><h3>Today’s timeline</h3></div><span class="timeline-count">'+S.ev.length+' LOGS</span></div>'+S.ev.slice().reverse().map(e=>'<div class="ev">'+(e.th?'<img src="'+e.th+'">':'<div style="width:46px"></div>')+'<div><b>'+N[e.t]+'</b> · '+new Date(e.at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})+'<br><span class="mu">'+Object.entries(e.d).filter(([k,v])=>v&&k!=='preset').map(([k,v])=>esc(k.replace(/_/g,' '))+': '+esc(v)).join(' · ')+'</span></div></div>').join('')+'</aside>';
 const controls=r.end?'<div class="actions"><button id="e">Export CSV</button><button class="g" id="rs">Start new day</button></div>':
 '<section class="quick-actions"><div class="section-heading"><span class="section-kicker">ON THE ROAD</span><span class="mu">Quick actions</span></div><div class="actions"><button id="l">📍 Upload current location image</button><button id="v">🏪 New business visit</button><button id="f">⛽ Upload fuel bill</button><button class="w" id="st">■ STOP</button></div><button class="g demo" id="dm">Demo: skip 30 min wait</button></section>';
 A.innerHTML=(over?'<div class="alert">⏰ UPLOAD CURRENT LOCATION IMAGE</div>':'')+
 '<div class="dashboard-grid"><div class="dashboard-main"><div class="card"><div class="section-kicker">SHIFT OVERVIEW</div><div class="stat"><div><span class="mu">Start KM</span><b>'+esc(sk)+'</b></div><div><span class="mu">'+(ek?'Distance':'Distance (so far)')+'</span><b>'+(ek?ek-sk:'—')+' km</b></div>'+
 '<div><span class="mu">Collected</span><b>₹'+sum('visit','amount_collected')+'</b></div><div><span class="mu">Fuel</span><b>₹'+sum('fuel','amount')+'</b></div></div>'+
 (r.end?'':'<p class="mu">Next location photo '+(over?'is due now':'in '+min+' min')+'</p>')+'</div>'+controls+'</div>'+timeline+'</div>';
 const b=(i,f)=>$('#'+i)&&($('#'+i).onclick=f);b('l',()=>loc());b('v',visit);b('f',fuel);b('st',stop);b('e',csv);b('rs',reset);
 b('dm',()=>{r.due=Date.now()-1;r.notified=false;keep();render()})}
setInterval(()=>{const r=S.run;if(r&&!r.end&&r.due&&Date.now()>r.due&&!r.notified){r.notified=true;keep();
 try{new Notification('UPLOAD CURRENT LOCATION IMAGE',{body:'30 minutes passed'});navigator.vibrate&&navigator.vibrate([300,150,300])}catch(e){}render()}
 else if(r&&!r.end&&!document.querySelector('.md'))render()},5000);
render();