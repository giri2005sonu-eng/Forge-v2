const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const state = {meta:null,catalog:[],buildResponse:null,activeBuild:null,rules:[],settings:{},discoveries:[]};
const categoryLabels = {controller:'Controller',driver:'Motor driver',motor:'Motor',battery:'Battery',sensor:'Sensor',chassis:'Chassis'};
const money = n => n == null || Number.isNaN(Number(n)) ? '—' : '₹' + Number(n).toLocaleString('en-IN',{maximumFractionDigits:0});
const num = (n,d=1) => n == null || !Number.isFinite(Number(n)) ? '—' : Number(n).toFixed(d);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(url, options={}) { const res=await fetch(url,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}}); const type=res.headers.get('content-type')||''; let data; if(type.includes('application/json')) data=await res.json(); else data=await res.text(); if(!res.ok) throw new Error(data?.detail || data?.message || `Request failed (${res.status})`); return data; }
function toast(msg, type='') { const el=document.createElement('div');el.className='toast '+type;el.textContent=msg;$('#toastRegion').append(el);setTimeout(()=>el.remove(),4300); }
function notice(target,msg,type='') { const el=typeof target==='string'?$(target):target; if(!el)return;el.innerHTML=msg?`<div class="notice ${type}">${msg}</div>`:''; }
function setBusy(button,busy,label='Working…'){if(!button)return;if(busy){button.dataset.oldText=button.innerHTML;button.disabled=true;button.innerHTML=`<span class="loading-dot">···</span> ${label}`;}else{button.disabled=false;if(button.dataset.oldText)button.innerHTML=button.dataset.oldText;}}
function goto(page){$$('.page').forEach(p=>p.classList.toggle('active',p.id===`page-${page}`));$$('.nav-item[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));$('#crumbCurrent').textContent=({overview:'Overview',requirements:'Build planner',catalog:'Parts & sourcing',validation:'Validation lab',wiring:'Wiring & power',reports:'Reports & evidence',settings:'Settings & API keys'})[page]||page;window.scrollTo({top:0,behavior:'smooth'});if(page==='catalog')loadCatalog();if(page==='validation')loadRules();if(page==='settings')loadSettingsStatus();}
$$('.nav-item[data-page]').forEach(b=>b.addEventListener('click',()=>goto(b.dataset.page)));
$$('[data-goto]').forEach(b=>b.addEventListener('click',()=>goto(b.dataset.goto)));
$$('[data-example]').forEach(b=>b.addEventListener('click',()=>{$('#robotPrompt').value=b.dataset.example;goto('requirements');$('#robotPrompt').focus();}));
async function init(){try{const [meta,health]=await Promise.all([api('/api/meta'),api('/api/health')]);state.meta=meta;$('#sidebarStatus').textContent='API online · catalog ready';$('#metricParts').textContent=meta.catalog_count;$('#metricLive').textContent=`${meta.live_price_count} with live-scraped price`;$('#geminiStatus').textContent=meta.gemini_configured?'Configured':'Not configured';$('#geminiStatus').className=meta.gemini_configured?'state-on':'state-off';$('#tinyfishStatus').textContent=meta.tinyfish_configured?'Configured':'Not configured';$('#tinyfishStatus').className=meta.tinyfish_configured?'state-on':'state-off';populateCategorySelects(meta);await loadCatalog();await loadRules();await loadSettingsStatus();await healthCheck();$('#lastUpdated').textContent='Workspace synced · '+new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});}catch(e){$('#sidebarStatus').textContent='API unavailable';toast(`Could not connect to local API: ${e.message}`,'error');}}
function populateCategorySelects(meta){const cats=Object.keys(meta.categories||{});['catalogCategory','refreshCategory','discoverCategory','importCategory'].forEach(id=>{const el=$('#'+id);if(!el)return;const old=el.value;el.innerHTML=(id==='catalogCategory'?'<option value="">All categories</option>':'')+cats.map(c=>`<option value="${esc(c)}">${esc(categoryLabels[c]||c)}</option>`).join('');if(old)el.value=old;});}
async function loadCatalog(){try{const q=$('#catalogSearch')?.value||'';const category=$('#catalogCategory')?.value||'';const params=new URLSearchParams();if(q)params.set('q',q);if(category)params.set('category',category);const d=await api('/api/catalog?'+params);state.catalog=d.items||[];renderCatalog();populateRefreshParts();}catch(e){$('#catalogRows').innerHTML=`<tr><td colspan="7" class="empty-state">${esc(e.message)}</td></tr>`;}}
function renderCatalog(){const rows=$('#catalogRows');$('#catalogCount').textContent=`${state.catalog.length} component${state.catalog.length===1?'':'s'}`;if(!state.catalog.length){rows.innerHTML='<tr><td colspan="7" class="empty-state">No parts match this search.</td></tr>';return;}rows.innerHTML=state.catalog.map(p=>`<tr><td><div class="part-name"><span class="part-symbol">${p.category==='controller'?'⌘':p.category==='motor'?'◉':p.category==='sensor'?'◎':p.category==='battery'?'ϟ':p.category==='driver'?'▤':'◇'}</span><span><b>${esc(p.name)}</b><small>${esc(p.id)}</small></span></div></td><td>${esc(categoryLabels[p.category]||p.category)}</td><td>${esc(p.vendor||'Seed catalog')}</td><td><b>${money(p.price_value)}</b></td><td><span class="tag ${p.price_method==='scraped'?'pass':''}">${esc(p.price_method||'none').toUpperCase()}</span></td><td>${p.stock_value===true?'<span class="tag pass">IN STOCK</span>':p.stock_value===false?'<span class="tag fail">OUT OF STOCK</span>':'<span class="tag unknown">UNKNOWN</span>'}</td><td><button class="btn btn-small btn-outline" data-inspect="${esc(p.id)}">Inspect →</button></td></tr>`).join('');$$('[data-inspect]',rows).forEach(b=>b.addEventListener('click',()=>showPart(b.dataset.inspect)));}
function populateRefreshParts(){const cat=$('#refreshCategory')?.value||'';const items=state.catalog.filter(p=>!cat||p.category===cat);const el=$('#refreshParts');if(!el)return;const selected=new Set([...el.selectedOptions].map(o=>o.value));el.innerHTML=items.map(p=>`<option value="${esc(p.id)}">${esc(p.name)} · ${money(p.price_value)}</option>`).join('');[...el.options].forEach(o=>o.selected=selected.has(o.value));}
$('#catalogSearch').addEventListener('input',debounce(loadCatalog,220));$('#catalogCategory').addEventListener('change',loadCatalog);$('#refreshCategory').addEventListener('change',populateRefreshParts);
function debounce(fn,wait){let t;return(...a)=>{clearTimeout(t);t=setTimeout(()=>fn(...a),wait);};}
async function showPart(id){try{const p=await api('/api/part/'+encodeURIComponent(id));$('#modalTitle').textContent=p.name;const specs=Object.entries(p.specs||{});$('#modalBody').innerHTML=`<div id="sourcesBox" class="sources-box"></div><div class="eyebrow" style="margin:18px 0 9px">SPECIFICATIONS & EVIDENCE</div><div class="spec-grid"><div class="spec-item"><small>COMPONENT ID</small><b>${esc(p.id)}</b></div><div class="spec-item"><small>CATEGORY</small><b>${esc(categoryLabels[p.category]||p.category)}</b></div><div class="spec-item"><small>VENDOR</small><b>${esc(p.vendor)}</b></div><div class="spec-item"><small>PRICE</small><b>${money(p.price_value)} <span class="tag">${esc(p.price_method)}</span></b></div>${specs.map(([k,v])=>`<div class="spec-item"><small>${esc(k.replaceAll('_',' ').toUpperCase())}</small><b>${esc(v.value??'NOT FOUND')} ${esc(v.unit||'')}</b><small>${esc(v.evidence?.method||'')} ${v.evidence?.retrieved_at?'· '+esc(v.evidence.retrieved_at):''}</small>${v.evidence?.source_url?`<a class="source-link" href="${esc(v.evidence.source_url)}" target="_blank" rel="noopener">Open source ↗</a>`:''}${v.evidence?.quote?`<p>${esc(v.evidence.quote)}</p>`:''}</div>`).join('')}</div>${p.url?`<p><a class="source-link" href="${esc(p.url)}" target="_blank" rel="noopener">Open product listing ↗</a></p>`:''}`;$('#partModal').classList.remove('hidden');loadSources(p.id);}catch(e){toast(e.message,'error');}}
$('#closeModal').addEventListener('click',()=>$('#partModal').classList.add('hidden'));$('#partModal').addEventListener('click',e=>{if(e.target.id==='partModal')$('#partModal').classList.add('hidden')});
$('#parseBtn').addEventListener('click',async e=>{const btn=e.currentTarget;setBusy(btn,true,'Parsing brief…');notice('#parseNotes','');try{const d=await api('/api/parse',{method:'POST',body:JSON.stringify({prompt:$('#robotPrompt').value})});const r=d.requirements;$('#robotType').value=r.robot_type;$('#budget').value=r.budget_inr;$('#motors').value=r.motor_count;$('#runtime').value=r.min_runtime_h;$('#bluetooth').checked=r.needs_bluetooth;$('#channels').value=r.sensor_channels||0;$('#parseMode').textContent=d.parser==='gemini'?'Parsed with Gemini':'Parsed locally';notice('#parseNotes',d.notes.map(esc).join('<br>'));toast('Requirements parsed. Review the fields before building.');}catch(err){notice('#parseNotes',esc(err.message),'error');}finally{setBusy(btn,false);}});
function reqPayload(){const c=Number($('#channels').value||0);return{robot_type:$('#robotType').value,budget_inr:Number($('#budget').value),motor_count:Number($('#motors').value),min_runtime_h:Number($('#runtime').value),needs_bluetooth:$('#bluetooth').checked,sensor_channels:c||null};}
$('#buildBtn').addEventListener('click',async e=>{const btn=e.currentTarget;setBusy(btn,true,'Optimizing components…');notice('#buildMessage','');try{const d=await api('/api/build',{method:'POST',body:JSON.stringify(reqPayload())});state.buildResponse=d;state.activeBuild=d.chosen;renderBuild(d);updateOverview(d);renderValidation();renderPower();renderReports();if(d.chosen)toast(`Build ready · ${money(d.chosen.total)} total`);else toast(d.message||'No build could be selected.','error');}catch(err){notice('#buildMessage',esc(err.message),'error');toast(err.message,'error');}finally{setBusy(btn,false);}});
function statusLabel(status){return status==='verified'?'VERIFIED':status==='invalid'?'INVALID':'UNVERIFIED';}
function renderBuild(d){const target=$('#buildResult');if(!d.chosen){target.innerHTML=`<div class="panel"><h3>No compatible build found</h3><p class="panel-copy">${esc(d.message||'Try increasing the budget or reviewing requirements.')}</p>${d.excluded?.length?`<p class="panel-copy">${d.excluded.length} parts were excluded due to missing prices or stock information.</p>`:''}</div>`;notice('#buildMessage',esc(d.message||'No build found.'),'warn');return;}const b=d.chosen;const parts=Object.values(b.parts||{});target.innerHTML=`<div class="result-hero"><div><div class="eyebrow">BUILD RESULT / ${esc($('#robotType').selectedOptions[0].text.toUpperCase())}</div><h2>Your robot build sheet</h2><p>${d.evaluated.toLocaleString()} candidate combinations evaluated · ${b.counts.pass} checks passed · ${b.counts.unknown} unknown · ${b.counts.fail} failed</p></div><span class="result-status ${esc(b.status)}">● ${statusLabel(b.status)}</span></div><div class="result-metrics"><div class="result-metric"><small>PARTS SUBTOTAL</small><b>${money(b.parts_cost)}</b><em>Before shipping</em></div><div class="result-metric"><small>SHIPPING ESTIMATE</small><b>${money(b.shipping_total)}</b><em>Vendor-based estimate</em></div><div class="result-metric"><small>ESTIMATED TOTAL</small><b>${money(b.total)}</b><em>${b.budget_remaining>=0?money(b.budget_remaining)+' remaining':money(Math.abs(b.budget_remaining))+' over budget'}</em></div><div class="result-metric"><small>EST. RUNTIME</small><b>${b.power?num(b.power.runtime_typical_h,1)+' h':'Unknown'}</b><em>Modelled typical load</em></div></div><article class="panel"><div class="panel-head"><div><div class="eyebrow">PROCUREMENT LIST</div><h3>Bill of materials</h3></div><button class="btn btn-small btn-outline" data-export="bom.csv">Export CSV ↓</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>COMPONENT</th><th>QTY</th><th>UNIT PRICE</th><th>LINE TOTAL</th><th>DATA SOURCE</th></tr></thead><tbody>${parts.map(p=>`<tr><td><b>${esc(p.name)}</b><small style="display:block;color:#9a9f9f;margin-top:3px">${esc(p.id)}</small></td><td>${p.qty}</td><td>${money(p.price_value)}</td><td><b>${money(p.line_total)}</b></td><td><span class="tag ${p.price_method==='scraped'?'pass':''}">${esc(p.price_method.toUpperCase())}</span></td></tr>`).join('')}</tbody><tfoot><tr><td colspan="3"><b>Estimated total including shipping</b></td><td colspan="2"><b>${money(b.total)}</b></td></tr></tfoot></table></div></article>${b.shipping_rows?.length?`<article class="panel" style="margin-top:13px"><div class="panel-head"><div><div class="eyebrow">FULFILMENT</div><h3>Shipping estimate by vendor</h3></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th>VENDOR</th><th>SUBTOTAL</th><th>SHIPPING</th></tr></thead><tbody>${b.shipping_rows.map(r=>`<tr><td>${esc(r.vendor)}</td><td>${money(r.subtotal)}</td><td>${money(r.shipping)}</td></tr>`).join('')}</tbody></table></div></article>`:''}${d.naive?`<div class="callout"><span class="callout-mark">i</span><div><b>Why compatibility-first selection matters</b><p>Ignoring compatibility, the cheapest combination costs ${money(d.naive.parts_cost)} and has ${d.naive.counts.fail} failed checks. The selected build prioritizes validation over a misleading cheapest-parts total.</p></div></div>`:''}<div class="hero-actions" style="margin:14px 0 0"><button class="btn btn-primary" data-goto="validation">Review validation →</button><button class="btn btn-outline" data-goto="wiring">View wiring & power →</button><button class="btn btn-outline" data-goto="reports">Export reports →</button></div>`;target.querySelectorAll('[data-export]').forEach(b=>b.addEventListener('click',()=>downloadExport(b.dataset.export)));target.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>goto(b.dataset.goto)));}
function updateOverview(d){const b=d.chosen;$('#metricBuild').textContent=b?statusLabel(b.status):'None';$('#metricBuildSub').textContent=b?`${Object.keys(b.parts).length} categories selected`:'No compatible build selected';$('#metricChecks').textContent=b?`${b.counts.pass}/${b.counts.pass+b.counts.fail+b.counts.unknown}`:'—';$('#metricChecksSub').textContent=b?`${b.counts.fail} failed · ${b.counts.unknown} unknown`:'Run a build to validate';$('#metricTotal').textContent=b?money(b.total):'—';$('#metricBudgetSub').textContent=b?(b.budget_remaining>=0?money(b.budget_remaining)+' under budget':money(-b.budget_remaining)+' over budget'):'Set a budget to begin';}
async function loadRules(){try{const d=await api('/api/rules');state.rules=d.items||[];$('#rulesCount').textContent=`${state.rules.length} RULES`;$('#rulesRows').innerHTML=state.rules.map(r=>`<tr><td><span class="tag">${esc(r.id)}</span></td><td><b>${esc(r.title)}</b><small style="display:block;color:#9ca2a0;margin-top:3px">${esc(r.check||'')}</small></td><td>${esc(r.category)}</td><td>${esc((r.needs||[]).join(', '))}</td><td>${esc(r.when||'Always')}</td></tr>`).join('')||'<tr><td colspan="5" class="empty-state">No rules found.</td></tr>';}catch(e){$('#rulesRows').innerHTML=`<tr><td colspan="5">${esc(e.message)}</td></tr>`;}}
function renderValidation(){const d=state.buildResponse,b=d?.chosen;$('#validationSummary').classList.toggle('hidden',!!b);$('#checksPanel').classList.toggle('hidden',!b);if(!b){$('#swapFields').innerHTML='<span class="subtle">Generate a BOM first to compare alternatives.</span>';return;}$('#statusCounts').innerHTML=`<span class="tag pass">${b.counts.pass} PASS</span><span class="tag unknown">${b.counts.unknown} UNKNOWN</span><span class="tag fail">${b.counts.fail} FAIL</span>`;$('#checksList').innerHTML=b.checks.map(c=>`<div class="check-row"><div><span class="tag ${esc(c.status)}">${esc(c.status.toUpperCase())}</span></div><div class="check-main"><b>${esc(c.title)} <span style="color:#a4aaa7;font-weight:400">· ${esc(c.rule_id)}</span></b><p>${esc(c.message)}</p>${c.missing?.length?`<small>Missing inputs: ${esc(c.missing.join(', '))}</small>`:''}</div></div>`).join('');const categories=Object.keys(b.parts);$('#swapFields').innerHTML=categories.map(cat=>{const current=b.parts[cat];const choices=state.catalog.filter(p=>p.category===cat);return `<div class="field"><label>${esc(categoryLabels[cat]||cat)}</label><select data-swap-cat="${esc(cat)}">${choices.map(p=>`<option value="${esc(p.id)}" ${p.id===current.id?'selected':''}>${esc(p.name)} · ${money(p.price_value)}</option>`).join('')}</select></div>`}).join('');}
$('#simulateSwap').addEventListener('click',async e=>{if(!state.activeBuild){toast('Generate a BOM first.','error');return;}const btn=e.currentTarget;setBusy(btn,true,'Re-validating…');try{const part_ids={};$$('[data-swap-cat]').forEach(s=>part_ids[s.dataset.swapCat]=s.value);const d=await api('/api/swap',{method:'POST',body:JSON.stringify({part_ids})});const b=d.build;notice('#swapOutput',`<b>${statusLabel(b.status)}</b> · Total ${money(b.total)} · ${d.cost_delta>=0?'+':'−'}${money(Math.abs(d.cost_delta))} versus the current build<br>${b.counts.pass} pass · ${b.counts.unknown} unknown · ${b.counts.fail} fail${b.checks.filter(c=>c.status==='fail').length?'<br><br>'+b.checks.filter(c=>c.status==='fail').map(c=>esc(c.title)+': '+esc(c.message)).join('<br>'):''}`,b.counts.fail?'warn':'');}catch(err){notice('#swapOutput',esc(err.message),'error');}finally{setBusy(btn,false);}});
$('#runTests').addEventListener('click',async e=>{const btn=e.currentTarget;setBusy(btn,true,'Running tests…');try{const d=await api('/api/tests',{method:'POST',body:'{}'});const panel=$('#testResults');panel.classList.remove('hidden');panel.innerHTML=`<div class="panel-head"><div><div class="eyebrow">REGRESSION SUITE</div><h3>Deterministic validation tests</h3></div><span class="tag ${d.passed===d.total?'pass':'fail'}">${d.passed}/${d.total} PASSED</span></div><div class="test-result-summary"><span class="test-result-number">${d.passed}/${d.total}</span><span class="subtle">Seed catalog · offline test cases</span></div>${d.items.map(r=>`<div class="test-item"><span><b>${esc(r.name)}</b><small style="display:block;color:#999;margin-top:3px">Expected ${esc(r.expected)} · actual ${esc(r.actual)}</small>${r.fails?.length?`<small style="display:block;color:#a44">Failed: ${esc(r.fails.join(', '))}</small>`:''}</span><span class="tag ${r.ok?'pass':'fail'}">${r.ok?'PASS':'FAIL'}</span></div>`).join('')}`;toast(`Regression tests: ${d.passed}/${d.total} passed`,d.passed===d.total?'':'error');}catch(err){toast(err.message,'error');}finally{setBusy(btn,false);}});
function renderPower(){const b=state.activeBuild;$('#powerPanel').classList.toggle('hidden',!!b);$('#powerContent').classList.toggle('hidden',!b);if(!b)return;const p=b.power;if(!p){$('#powerMetrics').innerHTML='<div class="panel">Power analysis unavailable for this build.</div>';return;}const metrics=[['IDLE CURRENT',num(p.system_idle_current_a*1000,0)+' mA','Estimated idle draw'],['TYPICAL CURRENT',num(p.system_typical_current_a*1000,0)+' mA','40% motor load assumption'],['PEAK STALL CURRENT',num(p.system_peak_stall_current_a,2)+' A','All motors stalled'],['DISCHARGE MARGIN',num(p.battery_safety_margin_pct,1)+'%','Battery current margin'],['USABLE CAPACITY',num(p.battery_usable_mah,0)+' mAh','80% of rated capacity'],['TYPICAL RUNTIME',num(p.runtime_typical_h,1)+' h','Modelled estimate'],['DRIVER THERMAL LOSS',num(p.driver_thermal_loss_w,2)+' W','Heat dissipation estimate'],['STALL RUNTIME',num(p.runtime_stall_min,1)+' min','Continuous worst-case stall']];$('#powerMetrics').innerHTML=metrics.map(m=>`<article class="metric-card"><div class="metric-top">${esc(m[0])}</div><div class="metric-value" style="font-size:23px">${esc(m[1])}</div><div class="metric-foot">${esc(m[2])}</div></article>`).join('');$('#wiringRows').innerHTML=b.wiring.connections.map(w=>`<tr><td><b>${esc(w.source_component)}</b></td><td>${esc(w.source_pin)}</td><td>${esc(w.target_component)}</td><td>${esc(w.target_pin)}</td><td><span class="tag">${esc(w.wire_type)}</span>${w.notes?`<small style="display:block;color:#929a9a;margin-top:4px">${esc(w.notes)}</small>`:''}</td></tr>`).join('');notice('#wiringWarnings',[...(b.wiring.warnings||[]),...(p.thermal_warning?[p.thermal_warning]:[])].map(esc).join('<br>'),(b.wiring.warnings?.length||p.thermal_warning)?'warn':'');$('#assemblySteps').innerHTML=b.wiring.assembly_steps.map(s=>`<li>${esc(s)}</li>`).join('');$('#mermaidDiagram').textContent=b.wiring.mermaid_diagram||'No diagram available.';}
$('#copyDiagram').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('#mermaidDiagram').textContent);toast('Mermaid source copied.');}catch(e){toast('Clipboard permission was not available.','error');}});
function renderReports(){const b=state.activeBuild;$('#reportEmpty').classList.toggle('hidden',!!b);$('#reportContent').classList.toggle('hidden',!b);if(!b)return;$('#ledgerCount').textContent=`${b.ledger.length} RECORDS`;$('#ledgerRows').innerHTML=b.ledger.map(r=>`<tr><td><b>${esc(r.Part||r.part||'—')}</b></td><td>${esc(r.Field||r.field||'—')}</td><td>${esc(r.Value??r.value??'—')} ${esc(r.Unit||r.unit||'')}</td><td><span class="tag ${(r.Method||r.method)==='scraped'?'pass':''}">${esc((r.Method||r.method||'unknown').toUpperCase())}</span></td><td>${(r.Source||r.source_url)?`<a class="source-link" href="${esc(r.Source||r.source_url)}" target="_blank" rel="noopener">Open source ↗</a>`:'—'}</td><td>${esc(r['Retrieved (UTC)']||r.retrieved_at||'—')}</td></tr>`).join('')||'<tr><td colspan="6" class="empty-state">No evidence records.</td></tr>';}
async function downloadExport(kind){try{const params=new URLSearchParams();const includePower=$('#includePowerToggle')?.checked!==false;const includeWiring=$('#includeWiringToggle')?.checked!==false;params.set('include_power', String(includePower));params.set('include_wiring', String(includeWiring));const res=await fetch(`/api/export/${encodeURIComponent(kind)}?${params.toString()}`);if(!res.ok){const d=await res.json().catch(()=>({}));throw new Error(d.detail||'Export failed');}const blob=await res.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=kind==='bom.csv'?'robot_bom.csv':kind==='ledger.csv'?'evidence_ledger.csv':kind==='report.md'?'robot_report.md':'robot_report.html';document.body.append(a);a.click();a.remove();URL.revokeObjectURL(a.href);toast('Report downloaded.');}catch(e){toast(e.message,'error');}}
$$('[data-export]').forEach(b=>b.addEventListener('click',()=>downloadExport(b.dataset.export)));
$('#refreshPartsBtn').addEventListener('click',async e=>{const btn=e.currentTarget;const ids=[...$('#refreshParts').selectedOptions].map(o=>o.value);if(!ids.length){notice('#refreshOutput','Select at least one part first.','warn');return;}setBusy(btn,true,'Refreshing vendor pages…');try{const d=await api('/api/live/refresh',{method:'POST',body:JSON.stringify({category:$('#refreshCategory').value,part_ids:ids,pages_per_part:Number($('#refreshPages').value)})});notice('#refreshOutput',d.results.map(r=>`<b>${esc(r.part)}</b>: ${r.error?esc(r.error):esc(JSON.stringify(r.report?.changes||r.report?.problems||r.report||{}))}`).join('<br>'));await loadCatalog();toast('Refresh run completed.');}catch(err){notice('#refreshOutput',esc(err.message),'error');}finally{setBusy(btn,false);}});
$('#discoverBtn').addEventListener('click',async e=>{const btn=e.currentTarget;setBusy(btn,true,'Searching vendor listings…');notice('#discoverOutput','');try{const d=await api('/api/live/discover',{method:'POST',body:JSON.stringify({category:$('#discoverCategory').value,query:$('#discoverQuery').value,kind:$('#discoverCategory').value==='sensor'?$('#discoverKind').value||null:null})});state.discoveries=d.items||[];notice('#discoverOutput',`${state.discoveries.length} candidate(s) found. ${esc((d.report?.problems||[]).join(' · '))}`);if(state.discoveries.length){$('#discoverOutput').insertAdjacentHTML('beforeend',`<div class="table-wrap" style="margin-top:8px"><table class="data-table"><thead><tr><th>PART</th><th>PRICE</th><th>SPECS</th><th>ADD</th></tr></thead><tbody>${state.discoveries.map((p,i)=>`<tr><td><b>${esc(p.name)}</b><small style="display:block">${esc(p.vendor)}</small></td><td>${money(p.price_value)}</td><td>${Object.keys(p.specs_flat||{}).length}</td><td><input type="checkbox" data-discover-add="${i}" checked></td></tr>`).join('')}</tbody></table></div><button class="btn btn-primary" id="addDiscovered" style="width:100%;margin-top:9px">Add selected candidates</button>`);$('#addDiscovered').addEventListener('click',addDiscovered);}}catch(err){notice('#discoverOutput',esc(err.message),'error');}finally{setBusy(btn,false);}});
async function addDiscovered(){const items=$$('[data-discover-add]').filter(c=>c.checked).map(c=>state.discoveries[Number(c.dataset.discoverAdd)]);if(!items.length){toast('Select at least one candidate.','error');return;}try{const d=await api('/api/catalog/add',{method:'POST',body:JSON.stringify({items})});toast(`${d.added} part(s) added to catalog.`);notice('#discoverOutput',`${d.added} part(s) added to the active catalog.`);await loadCatalog();}catch(e){notice('#discoverOutput',esc(e.message),'error');}}
$('#importBtn').addEventListener('click',async e=>{const btn=e.currentTarget;const url=$('#importUrl').value.trim();if(!url){notice('#importOutput','Enter a product page URL first.','warn');return;}setBusy(btn,true,'Fetching product page…');try{const d=await api('/api/live/import-url',{method:'POST',body:JSON.stringify({url,category:$('#importCategory').value,kind:$('#importCategory').value==='sensor'?$('#importKind').value||null:null})});if(!d.part){notice('#importOutput','No part could be extracted. Review the report and try a direct product listing.','warn');return;}state.pendingImport=d.part;notice('#importOutput',`<b>${esc(d.part.name)}</b> · ${money(d.part.price_value)} · ${Object.keys(d.part.specs_flat||{}).length} specifications extracted<br><button class="btn btn-primary" id="addImported" style="margin-top:8px">Add this part to catalog</button>`);$('#addImported').addEventListener('click',async()=>{try{const x=await api('/api/catalog/add',{method:'POST',body:JSON.stringify({items:[state.pendingImport]})});notice('#importOutput',`${esc(d.part.name)} added to catalog.`);toast('Imported part added.');await loadCatalog();}catch(err){notice('#importOutput',esc(err.message),'error');}});}catch(err){notice('#importOutput',esc(err.message),'error');}finally{setBusy(btn,false);}});
$('#resetCatalog').addEventListener('click',async()=>{if(!confirm('Reset the live overlay? Seed catalog values will remain; custom/live overlay parts will be removed.'))return;try{await api('/api/catalog/reset',{method:'POST',body:'{}'});state.buildResponse=null;state.activeBuild=null;renderValidation();renderPower();renderReports();await loadCatalog();toast('Live catalog overlay reset.');}catch(e){toast(e.message,'error');}});
async function loadSettingsStatus(){try{state.settings=await api('/api/settings/status');const s=state.settings;$('#geminiIndicator').classList.toggle('on',s.gemini_configured);$('#tinyfishIndicator').classList.toggle('on',s.tinyfish_configured);$('#geminiSettingStatus').textContent=s.gemini_configured?'Configured from environment or current session':'Not configured';$('#tinyfishSettingStatus').textContent=s.tinyfish_configured?'Configured from environment or current session':'Not configured';$('#geminiModel').value=s.model||'gemini-2.5-flash';$('#geminiStatus').textContent=s.gemini_configured?'Configured':'Not configured';$('#geminiStatus').className=s.gemini_configured?'state-on':'state-off';$('#tinyfishStatus').textContent=s.tinyfish_configured?'Configured':'Not configured';$('#tinyfishStatus').className=s.tinyfish_configured?'state-on':'state-off';}catch(e){}}
$('#saveSettings').addEventListener('click',async e=>{const btn=e.currentTarget;setBusy(btn,true,'Saving session settings…');try{const payload={gemini_model:$('#geminiModel').value};if($('#geminiKey').value.trim())payload.gemini_api_key=$('#geminiKey').value.trim();if($('#tinyfishKey').value.trim())payload.tinyfish_api_key=$('#tinyfishKey').value.trim();const d=await api('/api/settings',{method:'POST',body:JSON.stringify(payload)});$('#geminiKey').value='';$('#tinyfishKey').value='';await loadSettingsStatus();notice('#settingsOutput','Settings updated for this running server process. API keys are not written to disk.');toast('Settings saved for this session.');}catch(err){notice('#settingsOutput',esc(err.message),'error');}finally{setBusy(btn,false);}});
async function healthCheck(){try{const d=await api('/api/health');$('#healthInfo').innerHTML=`<span class="mini-dot green"></span> ${esc(d.service)} · API ${esc(d.version)} · Operational`; }catch(e){$('#healthInfo').textContent='Health check failed: '+e.message;}}
$('#checkHealth').addEventListener('click',healthCheck);$('#refreshAll').addEventListener('click',async()=>{await init();toast('Workspace refreshed.');});
/* ---------- Where to buy: TinyFish seller links in the Inspect popup ---------- */
state.sources = null; state.applied = {};
async function loadSources(partId, refresh=false){
  const box=$('#sourcesBox'); if(!box) return;
  state.sourcesFor=partId; state.sources=null;
  box.innerHTML=`<div class="src-head"><div><div class="eyebrow">WHERE TO BUY</div><h4>Finding sellers with TinyFish…</h4></div><span class="pill">TINYFISH SEARCH</span></div><div class="src-loading"><span class="loading-dot">···</span> Searching vendor sites for this part. This can take 10–30 seconds.</div>`;
  try{
    const d=await api(`/api/part/${encodeURIComponent(partId)}/sources${refresh?'?refresh=true':''}`);
    if(state.sourcesFor!==partId) return;
    state.sources=d; renderSources(partId);
    if(d.prices && Object.keys(d.prices).length) renderSourcePrices(d.prices);
    else if(d.tinyfish_count) checkSourcePrices(partId,$('#srcPrices'));
  }catch(e){
    if(state.sourcesFor!==partId) return;
    box.innerHTML=`<div class="src-head"><div><div class="eyebrow">WHERE TO BUY</div><h4>Could not fetch seller links</h4></div></div><div class="notice error">${esc(e.message)}</div><button class="btn btn-small btn-outline" id="srcRetry" style="margin-top:10px">Try again ↻</button>`;
    $('#srcRetry').addEventListener('click',()=>loadSources(partId,true));
  }
}
async function applySourcePrice(url,btn){
  const partId=state.sourcesFor; if(!partId) return;
  if(btn){btn.disabled=true;btn.textContent='Saving…';}
  try{
    const d=await api(`/api/part/${encodeURIComponent(partId)}/sources/apply`,{method:'POST',body:JSON.stringify({url})});
    (state.applied=state.applied||{});
    Object.keys(state.applied).forEach(k=>delete state.applied[k]); state.applied[url]=true;
    toast(`Catalog price set to ${money(d.part.price_value)} (source saved to the evidence ledger).`);
    await loadCatalog(); renderSourcePrices(state.sources.prices||{});
  }catch(e){toast(e.message,'error'); if(btn){btn.disabled=false;btn.textContent='Use this price';}}
}
function snippetCell(l){return l.source==='tinyfish_search'?'<span class="loading-dot">···</span>':'<span class="tag unknown">NO PRICE</span>';}
function renderSources(partId){
  const d=state.sources, box=$('#sourcesBox'); if(!d||!box) return;
  const rows=d.links.map((l,i)=>`<div class="src-row" data-url="${esc(l.url)}"><span class="src-rank">${String(l.rank).padStart(2,'0')}</span><div class="src-main"><b>${esc(l.vendor)}</b><span class="src-title">${esc(l.title||l.url)}</span>${l.snippet?`<small>${esc(l.snippet)}</small>`:''}<small class="src-url">${esc(l.url)}</small></div><div class="src-price" data-price-for="${i}">${snippetCell(l)}</div><a class="btn btn-small btn-outline" href="${esc(l.url)}" target="_blank" rel="noopener">Open ↗</a></div>`).join('');
  box.innerHTML=`<div class="src-head"><div><div class="eyebrow">WHERE TO BUY</div><h4>${d.links.length} selling links <span class="src-count">· ${d.tinyfish_count} found by TinyFish</span></h4></div><span class="pill">TINYFISH SEARCH</span></div>
  <div class="src-list">${rows}</div>
  <div class="src-actions"><button class="btn btn-primary btn-small" id="srcPrices">Re-check live prices <span>↗</span></button><button class="btn btn-outline btn-small hidden" id="srcUseLowest">Use lowest verified price →</button><button class="btn btn-outline btn-small" id="srcRefresh">Search again ↻</button><span class="subtle">${d.cached?'Cached · ':''}${esc(d.fetched_at||'')} · ${d.queries.length} search quer${d.queries.length===1?'y':'ies'} run</span></div><div id="srcPriceNote" class="notice-stack"></div>`;
  $('#srcRefresh').addEventListener('click',()=>loadSources(partId,true));
  $('#srcPrices').addEventListener('click',e=>checkSourcePrices(partId,e.currentTarget));
  $('#srcUseLowest').addEventListener('click',()=>{const pr=state.sources.prices||{};const ok=state.sources.links.filter(l=>pr[l.url]?.price!=null&&pr[l.url].matches!==false).sort((a,b)=>pr[a.url].price-pr[b.url].price)[0];if(!ok){toast('No verified price to use.','error');return;}applySourcePrice(ok.url,$(`[data-use-url="${CSS.escape(ok.url)}"]`));});
}
async function checkSourcePrices(partId,btn){
  const d=state.sources; if(!d) return;
  const urls=d.links.filter(l=>l.source==='tinyfish_search').map(l=>l.url);
  if(!urls.length){renderSourcePrices({});return;}
  setBusy(btn,true,'Fetching live pages…');
  $$('[data-price-for]').forEach((el,i)=>{if(d.links[i].source==='tinyfish_search')el.innerHTML='<span class="loading-dot">···</span>';});
  try{
    const r=await api(`/api/part/${encodeURIComponent(partId)}/sources/prices`,{method:'POST',body:JSON.stringify({urls})});
    if(state.sourcesFor!==partId) return;
    d.prices={...(d.prices||{}),...r.prices}; renderSourcePrices(d.prices);
    const found=Object.values(r.prices).filter(x=>x.price!=null).length;

  }catch(e){
    renderSourcePrices(d.prices||{});
  }finally{setBusy(btn,false);}
}
function renderSourcePrices(prices){
  const d=state.sources; if(!d) return;
  const priced=d.links.map(l=>prices[l.url]?.price).filter(v=>v!=null);
  const low=priced.length?Math.min(...priced):null;
  $$('[data-price-for]').forEach(el=>{
    const l=d.links[Number(el.dataset.priceFor)], r=prices[l.url];
    if(!r){el.innerHTML='<span class="tag unknown">NO PRICE</span>';return;}
    if(r.price!=null){
      el.innerHTML=`<b>${money(r.price)}</b>${r.matches===false?'':`<button class="btn btn-small btn-outline src-use" data-use-url="${esc(l.url)}">${state.applied?.[l.url]?'✓ In catalog':'Use this price'}</button>`}`;
    }else{
      el.innerHTML='<span class="tag unknown">NO PRICE</span>';
    }
  });
  $$('[data-use-url]').forEach(b=>b.onclick=()=>applySourcePrice(b.dataset.useUrl,b));
  const lowBtn=$('#srcUseLowest'); if(lowBtn) lowBtn.classList.toggle('hidden',!priced.length);
}

