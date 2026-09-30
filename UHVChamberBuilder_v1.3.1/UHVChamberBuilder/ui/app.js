/* Local-only palette UI. No external dependencies or network requests. */
'use strict';
const $=s=>document.querySelector(s), $$=s=>Array.from(document.querySelectorAll(s));
const h=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone=v=>JSON.parse(JSON.stringify(v));
const uid=p=>p+'_'+(globalThis.crypto?.randomUUID?.().replaceAll('-','').slice(0,16)||Math.random().toString(16).slice(2)+Date.now().toString(16));
const num=v=>Number(String(v??0).replace(',','.'));
let recipe=null,catalog=null,docKey='',offline=false,working=false,saveTimer=null,validationTimer=null;
let pointerHeld=false,renderPending=false;
let uiEpoch=0,reloadTimer=null,bridgeQueue=Promise.resolve();
let statuses={},resolved={},diagnostics=[],errors=[],inventory=[],saved=[];
const expanded=new Set();
const temporarilyDisabled=new Set();
const fk=['od','thickness','pcd','bolts','hole','knife','recess','gasket_od','gasket_id','gasket_t'];
const labels={od:'OD',thickness:'Thickness',pcd:'Bolt circle',bolts:'# bolts',hole:'Hole Ø',knife:'Knife Ø',recess:'Recess Ø',gasket_od:'Gasket OD',gasket_id:'Gasket ID',gasket_t:'Gasket thickness'};