const projectRobotIdeas = [
  { id: 'mobile-robot', name: 'Autonomous mobile robot', domain: 'autonomous', focus: 'Line following, obstacle avoidance, or indoor patrol', technologies: 'ESP32 · motor driver · distance/line sensors', domains: ['autonomous', 'iot'], hardware: ['esp32', 'arduino', 'pi'], software: ['c', 'python', 'ros'], environments: ['indoor', 'outdoor'], difficulty: 6, weeks: 6, scope: 7, budgetTier: 2, budgetLabel: 'Low–moderate', projectTypes: ['mini', 'capstone', 'lab'], summary: 'A tangible robot with a clear live demo and room to grow from basic control to mapping.' },
  { id: 'iot-system', name: 'Smart environment monitor', domain: 'iot', focus: 'Room conditions, energy use, or equipment monitoring', technologies: 'ESP32 · sensor suite · wireless dashboard', domains: ['iot', 'ev', 'health'], hardware: ['esp32', 'arduino', 'pi'], software: ['c', 'python'], environments: ['indoor', 'industrial'], difficulty: 4, weeks: 4, scope: 6, budgetTier: 1, budgetLabel: 'Low', projectTypes: ['mini', 'capstone', 'lab'], summary: 'A low-cost connected system with measurable data, alerts, and a straightforward prototype path.' },
  { id: 'vision-robot', name: 'Edge-vision inspection rover', domain: 'vision', focus: 'Object detection, visual tracking, or surface inspection', technologies: 'Raspberry Pi / Jetson · camera · OpenCV', domains: ['vision', 'autonomous'], hardware: ['pi', 'jetson'], software: ['python', 'opencv', 'ros'], environments: ['indoor', 'industrial'], difficulty: 8, weeks: 10, scope: 9, budgetTier: 3, budgetLabel: 'Moderate–high', projectTypes: ['capstone', 'research'], summary: 'Combines robotics and computer vision, with a strong path to measurable experiments and a research-style report.' },
  { id: 'assistive-device', name: 'Assistive mobility or gesture aid', domain: 'health', focus: 'Gesture-controlled aid, smart cane, or posture feedback', technologies: 'ESP32 · IMU / ranging sensors · haptic feedback', domains: ['health', 'iot'], hardware: ['esp32', 'arduino', 'pi'], software: ['c', 'python'], environments: ['indoor', 'outdoor'], difficulty: 6, weeks: 7, scope: 8, budgetTier: 2, budgetLabel: 'Low–moderate', projectTypes: ['mini', 'capstone', 'research'], summary: 'A user-centered prototype with a practical validation story and meaningful room for sensor experiments.' },
  { id: 'uav-platform', name: 'UAV telemetry and navigation', domain: 'uav', focus: 'Flight telemetry, waypoint navigation, or payload sensing', technologies: 'STM32 / flight controller · GPS · telemetry radio', domains: ['uav', 'autonomous'], hardware: ['stm32', 'pi', 'jetson'], software: ['c', 'python', 'ros'], environments: ['outdoor'], difficulty: 9, weeks: 12, scope: 9, budgetTier: 4, budgetLabel: 'High', projectTypes: ['capstone', 'research'], summary: 'A technically ambitious platform for teams with flight-safe test access and enough time for integration.' },
  { id: 'ev-power', name: 'EV battery and motor test bench', domain: 'ev', focus: 'Battery monitoring, motor control, or regenerative braking demo', technologies: 'STM32 · current/voltage sensing · protected power stage', domains: ['ev', 'iot'], hardware: ['stm32', 'arduino', 'pi'], software: ['c', 'python'], environments: ['indoor', 'industrial'], difficulty: 8, weeks: 10, scope: 9, budgetTier: 3, budgetLabel: 'Moderate–high', projectTypes: ['capstone', 'research', 'lab'], summary: 'A credible power-electronics project with instrumentable results and careful safety boundaries.' }
];