function notice(text,kind=''){const el=$('#notice');el.textContent=text;el.className=kind;}
function busy(value){
  if(value&&!working){$$('input,select,button').forEach(el=>{if(el.closest('#page-about')||el.dataset.page==='about')return;if(!el.disabled){temporarilyDisabled.add(el);el.disabled=true;}});}
  if(!value){temporarilyDisabled.forEach(el=>el.disabled=false);temporarilyDisabled.clear();}
  working=value;document.body.classList.toggle('working',value);
}
function attrs(scope,id,field){return `data-scope="${h(scope)}" data-id="${h(id)}" data-field="${h(field)}"`;}
function input(scope,id,field,value,{readOnly=false,name=false,label='',type='text'}={}){
  return `<input ${attrs(scope,id,field)} value="${h(value)}" type="${type}" ${type==='text'&&!name?'inputmode="decimal"':''} ${readOnly?'readonly':''} class="${name?'name':''}" aria-label="${h(label||field)}">`;
}
function select(scope,id,field,value,options,disabled=false){
  const entries=options.map(x=>Array.isArray(x)?x:[x,x]);
  if(!entries.some(x=>String(x[0])===String(value)))entries.unshift([value,'Missing: '+value]);
  return `<select ${attrs(scope,id,field)} ${disabled?'disabled':''} aria-label="${h(field)}">${entries.map(([v,l])=>`<option value="${h(v)}" ${String(v)===String(value)?'selected':''}>${h(l)}</option>`).join('')}</select>`;
}
function check(scope,id,field,value,label,disabled=false){return `<label class="check"><input type="checkbox" ${attrs(scope,id,field)} ${value?'checked':''} ${disabled?'disabled':''}>${h(label)}</label>`;}
function field(label,control){return `<label>${h(label)}${control}</label>`;}
function pointOptions(){return recipe.points.map(p=>[p.id,p.name]);}
function flangeOptions(){return [...Object.keys(recipe.defaults.flanges), 'Custom'];}
function flange(f){return {...(recipe.defaults.flanges[f.preset==='DN150CF'?'DN160CF':f.preset]||{}),...((f.deviate||f.preset==='Custom')?f.overrides:{})};}
function tube(f){
  let name=f.tube==='default'?recipe.defaults.preferred_tubes[f.preset]:f.tube;
  const stock=recipe.defaults.tubes[name];
  if(stock)return {od:num(stock.od),wall:num(stock.wall),id:num(stock.od)-2*num(stock.wall)};
  const wall=num(f.tube_wall),od=num(f.tube_diameter)+(f.tube_basis==='id'?2*wall:0);return {od,wall,id:od-2*wall};
}
function tubeOptions(f){return [['default','Project default'],...Object.entries(recipe.defaults.tubes).map(([id,t])=>[id,`${t.flange}: ${t.od} × ${t.wall}`]),['Custom','Custom']];}
function rowActions(scope,row){return `<button data-action="preview" data-row="${h(row.id)}" title="Preview this row in chamber context">Preview</button><button data-action="build" data-row="${h(row.id)}" title="Build this row and its dependencies">Build</button><button data-action="expand" data-row="${h(row.id)}" aria-label="${expanded.has(row.id)?'Collapse':'Expand'} ${h(row.name)}">${expanded.has(row.id)?'−':'+'}</button><span class="status" data-status="${h(row.id)}">${h(statuses[row.id]||'Not built')}</span>`;}
function invalid(row){return (row.kind!=='existing'&&!row.endpoint&&!recipe.points.some(p=>p.id===row.point))||(row.toward&&!recipe.points.some(p=>p.id===row.toward))||(row.target&&row.target!=='auto'&&![...recipe.bodies,...recipe.ports].some(p=>p.id===row.target));}
function rowClass(row){return invalid(row)||errors.some(x=>x.row===row.id)||diagnostics.some(x=>x.row===row.id&&x.level==='error')?'invalid':diagnostics.some(x=>x.row===row.id&&x.level==='warning')?'warning':'';}
function rowTail(scope,row){return `<button class="row-end" data-action="duplicate" data-scope="${scope}" data-row="${h(row.id)}" ${row.endpoint?'disabled':''}>Copy</button> <button class="row-end danger" data-action="delete-row" data-scope="${scope}" data-row="${h(row.id)}" ${row.endpoint?'disabled':''}>Delete</button>`;}
function numberCell(f,index){return `<div class="number-control">${input('port',f.id,'number',f.number??'',{label:'Flange number'})}<span><button data-action="move-up" data-row="${h(f.id)}" aria-label="Move ${h(f.name)} up" ${index===0?'disabled':''}>↑</button><button data-action="move-down" data-row="${h(f.id)}" aria-label="Move ${h(f.name)} down" ${index===recipe.ports.length-1?'disabled':''}>↓</button></span></div>`;}
function sortPortNumbers(){
  const n=f=>/^[0-9]+$/.test(String(f.number??'').trim())&&BigInt(String(f.number).trim())>0n?BigInt(String(f.number).trim()):null;
  recipe.ports.sort((a,b)=>{const x=n(a),y=n(b);if(x===null&&y!==null)return 1;if(x!==null&&y===null)return -1;if(x!==null&&y!==null&&x!==y)return x<y?-1:1;return String(a.name).localeCompare(String(b.name),undefined,{sensitivity:'base'});});
}
function htmlTable(headers,rows,cls=''){return `<table class="${cls}"><thead><tr>${headers.map(x=>`<th>${h(x)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`;}
function format(v){return Number.isFinite(v)?String(Math.round(v*10000)/10000):'—';}

function renderPoints(){
  $('#points').innerHTML=htmlTable(['Name','X (mm)','Y (mm)','Z (mm)','Visible',''],recipe.points.map(p=>`<tr data-row-id="${h(p.id)}"><td>${input('point',p.id,'name',p.name,{name:true})}</td>${['x','y','z'].map(k=>`<td>${input('point',p.id,k,p[k])}</td>`).join('')}<td>${check('point',p.id,'visible',p.visible,'Show')}</td><td>${rowTail('point',p)}</td></tr>`).join(''),'points-table');
}
function bodyDetails(b){
  const s='body',id=b.id;let fields=[];
  if(b.kind==='existing'){
    return `<div class="toolbar"><button data-action="pick_source" data-row="${h(id)}">Select / replace solid</button><button data-action="pick_cavity" data-row="${h(id)}">Select optional cavity solid</button><strong>${h(b.source_name||'No solid selected')}</strong><span>${h(b.cavity_name||'')}</span></div><p class="detail-note">Copies the selected placement. Use bounded manual necks for ports on imported geometry. Export a recipe ZIP to carry the snapshot.</p>`;
  }
  if(b.kind!=='sphere')fields.push(...['azimuth','elevation','roll'].map(k=>field(k+' (°)',input(s,id,k,b[k]))));
  if(b.kind==='sphere'||b.kind==='tube'){
    fields.push(field('Diameter basis',select(s,id,'basis',b.basis,[['id','Inner diameter + wall'],['od','Outer diameter + wall']])),field('Driving diameter (mm)',input(s,id,'diameter',b.diameter)),field('Wall (mm)',input(s,id,'wall',b.wall)));
    const od=num(b.diameter)+(b.basis==='id'?2*num(b.wall):0),inside=od-2*num(b.wall);
    fields.push(`<div class="detail-note">OD <strong>${format(od)}</strong> · ID <strong>${format(inside)}</strong> mm</div>`);
  }
  if(b.kind==='tube'){
    fields.push(field('Endpoint s− (mm)',input(s,id,'s_min',b.s_min)),field('Endpoint s+ (mm)',input(s,id,'s_max',b.s_max)));
    for(const end of ['minus','plus']){
      fields.push(field(end+' end',select(s,id,'end_'+end,b['end_'+end],[['open','None / open'],['plate','Plate'],['flange','Flange']])));
      if(b['end_'+end]==='plate')fields.push(field(end+' cap thickness',input(s,id,'cap_'+end,b['cap_'+end])));
      if(b['end_'+end]==='flange')fields.push(field(end+' flange',select(s,id,'flange_'+end,b['flange_'+end],Object.keys(recipe.defaults.flanges))));
    }
  }
  if(b.kind==='box'){
    fields.push(field('Wall (mm)',input(s,id,'wall',b.wall)));
    for(const [key,label] of [['x','u'],['y','v'],['z','w']])for(const end of ['min','max'])fields.push(field(`Inner ${label} ${end} (mm)`,input(s,id,key+'_'+end,b[key+'_'+end])));
  }
  return `<div class="field-grid">${fields.join('')}</div><p class="detail-note">${b.kind==='tube'?'Endpoint planes are open tube ends, outer cap faces or flange mating faces. Each end is independent.':b.kind==='box'?'Offsets define the inner cavity in the local u/v/w frame; w follows the azimuth/elevation axis.':'The centre is the referenced point; outside diameter follows from ID and wall thickness.'}</p>`;
}
function renderBodies(){
  $('#bodies').innerHTML=recipe.bodies.length?htmlTable(['Preview / build','Name','Shape','Reference point','Included',''],recipe.bodies.map(b=>`<tr class="${rowClass(b)}" data-row-id="${h(b.id)}"><td class="actions">${rowActions('body',b)}</td><td>${input('body',b.id,'name',b.name,{name:true})}</td><td>${select('body',b.id,'kind',b.kind,[['sphere','Sphere'],['tube','Tube'],['box','Cuboid'],['existing','Existing solid']])}</td><td>${b.kind==='existing'?'<span class="hint">Placed snapshot</span>':select('body',b.id,'point',b.point,pointOptions())}</td><td>${check('body',b.id,'enabled',b.enabled,'Build')}</td><td>${rowTail('body',b)}</td></tr>${expanded.has(b.id)?`<tr class="details-row"><td colspan="6">${bodyDetails(b)}</td></tr>`:''}`).join('')):'<div class="empty">Add a sphere, tube, cuboid or existing solid to start the main chamber.</div>';
}
function portDetails(f){
  const id=f.id,s='port',d=flange(f),t=tube(f);let fields=[];
  fields.push(field('Roll (°)',input(s,id,'roll',f.roll)),check(s,id,'enabled',f.enabled,'Include flange'));
  if(!f.endpoint){
    fields.push(field('Tube',select(s,id,'tube',f.tube,tubeOptions(f))));
    if(f.tube==='Custom'||(f.tube==='default'&&!recipe.defaults.preferred_tubes[f.preset]))fields.push(field('Tube size basis',select(s,id,'tube_basis',f.tube_basis,[['od','OD + wall'],['id','ID + wall']])),field('Tube driving diameter',input(s,id,'tube_diameter',f.tube_diameter)),field('Tube wall',input(s,id,'tube_wall',f.tube_wall)));
    fields.push(field('Neck extent',select(s,id,'neck_mode',f.neck_mode,[['auto','Automatic to cavity'],['manual','Manual length from flange back']])));
    if(f.neck_mode==='manual')fields.push(field('Neck length (mm)',input(s,id,'neck_length',f.neck_length)));
    else fields.push(field('Attachment target',select(s,id,'target',f.target,[['auto','Automatic'],...recipe.bodies.map(b=>[b.id,b.name]),...recipe.ports.filter(p=>p.id!==id&&!p.endpoint).map(p=>[p.id,'Neck: '+p.name])])));
    fields.push(field('Flange bore (blank = tube ID)',input(s,id,'bore',f.bore??'')),field('Aim toward point (optional)',select(s,id,'toward',f.toward||'',[['','Use table angles'],...pointOptions()])));
  }
  for(const key of ['knife','recess','gasket_od','gasket_id','gasket_t'])fields.push(field(labels[key]+' (mm)',input(s,id,'override.'+key,d[key],{readOnly:!f.deviate&&f.preset!=='Custom'})));
  const x=resolved[id];
  return `<div class="field-grid">${fields.join('')}</div><p class="detail-note">${f.endpoint?'Position and tube dimensions follow the parent tube endpoint. Change the end treatment in the body row to remove this flange.':`Tube OD ${format(t.od)} · ID ${format(t.id)} · wall ${format(t.wall)} mm. Necks belong to Main chamber.`}${x?` Face centre: ${x.face.map(format).join(', ')} mm. Normal: ${x.n.map(format).join(', ')}.`:''}</p>${f.configuration==='rotatable'?'<p class="detail-note">Two schematic ring bodies in one flange component. Roll sets bolt-ring orientation; retaining-lip geometry is supplier-specific.</p>':''}`;
}
function renderPorts(){
  $('#flange-angle-note').textContent='Azimuth: angle from +X (negative selects the opposite Y half). Elevation: rotation around X, positive toward +Z on either half.';
  const angleLabels=['Azimuth °','Elevation °'];
  $('#ports').innerHTML=recipe.ports.length?htmlTable(['Preview / build','Flange #','Component name','Point',...angleLabels,'Face distance','Flange','Configuration','Deviate','OD','Thickness','Bolt circle','# bolts','Hole Ø',''],recipe.ports.map((f,index)=>{
    const d=flange(f),readOnly=!f.deviate&&f.preset!=='Custom';
    const directionSource=f.endpoint?'From tube':f.toward?'By point':null;
    return `<tr class="${rowClass(f)}" data-row-id="${h(f.id)}"><td class="actions">${rowActions('port',f)}${diagnostics.some(x=>x.row===f.id&&x.level==='merge')?'<span class="badge merge">Merged neck</span>':''}</td><td class="number-cell">${numberCell(f,index)}</td><td>${input('port',f.id,'name',f.name,{name:true,readOnly:!!f.endpoint})}</td><td>${select('port',f.id,'point',f.point,pointOptions(),!!f.endpoint)}</td><td>${input('port',f.id,'azimuth',directionSource??f.azimuth,{readOnly:!!directionSource,label:angleLabels[0]})}</td><td>${input('port',f.id,'elevation',directionSource??f.elevation,{readOnly:!!directionSource,label:angleLabels[1]})}</td><td>${input('port',f.id,'distance',f.endpoint?'From endpoint':f.distance,{readOnly:!!f.endpoint})}</td><td>${select('port',f.id,'preset',f.preset,flangeOptions(),!!f.endpoint)}</td><td>${select('port',f.id,'configuration',f.configuration,[['inline','Fixed inline'],['straddled','Fixed straddled'],['rotatable','Rotatable']])}</td><td>${check('port',f.id,'deviate',f.deviate,'Edit',f.preset==='Custom')}</td>${['od','thickness','pcd','bolts','hole'].map(k=>`<td>${input('port',f.id,'override.'+k,d[k],{readOnly})}</td>`).join('')}<td>${rowTail('port',f)}</td></tr>${expanded.has(f.id)?`<tr class="details-row"><td colspan="16">${portDetails(f)}</td></tr>`:''}`;
  }).join(''),'ports-table'):'<div class="empty">Add a flange to define its face position and connecting tube.</div>';
}
function renderOptions(){
  $('#view-options').innerHTML=[['show_points','Points'],['show_axes','Port axes'],['gasket_features','Model gasket features'],['fasteners','Model fasteners'],['tool_clearance','Show tool clearance']].map(([k,l])=>check('defaults','',k,recipe.defaults[k],l)).join('')+'<span class="hint">Apply with Preview / Build.</span>';
}
function renderDefaults(){
  $('#theme-button').textContent=recipe.defaults.theme==='dark'?'Switch to light mode':'Switch to dark mode';
  $('#default-options').innerHTML=[['seal_depth','Schematic recess depth (mm)'],['tip_depth','Schematic knife depth (mm)'],['gasket_standoff','Gasket outer-face offset (mm)'],['bolt_length','Minimum displayed bolt length (mm)'],['fastener_diameter','Bolt Ø (0 = infer from hole)'],['tool_diameter','Tool envelope diameter (mm)'],['tool_length','Tool approach length (mm)'],['gap','Optional flange-gap threshold (mm)']].map(([k,l])=>field(l,input('defaults','',k,recipe.defaults[k]))).join('')+check('defaults','','proximity_check',recipe.defaults.proximity_check,'Check minimum flange gap');
  $('#flange-defaults').innerHTML=htmlTable(['Size',...fk.map(k=>labels[k])],Object.entries(recipe.defaults.flanges).map(([id,d])=>`<tr><td>${h(id)}</td>${fk.map(k=>`<td>${input('flange-default',id,k,d[k])}</td>`).join('')}</tr>`).join(''),'defaults-table');
  $('#tube-defaults').innerHTML=htmlTable(['Tube preset','Flange','Tube OD','Wall','Calculated ID'],Object.entries(recipe.defaults.tubes).map(([id,t])=>`<tr><td>${h(id)}</td><td>${h(t.flange)}</td><td>${input('tube-default',id,'od',t.od)}</td><td>${input('tube-default',id,'wall',t.wall)}</td><td>${format(num(t.od)-2*num(t.wall))}</td></tr>`).join(''),'defaults-table');
  $('#preferred-tubes').innerHTML=Object.keys(recipe.defaults.flanges).map(key=>field(key+' preferred tube',select('preferred',key,'value',recipe.defaults.preferred_tubes[key]||'Custom',[...Object.entries(recipe.defaults.tubes).filter(([id,t])=>t.flange===key).map(([id,t])=>[id,`${t.od} × ${t.wall}`]),['Custom','Enter tube per row']]))).join('');
}
function renderIssues(){
  const names=Object.fromEntries([...recipe.points,...recipe.bodies,...recipe.ports].map(r=>[r.id,r.name]));
  const all=[...errors.map(x=>({...x,level:'error'})),...diagnostics];
  $('#issues').innerHTML=all.length?all.map(x=>`<div class="issue ${h(x.level)}"><strong>${h(names[x.row]||'Chamber')}</strong> — ${h(x.message)}${x.other?` (${h(names[x.other]||x.other)})`:''}</div>`).join(''):'<span class="hint">No reported input issues. Preview evaluates solid geometry; tool access remains a visual check.</span>';
  $$('[data-status]').forEach(el=>el.textContent=statuses[el.dataset.status]||'Not built');
  $$('[data-row-id]').forEach(el=>{
    const row=[...recipe.bodies,...recipe.ports].find(x=>x.id===el.dataset.rowId);
    if(row)el.className=rowClass(row);
  });
  const active=recipe.ports.filter(x=>x.enabled).length;
  $('#counts').textContent=`${recipe.points.length} points · ${recipe.bodies.length} shapes · ${active} flanges`;
}
function renderInventory(){
  $('#inventory-count').textContent=`(${inventory.length})`;
  $('#inventory').innerHTML=inventory.length?inventory.map(x=>`<div class="inventory-item"><span><strong>${h(x.name)}</strong><br><small>${h(x.kind)}</small></span><button data-action="highlight" data-token="${h(x.token)}">Highlight</button><button class="danger" data-action="delete_geometry" data-token="${h(x.token)}" data-name="${h(x.name)}">Delete…</button></div>`).join(''):'<div class="empty">No other geometry found.</div>';
}
function renderAll(){
  if(!recipe||working)return;
  // A text-input blur can fire between pointerdown and click. Keep the clicked
  // row button in the DOM until its click has been delivered.
  if(pointerHeld){renderPending=true;return;}
  const focused=document.activeElement;const key=focused?.dataset?.field?{scope:focused.dataset.scope,id:focused.dataset.id,field:focused.dataset.field}:null;
  let selection=null;try{selection=[focused.selectionStart,focused.selectionEnd];}catch{}
  document.documentElement.dataset.theme=recipe.defaults.theme==='dark'?'dark':'light';
  $('#chamber-name').value=recipe.name;
  renderPoints();renderBodies();renderPorts();renderOptions();renderDefaults();renderIssues();renderInventory();
  $('#saved').innerHTML='<option value="">Current draft</option>'+saved.map(x=>`<option value="${h(x.id)}" ${x.id===recipe.id?'selected':''}>${h(x.name)}</option>`).join('');
  if(key){const el=$$('[data-field]').find(x=>x.dataset.scope===key.scope&&x.dataset.id===key.id&&x.dataset.field===key.field);if(el){el.focus({preventScroll:true});try{if(selection&&selection[0]!=null)el.setSelectionRange(...selection);}catch{}}}
}

function applyResult(data,{render=true}={}){
  if(data.recipe){recipe=data.recipe;diagnostics=[];errors=[];resolved={};expanded.clear();}
  if(data.catalog)catalog=data.catalog;
  if(data.doc_key)docKey=data.doc_key;
  if(data.statuses)statuses=data.statuses;
  if(data.resolved)resolved=data.resolved;
  if(data.errors)errors=data.errors;
  if(data.diagnostics)diagnostics=data.diagnostics;
  if(data.inventory)inventory=data.inventory;
  if(data.saved)saved=data.saved;
  if(data.document)$('#document').textContent=data.document;
  if(data.version)$('#version').textContent=data.version;
  if(data.message)notice(data.message,'success');
  if(render)renderAll();else renderIssues();
}

function staleRequest(){return Object.assign(new Error('A newer document context is active.'),{code:'stale'});}
function resync(){
  uiEpoch++;clearTimeout(saveTimer);clearTimeout(validationTimer);clearTimeout(reloadTimer);
  pointerHeld=false;renderPending=false;docKey='';busy(true);notice('Loading the active Fusion document…','busy');
  const epoch=uiEpoch;reloadTimer=setTimeout(()=>bootstrap(0,epoch),0);
}
function request(action,extra={}){
  if(offline)return offlineRequest(action,extra);
  const epoch=uiEpoch,key=docKey,payload=JSON.stringify({doc_key:key,...(['bootstrap','copy_text'].includes(action)?{}:{recipe}),...extra});
  const run=async()=>{
    if(epoch!==uiEpoch)throw staleRequest();
    const raw=await window.adsk.fusionSendData(action,payload);
    if(epoch!==uiEpoch)throw staleRequest();
    const response=typeof raw==='string'?JSON.parse(raw):raw;
    if(!response?.ok)throw Object.assign(new Error(response?.error||'Fusion returned an invalid response.'),{row:response?.row,log:response?.log,code:response?.code});
    if(action!=='bootstrap'&&response.result?.doc_key!==undefined&&response.result.doc_key!==key)throw Object.assign(staleRequest(),{code:'document_changed'});
    return response.result||{};
  };
  const pending=bridgeQueue.then(run,run);bridgeQueue=pending.catch(()=>{});return pending;
}
function requestError(e){
  if(e.code==='stale')return;
  if(e.code==='document_changed'){resync();return;}
  if(e.code==='busy'){busy(true);notice('Waiting for the current Fusion operation…','busy');return;}
  busy(false);notice(e.message+(e.log?'\nLog: '+e.log:''),'error');
  if(e.row){errors=[{row:e.row,message:e.message}];renderIssues();}
}

async function perform(action,extra={}){
  if(working)return;
  clearTimeout(saveTimer);clearTimeout(validationTimer);
  const long=['build','preview','clear_preview','delete_geometry','pick_source'].includes(action);
  if(long){busy(true);notice(action==='preview'?'Preparing chamber preview…':'Working in Fusion…','busy');}
  try{
    const data=await request(action,extra);
    if(!data.queued){busy(false);applyResult(data);if(action==='clear_preview')notice('Preview cleared. Built geometry restored.');}
  }catch(e){requestError(e);}
}

function dirty(){
  diagnostics=[];errors=[];
  for(const row of [...recipe.bodies,...recipe.ports])if(statuses[row.id]==='Up to date')statuses[row.id]='Changed';
  $('#save-status').textContent='Draft changed — Preview or Build to apply.';
  clearTimeout(saveTimer);clearTimeout(validationTimer);
  saveTimer=setTimeout(async()=>{
    if(working)return;
    try{await request('save');$('#save-status').textContent=offline?'Interface preview — no Fusion document connected.':'Draft stored. Save the Fusion document to keep it on disk.';}catch(e){requestError(e);}
  },600);
  validationTimer=setTimeout(async()=>{
    if(working)return;
    try{const d=await request('validate');applyResult(d,{render:false});}catch(e){requestError(e);}
  },850);
}

function newPoint(){
  let i=0,name;const names=new Set(recipe.points.map(p=>p.name));
  do{let n=i++;name='';do{name=String.fromCharCode(65+n%26)+name;n=Math.floor(n/26)-1;}while(n>=0);}while(names.has(name));
  return {id:uid('p'),name,x:0,y:0,z:0,visible:true};
}
function makeBody(kind){return {id:uid('b'),name:({sphere:'Sphere',tube:'Tube',box:'Cuboid',existing:'Existing solid'})[kind],kind,point:recipe.points[0]?.id||'',enabled:true,azimuth:0,elevation:0,roll:0,basis:'id',diameter:200,wall:3,s_min:-100,s_max:100,end_minus:'open',end_plus:'open',cap_minus:3,cap_plus:3,flange_minus:'DN200CF',flange_plus:'DN200CF',x_min:-100,x_max:100,y_min:-75,y_max:75,z_min:-75,z_max:75,token:'',source_name:'',cavity_token:''};}
function makePort(){return {id:uid('f'),number:'',name:'Port '+(recipe.ports.length+1),point:recipe.points[0]?.id||'',enabled:true,azimuth:0,elevation:0,roll:0,distance:160,preset:'DN40CF',configuration:'straddled',deviate:false,overrides:{},tube:'default',tube_basis:'od',tube_diameter:38,tube_wall:1.5,target:'auto',neck_mode:'auto',neck_length:70,bore:null};}
function syncEndpoints(){
  const wanted=new Set();
  for(const b of recipe.bodies)if(b.kind==='tube')for(const end of ['minus','plus'])if(b['end_'+end]==='flange'){
    const id=b.id+'_'+end;wanted.add(id);let f=recipe.ports.find(x=>x.id===id);
    if(!f){f=makePort();f.id=id;recipe.ports.push(f);}
    Object.assign(f,{endpoint:{body:b.id,end},point:b.point,name:b.name+' / '+end,preset:b['flange_'+end],enabled:b.enabled});
  }
  recipe.ports=recipe.ports.filter(f=>!f.endpoint||wanted.has(f.id));
}

function changeField(el,finalize=true){
  const {scope,id,field:key}=el.dataset;let value=el.type==='checkbox'?el.checked:el.value;
  const list={point:'points',body:'bodies',port:'ports'}[scope];
  if(list){
    const row=recipe[list].find(x=>x.id===id);if(!row)return;
    if(scope==='port'&&key==='deviate'&&!value&&Object.keys(row.overrides||{}).length){if(!confirm('Discard this row’s dimension overrides and inherit the project defaults?')){el.checked=true;return;}row.overrides={};}
    if(scope==='port'&&key==='preset'&&value==='Custom'){row.overrides=clone(flange(row));row.deviate=true;}
    else if(scope==='port'&&key==='preset'&&value!==row.preset){row.overrides={};row.deviate=false;}
    if(scope==='port'&&key==='bore'&&value==='')value=null;
    if(key.startsWith('override.')){row.overrides??={};row.overrides[key.slice(9)]=value;}
    else row[key]=value;
  }else if(scope==='defaults')recipe.defaults[key]=value;
  else if(scope==='flange-default')recipe.defaults.flanges[id][key]=value;
  else if(scope==='tube-default')recipe.defaults.tubes[id][key]=value;
  else if(scope==='preferred')recipe.defaults.preferred_tubes[id]=value;
  // Retain keystrokes before blur moves focus to another input. Replacing the
  // table synchronously on change can detach the field receiving that focus.
  if(!finalize)return;
  syncEndpoints();dirty();setTimeout(renderAll,0);
}

document.addEventListener('pointerdown',()=>{pointerHeld=true;},true);
function releasePointer(){pointerHeld=false;if(renderPending){renderPending=false;setTimeout(renderAll,0);}}
document.addEventListener('pointerup',releasePointer,true);
document.addEventListener('pointercancel',releasePointer,true);
document.addEventListener('input',e=>{
  const el=e.target;
  if(el.tagName==='INPUT'&&el.type!=='checkbox'&&(el.dataset.field||el.id==='chamber-name')){
    clearTimeout(saveTimer);clearTimeout(validationTimer);
    if(el.dataset.field)changeField(el,false);
    else if(recipe)recipe.name=el.value;
  }
});
document.addEventListener('change',e=>{
  const el=e.target;if(el.dataset.field)changeField(el);
  else if(el.id==='chamber-name'){recipe.name=el.value;dirty();}
  else if(el.id==='saved'&&el.value)perform('load',{id:el.value});
});
document.addEventListener('click',async e=>{
  const page=e.target.closest('[data-page]');
  if(page){$$('[data-page]').forEach(x=>x.classList.toggle('active',x===page));$$('main>section').forEach(x=>x.hidden=x.id!=='page-'+page.dataset.page);return;}
  const el=e.target.closest('[data-action]');if(!el||!recipe||working)return;
  let action=el.dataset.action;const row=el.dataset.row;const scope=el.dataset.scope;
  if(action==='expand'){expanded.has(row)?expanded.delete(row):expanded.add(row);renderAll();return;}
  if(action==='add-point'){recipe.points.push(newPoint());dirty();renderAll();return;}
  if(action==='add-body'||action==='add-port'){
    if(!recipe.points.length)recipe.points.push(newPoint());
    const r=action==='add-body'?makeBody($('#new-body-kind').value):makePort();recipe[action==='add-body'?'bodies':'ports'].push(r);expanded.add(r.id);dirty();renderAll();return;
  }
  if(action==='duplicate'){
    const key={point:'points',body:'bodies',port:'ports'}[scope],index=recipe[key].findIndex(x=>x.id===row);const r=clone(recipe[key][index]);r.id=uid(scope[0]);r.name+=' copy';if(scope==='port')r.number='';recipe[key].splice(index+1,0,r);syncEndpoints();dirty();renderAll();return;
  }
  if(action==='move-up'||action==='move-down'){
    const i=recipe.ports.findIndex(f=>f.id===row),j=i+(action==='move-up'?-1:1);
    if(i>=0&&j>=0&&j<recipe.ports.length){const [f]=recipe.ports.splice(i,1);recipe.ports.splice(j,0,f);dirty();renderAll();}return;
  }
  if(action==='sort-ports'){sortPortNumbers();dirty();renderAll();return;}
  if(action==='delete-row'){
    const key={point:'points',body:'bodies',port:'ports'}[scope];const r=recipe[key].find(x=>x.id===row);
    const refs=[...recipe.bodies,...recipe.ports].filter(x=>(x.kind!=='existing'&&x.point===row)||x.toward===row||x.target===row);
    const text=refs.length?`Delete ${r.name} anyway? Referenced by ${refs.map(x=>x.name).join(', ')}. Those rows will require repair.`:`Remove ${r.name} from the recipe? Build / update all will remove its generated geometry.`;
    if(!confirm(text))return;recipe[key]=recipe[key].filter(x=>x.id!==row);syncEndpoints();dirty();renderAll();return;
  }
  if(action==='theme'){recipe.defaults.theme=recipe.defaults.theme==='dark'?'light':'dark';dirty();renderAll();return;}
  if(action==='reset-defaults'){
    if(!confirm('Reset flange and tube catalog defaults for this chamber? Explicit row overrides are preserved.'))return;
    recipe.defaults.flanges=clone(catalog.flanges);recipe.defaults.tubes=clone(catalog.tubes);dirty();renderAll();return;
  }
  if(['new','example','import'].includes(action)&&!confirm('Replace the current draft? Export it first if you need to keep it. Built chambers stay in the document.'))return;
  if(action==='export')action=$('#export-format').value;
  if(action==='save-app-defaults'){await perform(action);return;}
  if(action==='delete_geometry'&&!confirm(`Delete “${el.dataset.name}” from this Fusion document? Deleting a body affects its component definition and may affect every instance. Fusion Undo can reverse the operation.`))return;
  const extra={};if(row)extra.row=row;
  if(el.dataset.token)extra.token=el.dataset.token;
  if(action==='pick_cavity'){action='pick_source';extra.cavity=true;}
  await perform(action,extra);
});

window.fusionJavaScriptHandler={handle(action,raw){
  try{
    const data=JSON.parse(raw||'{}'),epoch=uiEpoch;
    if(action==='reload'){resync();return 'OK';}
    // Return to Fusion before processing its callback. Never call back into
    // fusionSendData on the sendInfoToHTML stack.
    setTimeout(()=>{
      if(epoch!==uiEpoch||(data.doc_key!==undefined&&data.doc_key!==docKey))return;
      if(action==='progress')notice(data.message,'busy');
      else if(action==='completed'){busy(false);applyResult(data);}
      else if(action==='failed')requestError(Object.assign(new Error(data.message),{row:data.row,log:data.log}));
    },0);
    return 'OK';
  }catch(e){notice(e.message,'error');return 'FAILED';}
}};

async function offlineRequest(action,extra){
  if(action==='save'||action==='validate'||action==='refresh')return {};
  if(action==='example')return {recipe:clone(window.UHV_DEMO.recipe),message:'Example loaded in interface-preview mode.'};
  if(action==='new'){const r=clone(window.UHV_DEMO.recipe);r.id=uid('chamber');r.name='UHV chamber';r.bodies=[];r.ports=[];return {recipe:r};}
  if(action==='export_json'){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(recipe,null,2)],{type:'application/json'}));a.download='UHV_chamber.json';a.click();URL.revokeObjectURL(a.href);return {message:'Recipe JSON downloaded.'};}
  return {message:'This is an interface preview. Open the add-in in Autodesk Fusion to '+action.replaceAll('_',' ')+'.'};
}

async function bootstrap(attempt=0,epoch=uiEpoch){
  if(epoch!==uiEpoch)return;
  try{
    if(!window.adsk?.fusionSendData){
      if(attempt<8){reloadTimer=setTimeout(()=>bootstrap(attempt+1,epoch),200);return;}
      offline=true;busy(false);recipe=clone(window.UHV_DEMO.recipe);catalog=clone(window.UHV_DEMO.catalog);$('#document').textContent='Interface preview · no Fusion connection';renderAll();notice('Interface preview — geometry builds run inside Autodesk Fusion.');return;
    }
    offline=false;busy(true);const data=await request('bootstrap');
    if(epoch!==uiEpoch)return;
    busy(false);applyResult(data);
    if(data.available===false){docKey=data.doc_key||'';busy(true);return;}
    notice('Ready. Build will ask to switch to Hybrid if needed.','success');
  }catch(e){
    if(e.code==='stale')return;
    if(e.code==='document_changed'){resync();return;}
    busy(true);notice(e.code==='busy'?'Waiting for Fusion to finish; the palette will refresh automatically.':'Cannot connect to Fusion: '+e.message+' Reopen the palette to retry.',e.code==='busy'?'busy':'error');
  }
}
bootstrap();