const projectFitQuestions = [
  { key: 'degree', title: 'What are you studying?', hint: 'We use this to connect the project to your coursework.', options: [['robotics', 'Robotics / automation'], ['electrical', 'Electrical / electronics'], ['mechanical', 'Mechanical engineering'], ['mechatronics', 'Mechatronics'], ['cs', 'Computer science'], ['other', 'Another program']] },
  { key: 'year', title: 'Which year are you in?', hint: 'This helps calibrate the expected technical ramp-up.', options: [['1', '1st year'], ['2', '2nd year'], ['3', '3rd year'], ['4', '4th year / graduate']] },
  { key: 'projectType', title: 'What are you making this for?', hint: 'Project expectations affect how broad the recommendation should be.', options: [['lab', 'A lab assignment'], ['mini', 'A mini-project'], ['capstone', 'A capstone / final-year project'], ['research', 'A research project']] },
  { key: 'evaluationFocus', title: 'What matters most in the evaluation?', hint: 'Choose the outcome you most need to demonstrate.', options: [['demo', 'A working hardware demo'], ['report', 'Measured results and a strong report'], ['research', 'Novelty and research depth'], ['custom', 'A custom engineering solution']] },
  { key: 'teamSize', title: 'How many people are on your team?', hint: 'Larger teams can take on more parallel integration work.', options: [['solo', 'Just me'], ['pair', 'Two people'], ['small', 'Three or four people'], ['large', 'Five or more people']] },
  { key: 'timeline', title: 'How much time do you have?', hint: 'Select the full time available, including testing and write-up.', options: [['2', 'About 2 weeks'], ['4', 'About 1 month'], ['12', 'About 3 months'], ['16', 'A full semester or longer']] },
  { key: 'budget', title: 'What is your approximate parts budget?', hint: 'This is a project-level estimate, not a BOM quote.', options: [['low', 'Under ₹5,000'], ['mid', '₹5,000–₹15,000'], ['high', '₹15,000–₹40,000'], ['very-high', 'Above ₹40,000']] },
  { key: 'platform', title: 'Which hardware platform do you prefer or have?', hint: 'You can choose a mixed stack if the project needs a companion computer.', options: [['arduino', 'Arduino'], ['esp32', 'ESP32'], ['stm32', 'STM32'], ['pi', 'Raspberry Pi'], ['jetson', 'Jetson Nano'], ['mixed', 'A mixed controller + computer stack']] },
  { key: 'software', title: 'Which software are you comfortable using?', hint: 'A project can still introduce a new stack; this just improves the initial fit.', options: [['c', 'C / C++'], ['python', 'Python / MicroPython'], ['ros', 'ROS / ROS 2'], ['opencv', 'OpenCV / edge AI']] },
  { key: 'fabrication', title: 'What workshop access do you have?', hint: 'Think about tools you can reliably use during the project.', options: [['none', 'No workshop or fabrication access'], ['basic', 'Soldering and basic hand tools'], ['cad', 'CAD and 3D printing'], ['pcb', 'PCB design and fabrication']] },
  { key: 'domain', title: 'Which problem area excites you most?', hint: 'This is the strongest signal in the idea ranking.', options: [['autonomous', 'Autonomous robots'], ['iot', 'IoT and smart systems'], ['vision', 'Computer vision / edge AI'], ['uav', 'Drones and UAVs'], ['health', 'Assistive technology / healthcare'], ['ev', 'Electric vehicles / power electronics']] },
  { key: 'environment', title: 'Where should the system operate?', hint: 'Environment affects sensing, enclosure, and test requirements.', options: [['indoor', 'Indoor spaces'], ['outdoor', 'Outdoor / campus'], ['industrial', 'Industrial or equipment area'], ['water', 'Wet, rough, or off-road conditions']] },
  { key: 'availability', title: 'How will you source components?', hint: 'A local-first design can reduce delays and substitutions.', options: [['local', 'Prefer parts available locally'], ['online', 'Online shipping is fine']] }
];

const projectFitState = { step: 0, answers: {}, recommendations: [], selectedId: null, specStep: 0, specAnswers: {}, report: null };
const fitStageIds = ['fitIntro', 'fitSurveyScreen', 'fitSelectionScreen', 'fitSpecScreen', 'fitReportScreen'];

function clamp(value, min, max) { return Math.min(Math.max(value, min), max); }

function showFitStage(stageId) {
  fitStageIds.forEach(id => document.getElementById(id).classList.toggle('hidden', id !== stageId));
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function enterWorkspace(page = 'overview') {
  document.body.classList.add('app-live');
  goto(page);
}

function startProjectFit() {
  projectFitState.step = 0;
  projectFitState.answers = {};
  projectFitState.recommendations = [];
  projectFitState.selectedId = null;
  projectFitState.specStep = 0;
  projectFitState.specAnswers = {};
  projectFitState.report = null;
  showFitStage('fitSurveyScreen');
  renderProjectFitQuestion();
}

function renderProjectFitQuestion() {
  const question = projectFitQuestions[projectFitState.step];
  const progress = ((projectFitState.step + 1) / projectFitQuestions.length) * 100;
  document.getElementById('fitSurveyCount').textContent = `QUESTION ${projectFitState.step + 1} OF ${projectFitQuestions.length}`;
  document.getElementById('fitSurveyProgress').style.width = `${progress}%`;
  document.getElementById('fitSurveyQuestion').textContent = question.title;
  document.getElementById('fitSurveyHint').textContent = question.hint;
  document.getElementById('fitSurveyOptions').innerHTML = question.options.map(([value, label]) => `
    <button class="fit-survey-option ${projectFitState.answers[question.key] === value ? 'is-selected' : ''}" type="button" role="radio" aria-checked="${projectFitState.answers[question.key] === value}" data-fit-answer="${esc(value)}">
      <span class="fit-option-mark" aria-hidden="true"></span><span>${esc(label)}</span>
    </button>
  `).join('');
  document.querySelectorAll('[data-fit-answer]').forEach(button => button.addEventListener('click', () => {
    projectFitState.answers[question.key] = button.dataset.fitAnswer;
    renderProjectFitQuestion();
  }));
  document.getElementById('fitSurveyBack').disabled = projectFitState.step === 0;
  document.getElementById('fitQuestionNext').disabled = !projectFitState.answers[question.key];
}

function finishProjectFitQuestion(skipped = false) {
  const question = projectFitQuestions[projectFitState.step];
  if (skipped) projectFitState.answers[question.key] = null;
  else if (!projectFitState.answers[question.key]) return;

  if (projectFitState.step < projectFitQuestions.length - 1) {
    projectFitState.step += 1;
    renderProjectFitQuestion();
    return;
  }

  projectFitState.recommendations = buildRecommendationScores(projectFitState.answers);
  projectFitState.selectedId = null;
  renderRecommendationCards(projectFitState.recommendations);
  showFitStage('fitSelectionScreen');
}

function returnToSurvey() {
  projectFitState.step = projectFitQuestions.length - 1;
  showFitStage('fitSurveyScreen');
  renderProjectFitQuestion();
}

function projectSpecQuestionsFor(project) {
  const missions = {
    'mobile-robot': [['line', 'Follow a line / marked path'], ['avoid', 'Avoid obstacles'], ['patrol', 'Patrol or monitor an indoor area'], ['delivery', 'Carry a small item between points']],
    'iot-system': [['climate', 'Monitor temperature and humidity'], ['energy', 'Track energy or power use'], ['equipment', 'Monitor a machine or storage area'], ['alert', 'Build a sensor-based alert system']],
    'vision-robot': [['detect', 'Detect and classify objects'], ['track', 'Track a moving object'], ['inspect', 'Inspect a surface or product'], ['navigate', 'Navigate using visual landmarks']],
    'assistive-device': [['gesture', 'Gesture-controlled assistance'], ['mobility', 'Mobility or obstacle alerts'], ['posture', 'Posture or movement feedback'], ['wearable', 'Wearable health or activity sensing']],
    'uav-platform': [['telemetry', 'Collect flight and sensor telemetry'], ['waypoint', 'Navigate between waypoints'], ['mapping', 'Map or inspect an area'], ['payload', 'Carry a lightweight sensor payload']],
    'ev-power': [['battery', 'Monitor battery voltage and current'], ['motor', 'Control a low-voltage motor'], ['thermal', 'Measure temperature and thermal behavior'], ['regen', 'Demonstrate regenerative braking concepts']]
  };
  const targets = {
    'mobile-robot': [['runtime', 'Maximize operating time'], ['accuracy', 'Repeatable path tracking'], ['speed', 'Higher travel speed'], ['payload', 'Carry a useful payload']],
    'iot-system': [['uptime', 'Long unattended uptime'], ['accuracy', 'Stable sensor accuracy'], ['response', 'Fast alerts'], ['cost', 'Lowest practical cost']],
    'vision-robot': [['accuracy', 'Detection accuracy'], ['realtime', 'Real-time frame rate'], ['lighting', 'Work across changing light'], ['runtime', 'Longer mobile runtime']],
    'assistive-device': [['reliability', 'Reliable alerts with few false triggers'], ['response', 'Fast response'], ['comfort', 'Low weight and comfort'], ['runtime', 'All-day battery life']],
    'uav-platform': [['flighttime', 'Longer flight time'], ['range', 'Greater communication range'], ['payload', 'More payload capacity'], ['stability', 'Stable autonomous flight']],
    'ev-power': [['voltage', 'Accurate voltage measurements'], ['current', 'Accurate current measurements'], ['thermal', 'Thermal monitoring'], ['control', 'Precise motor control']]
  };
  return [
    { key: 'mission', title: 'What should the project do first?', hint: 'Pick the primary function for the first working prototype.', options: missions[project.id] },
    { key: 'environment', title: 'Where will it operate?', hint: 'This affects enclosure, wheel/frame choice, and sensor protection.', options: [['indoor', 'Indoor, clean and level'], ['outdoor', 'Outdoor, mostly level'], ['rough', 'Uneven, dusty, or wet'], ['industrial', 'Near machinery or electrical equipment']] },
    { key: 'target', title: 'What is the main performance target?', hint: 'This will be called out as the project success criterion.', options: targets[project.id] },
    { key: 'sizeLoad', title: 'How large or heavy should it be?', hint: 'Choose a rough packaging or payload envelope.', options: [['compact', 'Compact and lightweight'], ['small-load', 'Carry up to about 500 g'], ['medium-load', 'Carry about 0.5–2 kg'], ['larger', 'Larger payload or bench-mounted system']] },
    { key: 'budget', title: 'Set the maximum parts budget', hint: 'Live prices may be missing; the report will mark those BOM rows as TBD.', options: [['low', 'Under ₹5,000'], ['mid', '₹5,000–₹15,000'], ['high', '₹15,000–₹40,000'], ['very-high', 'Above ₹40,000']] },
    { key: 'fabrication', title: 'How will you make the structure?', hint: 'This determines whether CAD drawings or custom mounting parts are needed.', options: [['kit', 'Use an off-the-shelf kit / enclosure'], ['hand', 'Hand tools and basic workshop'], ['laser', 'Laser-cut plates or sheet material'], ['3d', 'CAD and 3D printing']] },
    { key: 'power', title: 'What power source should it use?', hint: 'Choose the intended source for the prototype.', options: [['battery', 'Rechargeable battery'], ['mains', 'Mains adapter / bench supply'], ['solar', 'Solar-assisted power'], ['host', 'Powered by an existing system']] }
  ];
}

function startProjectSpecifications() {
  projectFitState.specStep = 0;
  projectFitState.specAnswers = {};
  projectFitState.report = null;
  renderProjectSpecQuestion();
  showFitStage('fitSpecScreen');
}

function renderProjectSpecQuestion() {
  const project = projectFitState.recommendations.find(item => item.id === projectFitState.selectedId);
  const questions = projectSpecQuestionsFor(project);
  const question = questions[projectFitState.specStep];
  document.getElementById('fitSpecCount').textContent = `PROJECT SPEC ${projectFitState.specStep + 1} OF ${questions.length}`;
  document.getElementById('fitSpecProgress').style.width = `${((projectFitState.specStep + 1) / questions.length) * 100}%`;
  document.getElementById('fitSpecBack').setAttribute('aria-label', projectFitState.specStep > 0 ? 'Go to previous specification question' : 'Go back to project choices');
  document.getElementById('fitSpecProjectName').textContent = project.name.toUpperCase();
  document.getElementById('fitSpecQuestion').textContent = question.title;
  document.getElementById('fitSpecHint').textContent = question.hint;
  document.getElementById('fitSpecOptions').innerHTML = question.options.map(([value, label]) => `
    <button class="fit-survey-option ${projectFitState.specAnswers[question.key] === value ? 'is-selected' : ''}" type="button" role="radio" aria-checked="${projectFitState.specAnswers[question.key] === value}" data-fit-spec="${esc(value)}"><span class="fit-option-mark" aria-hidden="true"></span><span>${esc(label)}</span></button>
  `).join('');
  document.querySelectorAll('[data-fit-spec]').forEach(button => button.addEventListener('click', () => {
    projectFitState.specAnswers[question.key] = button.dataset.fitSpec;
    renderProjectSpecQuestion();
  }));
  document.getElementById('fitSpecNext').disabled = !projectFitState.specAnswers[question.key];
  document.getElementById('fitSpecNext').innerHTML = projectFitState.specStep === questions.length - 1 ? 'Generate engineering report <span>→</span>' : 'Next <span>→</span>';
}

function finishProjectSpecQuestion(skipped = false) {
  const project = projectFitState.recommendations.find(item => item.id === projectFitState.selectedId);
  const questions = projectSpecQuestionsFor(project);
  const question = questions[projectFitState.specStep];
  if (skipped) projectFitState.specAnswers[question.key] = null;
  else if (!projectFitState.specAnswers[question.key]) return;
  if (projectFitState.specStep < questions.length - 1) {
    projectFitState.specStep += 1;
    renderProjectSpecQuestion();
    return;
  }
  generateProjectReport();
}

async function generateProjectReport() {
  const selected = projectFitState.recommendations.find(item => item.id === projectFitState.selectedId);
  showFitStage('fitReportScreen');
  document.getElementById('fitReportLoading').classList.remove('hidden');
  document.getElementById('fitReportError').classList.add('hidden');
  document.getElementById('fitReportOutput').classList.add('hidden');
  document.getElementById('fitReportActions').classList.add('hidden');
  document.getElementById('fitSourceBadge').textContent = 'PREPARING';
  document.getElementById('fitReportLoadingText').textContent = state.meta?.tinyfish_configured ? 'Searching vendors and verifying available prices with TinyFish…' : 'Preparing a catalog-based report; TinyFish is not configured in this session…';
  try {
    const report = await api('/api/project/report', { method: 'POST', body: JSON.stringify({ project_id: selected.id, project_answers: projectFitState.specAnswers, survey_answers: projectFitState.answers }) });
    projectFitState.report = report;
    renderProjectReport(report);
  } catch (error) {
    document.getElementById('fitReportLoading').classList.add('hidden');
    const errorBox = document.getElementById('fitReportError');
    errorBox.innerHTML = `<p>${esc(error.message)}</p><button id="fitRetryReport" class="fit-primary" type="button">Retry sourcing <span>↻</span></button>`;
    errorBox.classList.remove('hidden');
    document.getElementById('fitRetryReport').addEventListener('click', generateProjectReport);
  }
}

function buildRecommendationScores(values) {
  const years = Number(values.year || 2);
  const budgetIndex = { low: 1, mid: 2, high: 3, 'very-high': 4 }[values.budget] || 2;
  const timelineWeeks = Number(values.timeline || 12);

  return projectRobotIdeas.map(robot => {
    let relevance = 4;
    relevance += values.domain && robot.domains.includes(values.domain) ? 3 : 0;
    relevance += values.platform && robot.hardware.includes(values.platform) ? 2 : 0;
    relevance += values.software && robot.software.includes(values.software) ? 1 : 0;
    relevance += values.environment && robot.environments.includes(values.environment) ? 1 : 0;
    relevance += values.availability === 'local' && ['mobile-robot', 'iot-system', 'assistive-device'].includes(robot.id) ? 1 : 0;
    relevance += values.evaluationFocus === 'demo' && robot.projectTypes.includes('mini') ? 1 : 0;
    relevance += values.evaluationFocus === 'research' && robot.scope >= 8 ? 1 : 0;
    relevance += values.projectType === 'capstone' && robot.scope >= 8 ? 1 : 0;
    relevance += values.degree === 'cs' && ['vision-robot', 'iot-system'].includes(robot.id) ? 1 : 0;
    relevance += ['electrical', 'mechatronics'].includes(values.degree) && robot.domain === 'ev' ? 2 : 0;
    relevance += values.degree === 'mechanical' && robot.domain === 'autonomous' ? 1 : 0;
    relevance -= values.environment === 'water' && !['uav-platform', 'mobile-robot'].includes(robot.id) ? 1 : 0;

    const fabricationAdjustment = values.fabrication === 'none' ? 0 : values.fabrication === 'basic' ? 1 : values.fabrication ? 2 : 0;
    const readiness = 2 + years + fabricationAdjustment + (['small', 'large'].includes(values.teamSize) ? 1 : 0);
    const difficulty = clamp(Math.round(11 - Math.abs(robot.difficulty - readiness) * 1.4), 2, 10);
    const timeFit = clamp(Math.round(Math.min(10, timelineWeeks / robot.weeks * 10)), 1, 10);
    const budgetFits = !values.budget || budgetIndex >= robot.budgetTier;
    const projectTypeFit = !values.projectType ? 0 : robot.projectTypes.includes(values.projectType) ? 2 : -1;
    const scopeFit = clamp(5 + projectTypeFit + (values.teamSize === 'solo' && robot.scope > 8 ? -2 : 0) + (values.projectType === 'research' && robot.scope >= 8 ? 2 : 0) + (budgetFits ? 1 : -2), 1, 10);
    const relevanceScore = clamp(relevance, 1, 10);
    const budgetPenalty = values.budget ? Math.max(0, robot.budgetTier - budgetIndex) * 0.8 : 0;
    const fit = relevanceScore * 0.4 + difficulty * 0.2 + timeFit * 0.25 + scopeFit * 0.15 - budgetPenalty;
    const reasons = [];
    if (values.domain && robot.domains.includes(values.domain)) reasons.push('matches your interest area');
    if (values.platform && robot.hardware.includes(values.platform)) reasons.push(`works with your ${values.platform === 'pi' ? 'Raspberry Pi' : values.platform.toUpperCase()} preference`);
    if (values.timeline && timeFit >= 7) reasons.push('fits the time you have');
    if (values.projectType && scopeFit >= 7) reasons.push('has the right depth for your project type');

    return { ...robot, relevance: relevanceScore, difficulty, timeFit, scopeFit, fit, reason: reasons.slice(0, 2).join(' and ') || 'offers a balanced match for your constraints' };
  }).sort((a, b) => b.fit - a.fit).slice(0, 3);
}

function radarChart(item) {
  const values = [item.relevance, item.difficulty, item.timeFit, item.scopeFit];
  const centerX = 100;
  const centerY = 88;
  const radius = 57;
  const axes = [[0, -1], [1, 0], [0, 1], [-1, 0]];
  const pointsFor = scale => axes.map(([x, y]) => `${centerX + x * radius * scale},${centerY + y * radius * scale}`).join(' ');
  const resultPoints = values.map((value, index) => `${centerX + axes[index][0] * radius * value / 10},${centerY + axes[index][1] * radius * value / 10}`).join(' ');
  return `<svg class="radar-chart" viewBox="0 0 200 176" role="img" aria-label="Four-factor scores: relevance ${values[0]}, difficulty fit ${values[1]}, time fit ${values[2]}, project scope ${values[3]} out of 10">
    <polygon class="radar-grid" points="${pointsFor(1)}"></polygon><polygon class="radar-grid" points="${pointsFor(.75)}"></polygon><polygon class="radar-grid" points="${pointsFor(.5)}"></polygon><polygon class="radar-grid" points="${pointsFor(.25)}"></polygon>
    <line class="radar-axis" x1="100" y1="88" x2="100" y2="31"></line><line class="radar-axis" x1="100" y1="88" x2="157" y2="88"></line><line class="radar-axis" x1="100" y1="88" x2="100" y2="145"></line><line class="radar-axis" x1="100" y1="88" x2="43" y2="88"></line>
    <polygon class="radar-area" points="${resultPoints}"></polygon>
    ${values.map((value, index) => `<circle class="radar-point" cx="${centerX + axes[index][0] * radius * value / 10}" cy="${centerY + axes[index][1] * radius * value / 10}" r="3"></circle>`).join('')}
  </svg>`;
}

function renderProjectReport(report) {
  const output = document.getElementById('fitReportOutput');
  const sourceBadge = document.getElementById('fitSourceBadge');
  const priceText = value => value == null ? 'TBD' : money(value);
  const sourceLinks = (row) => (row.sources || []).map(source => `
    <div class="report-source"><a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.vendor || source.domain)} ↗</a>${source.title ? `<small>${esc(source.title)}</small>` : ''}<span>${source.source_type === 'tinyfish_search' ? 'TinyFish product result' : 'Vendor search page · not a product result'}</span><span>${source.price == null ? 'Price unverified' : `${money(source.price)} · ${esc(source.method || 'quote verified')}`}</span>${source.quote ? `<small>“${esc(source.quote)}”</small>` : ''}${source.error ? `<small>${esc(source.error)}</small>` : ''}</div>
  `).join('') || '<span class="report-no-source">No live listing found for this line.</span>';
  sourceBadge.textContent = report.sourcing.status === 'live' ? `TINYFISH · ${report.sourcing.verified_price_count} VERIFIED PRICES` : report.sourcing.status === 'partial' ? 'TINYFISH · PARTIAL' : 'NO LIVE SOURCES';
  sourceBadge.className = `fit-source-badge ${report.sourcing.status === 'live' ? 'is-live' : ''}`;
  output.innerHTML = `
    <section class="fit-report-project"><div><span>SELECTED PROJECT</span><h2>${esc(report.project.name)}</h2><p>${esc(report.project.focus)}</p></div><span class="fit-report-date">${esc(report.generated_at || '')}</span></section>
    <section class="fit-report-section"><h2>Project specifications</h2><div class="fit-report-spec-grid">${report.requirements.map(item => `<div><small>${esc(item.label)}</small><b>${esc(item.value || 'Not specified')}</b></div>`).join('')}</div></section>
    <section class="fit-report-section"><div class="fit-report-section-head"><div><span class="fit-report-kicker">PROCUREMENT PLAN</span><h2>Bill of materials</h2></div><span class="fit-report-total">${report.verified_total_inr == null ? 'Partial total' : `Verified subtotal ${money(report.verified_total_inr)}`}</span></div>
      <div class="fit-report-table-wrap"><table class="fit-report-table"><thead><tr><th>Component</th><th>Qty</th><th>Design requirement</th><th>Unit</th><th>Line</th><th>Stock</th><th>Live source evidence</th></tr></thead><tbody>${report.bom.map(row => `<tr><td><b>${esc(row.name)}</b><small>${esc(row.category)}</small></td><td>${esc(row.qty)}</td><td>${esc(row.requirements)}</td><td>${priceText(row.unit_price)}</td><td>${priceText(row.line_total)}</td><td>${row.in_stock === true ? 'In stock' : row.in_stock === false ? 'Out of stock' : 'Unknown'}</td><td>${sourceLinks(row)}</td></tr>`).join('')}</tbody></table></div>
    </section>
    <section class="fit-report-section"><div class="fit-report-section-head"><div><span class="fit-report-kicker">CONCEPTUAL CONNECTIONS</span><h2>Wiring plan</h2></div></div><p class="fit-report-note">${esc(report.wiring.note)}</p><div class="fit-report-table-wrap"><table class="fit-report-table"><thead><tr><th>From</th><th>To</th><th>Connection</th><th>Implementation note</th></tr></thead><tbody>${report.wiring.connections.map(row => `<tr><td>${esc(row.from)}</td><td>${esc(row.to)}</td><td>${esc(row.signal)}</td><td>${esc(row.notes)}</td></tr>`).join('')}</tbody></table></div></section>
    <section class="fit-report-section fit-chassis-report"><div class="fit-report-section-head"><div><span class="fit-report-kicker">MECHANICAL PACKAGE</span><h2>Chassis & CAD</h2></div><span class="cad-status ${report.chassis.cad_needed ? 'cad-needed' : ''}">${report.chassis.cad_needed ? 'CAD NEEDED' : 'CAD OPTIONAL'}</span></div><p>${esc(report.chassis.recommendation)}</p><div class="fit-report-spec-grid"><div><small>STRUCTURE</small><b>${esc(report.chassis.structure)}</b></div><div><small>MATERIAL / FABRICATION</small><b>${esc(report.chassis.material)}</b></div><div><small>CAD DECISION</small><b>${esc(report.chassis.cad_reason)}</b></div><div><small>DRAWINGS / PARTS TO MODEL</small><b>${esc(report.chassis.cad_deliverables.join(', '))}</b></div></div></section>
    <section class="fit-report-section fit-report-notes"><h2>Sourcing notes & checks</h2><p>${esc(report.sourcing.message)}</p>${report.warnings.length ? `<ul>${report.warnings.map(warning => `<li>${esc(warning)}</li>`).join('')}</ul>` : '<p>No additional project-specific warnings.</p>'}</section>`;
  document.getElementById('fitReportLoading').classList.add('hidden');
  document.getElementById('fitReportError').classList.add('hidden');
  output.classList.remove('hidden');
  document.getElementById('fitReportActions').classList.remove('hidden');
}

function downloadProjectReport() {
  const report = projectFitState.report;
  if (!report?.markdown) return;
  const blob = new Blob([report.markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${report.project.id}_engineering_report.md`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function renderRecommendationCards(items, answers) {
  const options = document.getElementById('fitProjectOptions');
  options.innerHTML = items.map((item, index) => `
    <button class="fit-project-option ${projectFitState.selectedId === item.id ? 'is-selected' : ''}" type="button" role="radio" aria-checked="${projectFitState.selectedId === item.id}" data-fit-project="${esc(item.id)}">
      <span class="fit-project-top"><span>OPTION 0${index + 1} ${index === 0 ? '· TOP MATCH' : ''}</span><span class="fit-project-check" aria-hidden="true"></span></span>
      <span class="fit-project-name">${esc(item.name)}</span>
      <span class="fit-project-summary">${esc(item.summary)}</span>
      <span class="fit-project-chart">${radarChart(item)}</span>
      <span class="fit-project-meta"><span>${item.fit.toFixed(1)} / 10 match</span><span>${item.weeks} weeks · ${esc(item.budgetLabel)} budget</span></span>
    </button>
  `).join('');
  options.querySelectorAll('[data-fit-project]').forEach(button => button.addEventListener('click', () => {
    projectFitState.selectedId = button.dataset.fitProject;
    renderRecommendationCards(items, answers);
  }));
  document.getElementById('fitSelectionContinue').disabled = !projectFitState.selectedId;
}

document.getElementById('fitBeginSurvey').addEventListener('click', startProjectFit);
document.getElementById('fitSkipSurvey').addEventListener('click', () => enterWorkspace());
document.getElementById('fitSurveyBack').addEventListener('click', () => {
  if (projectFitState.step > 0) {
    projectFitState.step -= 1;
    renderProjectFitQuestion();
  } else {
    showFitStage('fitIntro');
  }
});
document.getElementById('fitQuestionNext').addEventListener('click', () => finishProjectFitQuestion());
document.getElementById('fitQuestionSkip').addEventListener('click', () => finishProjectFitQuestion(true));
document.getElementById('fitSelectionBack').addEventListener('click', returnToSurvey);
document.getElementById('fitSelectionContinue').addEventListener('click', startProjectSpecifications);
document.getElementById('fitSpecBack').addEventListener('click', () => {
  if (projectFitState.specStep > 0) {
    projectFitState.specStep -= 1;
    renderProjectSpecQuestion();
  } else {
    showFitStage('fitSelectionScreen');
  }
});
document.getElementById('fitSpecNext').addEventListener('click', () => finishProjectSpecQuestion());
document.getElementById('fitSpecSkip').addEventListener('click', () => finishProjectSpecQuestion(true));
document.getElementById('fitReportBack').addEventListener('click', () => {
  const project = projectFitState.recommendations.find(item => item.id === projectFitState.selectedId);
  projectFitState.specStep = projectSpecQuestionsFor(project).length - 1;
  renderProjectSpecQuestion();
  showFitStage('fitSpecScreen');
});
document.getElementById('fitEditSpecifications').addEventListener('click', () => {
  const project = projectFitState.recommendations.find(item => item.id === projectFitState.selectedId);
  projectFitState.specStep = projectSpecQuestionsFor(project).length - 1;
  renderProjectSpecQuestion();
  showFitStage('fitSpecScreen');
});
document.getElementById('fitDownloadReport').addEventListener('click', downloadProjectReport);

init();
