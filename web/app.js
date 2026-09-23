const state = { dataset: null, manifest: null, lineSeq: 0, lines: [], rfqId: null, snapshotId: null, runId: null, matches: null };
const nativeScrollTo = window.scrollTo.bind(window);
window.scrollTo = (options, y) => {
  if (options && typeof options === 'object' && options.behavior === 'smooth' && matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return nativeScrollTo({...options, behavior:'auto'});
  }
  return nativeScrollTo(options, y);
};
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const el = (tag, props = {}, children = []) => { const n = document.createElement(tag); Object.entries(props).forEach(([k,v]) => k === 'text' ? n.textContent = v : k === 'className' ? n.className = v : k === 'on' ? Object.entries(v).forEach(([e,f]) => n.addEventListener(e,f)) : n.setAttribute(k,v)); children.forEach(c => n.append(c)); return n; };
const fa = n => new Intl.NumberFormat('fa-IR').format(Number(n || 0));
const money = n => `${fa(n)} ریال`;
function applyTheme(theme){ document.documentElement.dataset.theme=theme; const button=$('#theme-toggle'); if(button){button.textContent=theme==='dark'?'☀':'☾';button.setAttribute('aria-label',theme==='dark'?'بازگشت به پوستهٔ روشن':'تغییر به پوستهٔ تیره');} }
function initTheme(){ const saved=localStorage.getItem('torob-theme'); const theme=saved||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'); applyTheme(theme); $('#theme-toggle')?.addEventListener('click',()=>{const next=document.documentElement.dataset.theme==='dark'?'light':'dark';localStorage.setItem('torob-theme',next);applyTheme(next);}); }
const api = async (path, options = {}) => { const r = await fetch(path, { headers: {'Content-Type':'application/json', ...(options.headers||{})}, ...options }); let body = null; try { body = await r.json(); } catch {} if (!r.ok) { const msg = body?.error?.message || body?.detail || body?.message || `خطای ${r.status}`; throw new Error(msg); } return body; };
function notice(text, type='info') { const n = $('#notice'); n.textContent = text; n.className = `notice ${type}`; n.hidden = !text; }
function lineDom(line) { const wrap = el('div', {className:'line', 'data-line-id':line.id}); const top = el('div',{className:'line-top'},[el('span',{className:'line-number',text:fa(state.lines.indexOf(line)+1)}), el('button',{type:'button',className:'remove-line',title:'حذف قلم',text:'×',on:{click:()=>removeLine(line.id)}})]); const query = el('div',{className:'field grow'}); query.append(el('label',{text:'نام کالا یا مشخصات'})); const input=el('input',{type:'text',className:'query-input',placeholder:'مثلاً خودکار آبی ۰.۷',value:line.query,autocomplete:'off'}); query.append(input); if(line.decisionContextId)query.append(el('small',{className:'decision-line-note',text:'زمینهٔ تصمیم و ترجیح خرید ثبت شد'})); const suggestions=el('div',{className:'suggestions',role:'listbox'}); query.append(suggestions); input.addEventListener('input',()=>{ line.query=input.value; line.catalogItemId=null; line.decisionContextId=null; line.decisionAnswers={}; updateRequestCount(); searchSuggestions(input,suggestions,line); }); const qty=el('div',{className:'field qty'}); qty.append(el('label',{text:'تعداد'})); const q=el('input',{type:'number',min:'1',step:'1',value:line.qty,'aria-label':'تعداد'}); q.addEventListener('input',()=>line.qty=q.value); qty.append(q); top.append(el('div',{className:'line-id',text:`قلم ${fa(state.lines.indexOf(line)+1)}`})); wrap.append(top,el('div',{className:'line-fields'},[query,qty])); return wrap; }
function renderLines(){ const root=$('#lines'); root.replaceChildren(...state.lines.map(lineDom)); updateRequestCount(); }
function addLine(query='', qty='1'){ const line={id:`line-${++state.lineSeq}`,query,qty}; state.lines.push(line); renderLines(); }
function removeLine(id){ if(state.lines.length<=2) return notice('درخواست باید حداقل دو قلم داشته باشد.','error'); state.lines=state.lines.filter(x=>x.id!==id); renderLines(); }
let searchTimer;
async function searchSuggestions(input, box, line){ clearTimeout(searchTimer); box.replaceChildren(); if(input.value.trim().length<2)return; searchTimer=setTimeout(async()=>{ try { const data=await api(`/api/catalog/search?q=${encodeURIComponent(input.value.trim())}${state.snapshotId?`&snapshot_id=${encodeURIComponent(state.snapshotId)}`:''}`); const candidates=data.candidates||[]; if(!candidates.length){box.append(el('div',{className:'suggestion-empty',text:'نامزدی پیدا نشد'}));return;} candidates.slice(0,6).forEach(item=>{ const usable=(item.offer_count||0)>0; const b=el('button',{type:'button',className:`suggestion ${usable?'':'suggestion-disabled'}`,role:'option'}); b.append(el('b',{text:item.title||item.name||item.catalog_item_id||'کالای بدون نام'}),el('small',{text:usable?`${item.unit||item.base_unit||''} · ${fa(item.offer_count)} پیشنهاد`:'فقط برای مقایسهٔ منشأ؛ شرایط سفارش کامل نیست'})); if(usable)b.addEventListener('click',()=>{line.query=item.title||item.name||input.value; line.catalogItemId=item.catalog_item_id||item.id; input.value=line.query; box.replaceChildren();});else b.disabled=true; box.append(b); }); } catch(e){ /* search is progressive; submit still reports validation */ } },260); }
function readForm(){ const budget=$('#budget').value.replace(/[^0-9۰-۹]/g,'').replace(/[۰-۹]/g,d=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(d)); return {lines:state.lines.map(l=>({id:l.id,query_text:l.query,qty_base:Number(l.qty),catalog_item_id:l.catalogItemId||null,decision_context_id:l.decisionContextId||null,decision_answers:l.decisionAnswers||{}})), budget_irr:budget?Number(budget):null,max_lead_days:$('#lead').value?Number($('#lead').value):null,requires_declared_invoice:$('#invoice').checked,preference:$('input[name=preference]:checked').value}; }
async function submitRFQ(e){e.preventDefault(); notice('در حال ثبت درخواست و تطبیق اقلام…'); const payload=readForm(); if(payload.lines.some(l=>!l.query_text.trim()||!Number.isInteger(l.qty_base)||l.qty_base<1)){notice('نام کالا و تعداد معتبر برای همهٔ اقلام لازم است.','error');return;} try { const data=await api('/api/rfqs',{method:'POST',body:JSON.stringify({snapshot_id:state.snapshotId,...payload})}); state.rfqId=data.rfq_id; state.snapshotId=data.snapshot_id||state.snapshotId; state.matches=data.matches||null; $('#form-view').hidden=true; $('#match-view').hidden=false; renderMatches(data.matches||[]); notice(''); window.scrollTo({top:0,behavior:'smooth'}); } catch(e){notice(e.message,'error');} }
function renderMatches(matches){ const root=$('#matches'); root.replaceChildren(); const catalog=new Map((state.dataset?.catalog||[]).map(x=>[x.id,x])); (matches||[]).forEach(m=>{ const line=state.lines.find(x=>x.id===m.line_id); const box=el('article',{className:`match-item ${m.status}`}); const head=el('div',{className:'match-head'},[el('div',{className:'match-name',text:line?.query||m.line_id}),el('span',{className:`status status-${m.status}`,text:m.status==='confirmed'?'تأییدشده':m.status==='ambiguous'?'نیازمند انتخاب':'بدون تطبیق'})]); box.append(head); if(m.method)box.append(el('p',{className:'match-reason',text:m.status==='ambiguous'?'چند نامزد سازگار پیدا شد؛ یکی را انتخاب کن.':m.method==='no_rankable_offers'?'این کالا در دادهٔ دمو قیمت دارد، اما شرایط کامل موجودی/تحویل برای رتبه‌بندی ثبت نشده است.':m.status==='unmatched'?'برای این عبارت کالای قابل‌خرید در مجموعهٔ فعال پیدا نشد.':`تطبیق با روش ${m.method} ثبت شد.`})); const candidates=m.candidate_catalog_ids||[]; if(m.status!=='confirmed'&&candidates.length){ const list=el('div',{className:'candidate-list'}); candidates.forEach(id=>{const c=catalog.get(id)||{id}; const label=el('label',{className:'candidate'}); const radio=el('input',{type:'radio',name:`match-${m.line_id}`,value:id}); radio.addEventListener('change',()=>m.selected=id); const categoryPath=(c.category_path||[c.category||'کاتالوگ']).join(' / '); label.append(radio,el('span',{},[el('b',{text:c.name||id}),el('small',{text:`${c.base_unit||''} · ${categoryPath}`} )])); list.append(label);}); box.append(list); } else if(m.selected_catalog_id) box.append(el('p',{className:'confirmed-sku',text:`SKU: ${m.selected_catalog_id}`})); root.append(box); }); }
async function runEvaluation(preference, showResults=true){ try { notice('در حال بررسی همهٔ ترکیب‌های ممکن…'); const started=await api(`/api/rfqs/${state.rfqId}/evaluate`,{method:'POST',body:JSON.stringify({snapshot_id:state.snapshotId,preference})}); state.runId=started.run_id; const result=await api(`/api/runs/${state.runId}`); renderResults(result); if(showResults){$('#match-view').hidden=true;$('#results-view').hidden=false;window.scrollTo({top:0,behavior:'smooth'});} notice(''); }catch(e){notice(e.message,'error');} }
async function evaluate(){ const unresolved=(state.matches||[]).filter(m=>m.status!=='confirmed'&&!m.selected); if(unresolved.length){notice('برای ادامه، برای هر قلم مبهم یک SKU انتخاب کن.','error');return;} try { for(const m of state.matches||[]){if(m.selected) { const updated=await api(`/api/rfqs/${state.rfqId}/matches/${m.line_id}`,{method:'PUT',body:JSON.stringify({catalog_item_id:m.selected})}); m.status='confirmed'; m.selected_catalog_id=m.selected; if(updated.matches) state.matches=updated.matches; }} await runEvaluation($('input[name="preference"]:checked').value); }catch(e){notice(e.message,'error');} }
function renderResults(result){ const combos=result.combinations||[]; const statusLabel=result.status==='ok'?'قابل بررسی':result.status==='no_full_coverage'?'پوشش کامل پیدا نشد':result.status==='search_limit'?'سقف جست‌وجو رد شد':'اجرای ناموفق'; $('#results-subtitle').textContent=`${result.search_exhaustive?'جست‌وجوی کامل':'جست‌وجوی محدود'} · ${fa(result.enumerated_combinations)} ترکیب بررسی شد · اولویت: ${result.preference==='fastest_delivery'?'سریع‌ترین تحویل':'کمترین هزینه'}`; $('#result-summary').replaceChildren(el('div',{className:'summary-chip'},[el('span',{text:'مجموعه قیمت'}),el('b',{text:'فعال'})]),el('div',{className:'summary-chip'},[el('span',{text:'وضعیت'}),el('b',{text:statusLabel})]),el('div',{className:'summary-chip'},[el('span',{text:'منبع'}),el('b',{text:'پیشنهادهای ثبت‌شده'})])); const root=$('#results'); root.replaceChildren(); combos.slice(0,8).forEach((c,i)=>root.append(comboCard(c,i,result.preference))); const uncovered=result.uncovered_lines||[]; const excluded=result.excluded_reasons||[]; const reasonLabels={NO_RANKABLE_OFFERS:'این کالا فقط دادهٔ مقایسه‌ای دارد و شرایط کامل رتبه‌بندی سفارش ثبت نشده است.',UNKNOWN_CATALOG_ITEM:'کالا در کاتالوگ فعال پیدا نشد.'}; $('#uncovered').hidden=!uncovered.length&&!excluded.length; if(!$('#uncovered').hidden){const box=$('#uncovered');box.replaceChildren(el('h3',{text:result.status==='search_limit'?'جست‌وجو به سقف مجاز رسید':'اقلام یا ترکیب‌های کنارگذاشته‌شده'})); uncovered.forEach(u=>box.append(el('p',{text:`${(u.line_ids||[]).join('، ')}: ${(u.reason_codes||[]).map(code=>reasonLabels[code]||code).join('، ')}`}))); if(result.status==='search_limit')box.append(el('p',{text:'برای این درخواست هیچ رتبه‌ای تا کامل‌شدن جست‌وجو نمایش داده نمی‌شود.'}));} }
function comboCard(c,i,pref){ const card=el('article',{className:`combo-card ${i===0?'top':''}`}); const catalog=new Map((state.dataset?.catalog||[]).map(x=>[x.id,x])); const vendors=new Map((state.dataset?.vendors||[]).map(x=>[x.id,x])); const badge=i===0?el('span',{className:'best-badge',text:'پیشنهاد اول بر اساس ترجیح شما'}):el('span',{className:'rank',text:`رتبه ${fa(c.rank||i+1)}`}); const head=el('div',{className:'combo-head'},[badge,el('div',{className:'combo-total'},[el('small',{text:'جمع کل'}),el('strong',{text:money(c.total_irr)}),el('span',{text:`تحویل تا ${fa(c.max_lead_days)} روز`})])]); card.append(head); const reason=c.reason||c.reason_data||{}; let reasonText=reason.criterion==='max_lead_days'?`به‌دلیل زمان تحویل ${fa(c.max_lead_days)} روز انتخاب شده است.`:`به‌دلیل جمع کل ${money(c.total_irr)} در اولویت هزینه قرار گرفته است.`; if(reason.difference)reasonText+=` اختلاف با گزینهٔ مقایسه ${fa(reason.difference)} ${reason.difference_unit==='days'?'روز':'ریال'} است.`; card.append(el('p',{className:'reason',text:reasonText})); const table=el('div',{className:'assignment-table'}); table.append(el('div',{className:'table-row table-header'},[el('span',{text:'قلم'}),el('span',{text:'فروشنده'}),el('span',{text:'تعداد / اضافه'}),el('span',{text:'هزینه'})])); const invoiceStates=[]; (c.assignments||[]).forEach(a=>{const vendor=vendors.get(a.vendor_id); const item=catalog.get(a.catalog_item_id); if(a.invoice_status) invoiceStates.push(a.invoice_status); const row=el('div',{className:'table-row'},[el('span',{text:item?.name||a.catalog_item_id||a.line_ids?.join('، ')||'—'}),el('span',{text:vendor?.name||a.vendor_id||'—'}),el('span',{text:`${fa(a.covered_qty_base)} عدد / ${fa(a.overbuy_qty_base)} اضافه`}),el('span',{text:money(a.line_total_irr)})]); const offer=el('button',{type:'button',className:'provenance-link',text:'مشاهدهٔ منشأ'}); offer.addEventListener('click',()=>openProvenance(a.offer_id)); row.lastChild.append(offer); table.append(row);}); card.append(table); const invoiceLabel=invoiceStates.length&&invoiceStates.every(x=>x==='declared_yes'||x==='verified_yes')?'فاکتور: طبق اظهار فروشنده':invoiceStates.some(x=>x==='declared_no')?'فاکتور: برای برخی اقلام اعلام نشده':'فاکتور: وضعیت در داده ثبت نشده'; const foot=el('div',{className:'combo-foot'},[el('span',{text:`ارسال: ${money(c.shipping_total_irr)}`}),el('span',{text:`${fa(c.vendor_count)} فروشنده`}),el('span',{text:invoiceLabel})]); card.append(foot); return card; }
async function openProvenance(id){
  try{
    const d=await api(`/api/offers/${encodeURIComponent(id)}/provenance`);const root=$('#provenance-content');root.replaceChildren();
    const fields=[['پیشنهاد',d.offer?.id||id],['فروشنده',d.vendor?.name||d.vendor?.id],['کالا',d.catalog_item?.title||d.catalog_item?.name||d.catalog_item?.id],['منبع',d.source_label||d.raw?.source_label],['رکورد خام',d.raw?.raw_title||d.raw?.id],['قیمت خام',d.raw?.raw_price_text],['واحد خام',d.raw?.raw_unit_text],['زمان برداشت',d.raw?.captured_at||d.raw?.generated_at||d.raw?.observed_at],['URL منبع',d.raw?.source_url]];
    fields.filter(([,v])=>v!=null).forEach(([k,v])=>root.append(el('div',{className:'provenance-row'},[el('span',{text:k}),el('b',{text:String(v)})])));
    if(d.raw?.field_status)root.append(el('div',{className:'provenance-status'},[el('span',{text:'وضعیت فیلدها'}),el('b',{text:Object.entries(d.raw.field_status).map(([k,v])=>`${k}: ${v}`).join(' · ')})]));
    if(d.offer?.normalization_steps)root.append(el('p',{className:'normalization',text:`تبدیل‌های ثبت‌شده: ${d.offer.normalization_steps.join('، ')}`}));
    $('#provenance-dialog').showModal();
  }catch(e){notice(e.message,'error');}
}
async function loadDataset(){
  try{
    const d=await api('/api/datasets/active');
    state.dataset=d;
    const meta=d.metadata||{};
    state.snapshotId=meta.id||d.snapshot_id||d.id;
    $('#dataset-name').textContent='مجموعه قیمت‌های فعال';
    $('#dataset-meta').textContent=`${fa(d.counts?.catalog_items)} کالا · ${fa(d.counts?.vendors)} فروشنده`;
    $('#dataset-status').classList.remove('is-error');
    $('#dataset-status-label').textContent='هستهٔ تصمیم فعال';
    $('#header-snapshot').textContent=`snapshot ${state.snapshotId} · ${fa(d.counts?.accepted_offers)} پیشنهاد معتبر`;
    $('#hero-snapshot').textContent=`snapshot: ${state.snapshotId}`;
    $('#metric-catalog').textContent=fa(d.counts?.catalog_items);
    $('#metric-vendors').textContent=fa(d.counts?.vendors);
    $('#metric-prices').textContent=fa(d.counts?.prices);
  }catch(e){
    $('#dataset-name').textContent='مجموعه قیمت‌ها';
    $('#dataset-meta').textContent='اطلاعات مجموعه در دسترس نیست';
    $('#dataset-status').classList.add('is-error');
    $('#dataset-status-label').textContent='داده در دسترس نیست';
    $('#header-snapshot').textContent='snapshot در دسترس نیست';
    $('#hero-snapshot').textContent='snapshot: unavailable';
  }
}

async function loadSystemManifest(){
  try{
    const manifest=await api('/api/agents/manifest');
    state.manifest=manifest;
    $('#metric-agents').textContent=fa(manifest.agents?.length);
    const registered=new Set((manifest.agents||[]).map(agent=>agent.id));
    $$('.execution-graph [data-agent]').forEach(row=>{
      const available=registered.has(row.dataset.agent);
      row.querySelector('em').textContent=available?'REGISTERED':'MISSING';
      row.classList.toggle('is-error',!available);
    });
    $('#runtime-status').classList.remove('is-error');
    $('#runtime-status-label').textContent=`موتور تصمیم ${manifest.runtime?.mode||'آماده'}`;
    $('#runtime-failure-mode').textContent=manifest.runtime?.execution_plan?.failure_mode||'—';
    $('#runtime-parallelism').textContent=manifest.runtime?.execution_plan?.max_parallelism??'—';
    $('#console-status').classList.remove('is-error');
    $('#console-status').lastChild.textContent=' registry آماده';
  }catch{
    $('#metric-agents').textContent='—';
    $('#runtime-status').classList.add('is-error');
    $('#runtime-status-label').textContent='runtime در دسترس نیست';
    $('#runtime-failure-mode').textContent='—';
    $('#runtime-parallelism').textContent='—';
    $('#console-status').classList.add('is-error');
    $('#console-status').lastChild.textContent=' registry ناموجود';
    $$('.execution-graph [data-agent]').forEach(row=>{
      row.querySelector('em').textContent='UNKNOWN';
      row.classList.add('is-error');
    });
  }
}
document.addEventListener('DOMContentLoaded',()=>{addLine();addLine();loadDataset();loadSystemManifest();$('#add-line').addEventListener('click',()=>addLine());$('#rfq-form').addEventListener('submit',submitRFQ);$('#evaluate').addEventListener('click',evaluate);const backToForm=()=>{$('#match-view').hidden=true;$('#results-view').hidden=true;$('#form-view').hidden=false;notice('');window.scrollTo({top:0,behavior:'smooth'});};$('#edit-from-match').addEventListener('click',backToForm);$('#edit-request').addEventListener('click',backToForm);$('#close-dialog').addEventListener('click',()=>$('#provenance-dialog').close());$$('input[name=preference]').forEach(r=>r.addEventListener('change',()=>$$('.radio-card').forEach(x=>x.classList.toggle('active',x.querySelector('input').checked))));$$('.intent-button').forEach(button=>button.addEventListener('click',async()=>{const preference=button.dataset.preference;$$('.intent-button').forEach(x=>x.classList.toggle('active',x===button));await runEvaluation(preference,false);}));});
const _renderResults = renderResults;
renderResults = function(result) {
  _renderResults(result);
  decorateComparisonTables();
  if ((result.combinations || []).length || !(result.excluded_reasons || []).length) return;
  const box = $('#uncovered');
  const labels = {EXCEEDS_BUDGET:'از سقف بودجه عبور می‌کند', EXCEEDS_MAX_LEAD_DAYS:'از حداکثر زمان تحویل عبور می‌کند', BELOW_VENDOR_MINIMUM_ORDER:'به حداقل خرید فروشنده نمی‌رسد', INVOICE_NOT_DECLARED:'فاکتور اعلام‌شده ندارد', INSUFFICIENT_STOCK:'موجودی کافی ندارد', UNKNOWN_SHIPPING:'هزینهٔ ارسال نامشخص است'};
  const basketCodes = new Set(['EXCEEDS_BUDGET','EXCEEDS_MAX_LEAD_DAYS','BELOW_VENDOR_MINIMUM_ORDER','INVOICE_NOT_DECLARED','SEARCH_LIMIT']);
  const codes = [...new Set((result.excluded_reasons || []).filter(x => !x.catalog_item_id && (x.offer_ids || x.reason_codes?.some(c => basketCodes.has(c)))).flatMap(x => x.reason_codes || []).filter(c => basketCodes.has(c)))];
  if (!codes.length) return;
  box.append(el('p',{className:'excluded-summary',text:`هیچ سبد کاملی با این محدودیت‌ها واجد شرایط نشد: ${codes.map(c=>labels[c]).join('، ')}.`}));
  box.append(el('button',{type:'button',className:'button button-ghost empty-edit',text:'ویرایش بودجه یا محدودیت‌ها',on:{click:()=>{$('#results-view').hidden=true;$('#form-view').hidden=false;window.scrollTo({top:0,behavior:'smooth'});}}}));
};
function decorateComparisonTables(){
  $$('.assignment-table').forEach(table=>{
    table.setAttribute('role','table');
    table.setAttribute('aria-label','جزئیات اقلام پیشنهاد');
    $$('.table-row',table).forEach(row=>{
      row.setAttribute('role','row');
      $$('span',row).forEach(cell=>cell.setAttribute('role',row.classList.contains('table-header')?'columnheader':'cell'));
    });
  });
}
document.addEventListener('DOMContentLoaded',initTheme);

document.addEventListener('DOMContentLoaded',()=>{
  $('#catalog-start')?.addEventListener('click',()=>{
    const search=$('#catalog-query');
    if(!search)return;
    search.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'center'});
    search.focus({preventScroll:true});
  });
});

// The catalog is the entry point; RFQ remains the second step of the journey.
const shop = {items:[], categoryTree:[], categoryPath:[], query:'', sort:'relevance', rankableOnly:false, page:1, pageSize:12, decisionContextId:null, decisionAnswers:{}};
const normalizeSearch = value => String(value || '').toLocaleLowerCase('fa-IR').replace(/ي/g,'ی').replace(/ك/g,'ک').trim();
const itemCategoryPath = item => Array.isArray(item.category_path) && item.category_path.length ? item.category_path : [item.category || 'کالا'];
const samePrefix = (path, prefix) => prefix.every((part, index) => path[index] === part);
function updateRequestCount(){const target=$('#request-count');if(target)target.textContent=fa(state.lines.filter(line=>line.query.trim()).length);}
function showMainView(name){
  ['storefront','product-detail','workflow','business'].forEach(view=>{$(`#${view}-view`).hidden=view!==name;});
  $$('.nav-link').forEach(button=>{const active=button.dataset.view===name;button.classList.toggle('active',active);if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
  if(name==='workflow'){$('#form-view').hidden=false;$('#match-view').hidden=true;$('#results-view').hidden=true;notice('');}
  window.scrollTo({top:0,behavior:'smooth'});
}
function addCatalogItemToRequest(item, qty=1){
  if(item.rfq_capable===false){notice('این کالا فقط برای مقایسهٔ منشأ ثبت شده و شرایط کامل رتبه‌بندی خرید را ندارد.','error');return;}
  let line=state.lines.find(entry=>!entry.query.trim());
  if(!line){line={id:`line-${++state.lineSeq}`,query:'',qty:'1'};state.lines.push(line);}
  line.query=item.name;line.qty=String(qty);line.catalogItemId=item.id;line.decisionContextId=shop.decisionContextId||null;line.decisionAnswers={...(shop.decisionAnswers||{})};
  renderLines();if($('#product-dialog')?.open)$('#product-dialog').close();showMainView('workflow');
  const count=state.lines.filter(entry=>entry.query.trim()).length;
  notice(count<2?`${item.name} به فهرست خرید اضافه شد. برای مقایسه، دست‌کم یک قلم دیگر هم وارد کنید.`:`${item.name} به فهرست خرید اضافه شد. تعداد و شرایط را بررسی کنید.`);
}
function productVisual(item){
  const category=item.category||'';
  const asset=item.id?.startsWith('paper')?'/catalog/stack-of-papers.svg':item.id?.startsWith('mouse')?'/catalog/computer-mouse.svg':(['نوشت‌افزار'].includes(category)?'/catalog/ballpen.svg':null);
  const glyph=category==='صندلی اداری'?'🪑':category==='مانیتور'?'🖥️':category==='کیبورد'?'⌨️':category==='هارد و SSD'?'💾':'📦';
  const visual=el('div',{className:`product-visual ${itemCategoryPath(item).includes('لوازم جانبی کامپیوتر و لپ‌تاپ')?'product-visual-it':''}`});
  visual.append(asset?el('img',{src:asset,alt:item.name||'تصویر کالا',loading:'lazy'}):el('span',{text:glyph,'aria-label':item.name||'تصویر کالا'}));
  if(!asset) visual.firstChild?.setAttribute('role','img');
  return visual;
}
function cardPrice(item){const price=item.lowest_package_price_irr??item.min_package_price_irr??item.lowest_offer_price_irr;return price==null?'قیمت ثبت نشده':money(price);}
function renderCategoryFilters(){
  const root=$('#category-filters');
  const treePaths=[];
  const walk=(nodes,prefix=[])=>{(nodes||[]).forEach(node=>{const path=[...prefix,node.name];treePaths.push(path);walk(node.children,path);});};
  walk(shop.categoryTree);
  const paths=treePaths.length?treePaths:[...new Map(shop.items.map(item=>{const path=itemCategoryPath(item);return [path.join(' / '),path];})).values()];
  const makeChip=(label,path)=>{const active=samePrefix(shop.categoryPath,path)&&shop.categoryPath.length===path.length;const button=el('button',{type:'button',className:`filter-chip ${active?'active':''}`,text:label});button.setAttribute('aria-pressed',String(active));button.addEventListener('click',()=>{shop.categoryPath=path;shop.page=1;renderCategoryFilters();renderCatalog();});return button;};
  const childrenFor=prefix=>[...new Set(paths.filter(path=>samePrefix(path,prefix)).map(path=>path[prefix.length]).filter(Boolean))];
  const chips=[makeChip('همهٔ کالاها',[])];
  childrenFor([]).forEach(rootName=>chips.push(makeChip(rootName,[rootName])));
  if(shop.categoryPath.length){
    childrenFor(shop.categoryPath).forEach(child=>chips.push(makeChip(child,[...shop.categoryPath,child])));
  }
  root.replaceChildren(...chips);
}
function renderCatalog(){
  const q=normalizeSearch(shop.query);
  let items=shop.items.filter(item=>(!shop.categoryPath.length||samePrefix(itemCategoryPath(item),shop.categoryPath))&&(!q||normalizeSearch(`${item.name} ${item.id} ${(item.aliases||[]).join(' ')}`).includes(q)));
  if(shop.rankableOnly)items=items.filter(item=>item.rfq_capable!==false);
  if(shop.sort==='sources')items.sort((a,b)=>(b.accepted_offer_count||0)-(a.accepted_offer_count||0)||(b.supplier_count||0)-(a.supplier_count||0));
  if(shop.sort==='price-asc')items.sort((a,b)=>(a.lowest_package_price_irr??Infinity)-(b.lowest_package_price_irr??Infinity));
  if(shop.sort==='price-desc')items.sort((a,b)=>(b.lowest_package_price_irr??-1)-(a.lowest_package_price_irr??-1));
  const pages=Math.max(1,Math.ceil(items.length/shop.pageSize));
  shop.page=Math.min(shop.page,pages);
  const start=(shop.page-1)*shop.pageSize;
  const visible=items.slice(start,start+shop.pageSize);
  const end=Math.min(start+visible.length,items.length);
  $('#catalog-total').textContent=`${fa(items.length)} کالا`;
  $('#catalog-range').textContent=items.length?`نمایش ${fa(start+1)} تا ${fa(end)} از ${fa(items.length)}`:'بدون نتیجه';
  $('#catalog-empty').hidden=items.length>0;
  const pagination=$('#catalog-pagination');
  pagination.hidden=items.length<=shop.pageSize;
  $('#catalog-page-status').textContent=`صفحهٔ ${fa(shop.page)} از ${fa(pages)}`;
  $('#catalog-prev').disabled=shop.page<=1;
  $('#catalog-next').disabled=shop.page>=pages;
  const grid=$('#product-grid');grid.replaceChildren();
  visible.forEach(item=>{
    const card=el('article',{className:'product-card'});
    card.append(el('span',{className:`product-health ${item.rfq_capable===false?'':'rankable'}`,text:item.rfq_capable===false?'فقط منشأ':'قابل رتبه‌بندی'}),productVisual(item));
    const categoryPath=itemCategoryPath(item);const infoChildren=[el('span',{className:'product-category',text:categoryPath.join(' / ')}),el('h3',{text:item.name}),el('p',{text:`${fa(item.supplier_count||0)} تأمین‌کننده · ${fa(item.accepted_offer_count??0)} قیمت ثبت‌شده · واحد: ${item.base_unit||'عدد'}`})];if(item.decision_enabled)infoChildren.push(el('span',{className:'decision-card-hint',text:`راهنمای خرید: ${decisionStatusLabel(item.decision_status)}`}));if(item.rfq_capable===false)infoChildren.push(el('span',{className:'catalog-readonly',text:'فقط مقایسهٔ منشأ؛ شرایط سفارش کامل نیست'}));const info=el('div',{className:'product-info'},infoChildren);
    const price=el('div',{className:'product-price'},[el('small',{text:'کمترین قیمت ثبت‌شده'}),el('strong',{text:cardPrice(item)})]);
    const actions=el('div',{className:'product-actions'});
    actions.append(el('button',{type:'button',className:'button button-ghost',text:'مقایسهٔ تأمین‌کننده‌ها',on:{click:()=>openProduct(item.id)}}));
    if(item.rfq_capable===false)actions.append(el('span',{className:'catalog-readonly-action',text:'برای مقایسهٔ قیمت و منشأ'}));
    else actions.append(el('button',{type:'button',className:'button button-primary',text:'افزودن به فهرست',on:{click:()=>addCatalogItemToRequest(item)}}));
    card.append(info,price,actions);grid.append(card);
  });
}
const decisionStatusLabel=status=>({confirmed:'سازگاری تأیید شده',needs_check:'نیازمند بررسی قبل از خرید',unknown:'اطلاعات سازگاری ناقص'})[status]||'نیازمند بررسی';
const decisionStatusClass=status=>status==='confirmed'?'confirmed':status==='needs_check'?'needs-check':'unknown';
function decisionQuestion(question, contextId){
  const box=el('div',{className:'decision-question'});
  box.append(el('strong',{text:question.label||'یک ترجیح را مشخص کن'}));
  const options=el('div',{className:'decision-options'});
  (question.options||[]).forEach(option=>{
    const button=el('button',{type:'button',className:'decision-option'});
    button.append(el('b',{text:option.label}),el('small',{text:option.description||''}));
    button.addEventListener('click',()=>answerDecision(contextId,question.id,option.id,box));
    options.append(button);
  });
  box.append(options,el('p',{className:'decision-feedback',text:'یک گزینه را انتخاب کن؛ این انتخاب جای تأیید سازگاری را نمی‌گیرد.'}));
  return box;
}
async function answerDecision(contextId,questionId,optionId,box){
  try{
    const result=await api(`/api/catalog/decision/${encodeURIComponent(contextId)}/answers`,{method:'POST',body:JSON.stringify({answers:{[questionId]:optionId}})});
    shop.decisionContextId=contextId;shop.decisionAnswers={...(shop.decisionAnswers||{}),[questionId]:optionId};
    const feedback=$('.decision-feedback',box);if(feedback)feedback.textContent=result.message||'ترجیح ثبت شد؛ حالا تفاوت گزینه‌ها را بررسی کن.';
    $$('.decision-option',box).forEach(button=>button.classList.toggle('selected',button.querySelector('b')?.textContent===result.selected_option_label));
  }catch(error){const feedback=$('.decision-feedback',box);if(feedback)feedback.textContent=error.message;}
}
function renderDecisionHelper(data){
  const root=$('#decision-helper');
  root.replaceChildren();
  if(!data?.context){root.hidden=true;return;}
  const context=data.context;const options=data.options||[];const question=(context.questions||[])[0];
  const header=el('div',{className:'decision-header'},[
    el('div',{},[el('span',{className:'decision-kicker',text:'جواب کالا · قبل از مقایسه'}),el('h3',{id:'decision-helper-title',text:context.title||'راهنمای انتخاب'}),el('p',{text:context.summary||''})]),
    el('span',{className:'decision-status needs-check',text:options.length?`${fa(options.length)} گزینهٔ مرتبط`:'اطلاعات ناقص'})
  ]);
  root.append(header);
  if(question)root.append(decisionQuestion(question,context.id));
  const list=el('div',{className:'decision-option-list'});
  options.slice(0,6).forEach(option=>{
    const card=el('article',{className:'decision-product'});
    const price=option.lowest_price_irr==null?'قیمت ثبت نشده':`از ${money(option.lowest_price_irr)}`;
    card.append(el('div',{},[el('strong',{text:option.name}),el('p',{text:option.summary||'مشخصات تکمیلی برای این گزینه کامل نیست.'})]),el('div',{className:'decision-product-side'},[el('span',{className:`decision-status ${decisionStatusClass(option.fitment_status)}`,text:decisionStatusLabel(option.fitment_status)}),el('b',{text:price}),el('button',{type:'button',className:'provenance-link',text:'بررسی جزئیات',on:{click:()=>openProduct(option.product_id)}})]));
    list.append(card);
  });
  if(options.length)root.append(el('div',{className:'decision-list-heading'},[el('strong',{text:'گزینه‌های پیدا شده'}),el('span',{text:'قیمت به‌تنهایی جواب نیست؛ این تفاوت‌ها را هم ببین.'})]),list);
  const checks=context.checks_before_buying||[];
  if(checks.length)root.append(el('div',{className:'decision-checks'},[el('strong',{text:'قبل از خرید چک کن'}),el('ul',{},checks.slice(0,4).map(check=>el('li',{text:check})))]));
  root.hidden=false;
}
let decisionTimer;let decisionRequestSeq=0;
function loadDecision(query){
  clearTimeout(decisionTimer);const value=String(query||'').trim();const seq=++decisionRequestSeq;
  if(value.length<2){renderDecisionHelper(null);return;}
  decisionTimer=setTimeout(async()=>{try{const data=await api(`/api/catalog/decision?q=${encodeURIComponent(value)}`);if(seq===decisionRequestSeq)renderDecisionHelper(data);}catch(error){if(seq===decisionRequestSeq)renderDecisionHelper(null);}},180);
}
async function loadCatalog(){
  try{const data=await api('/api/catalog/items');shop.items=(data.items||[]).map(item=>({...item,id:item.catalog_item_id||item.id,offer_count:item.accepted_offer_count}));shop.categoryTree=data.categories||[];renderCategoryFilters();renderCatalog();$('#catalog-error').hidden=true;}
  catch(error){$('#product-grid').replaceChildren();const box=$('#catalog-error');box.textContent=`کاتالوگ بارگذاری نشد: ${error.message}`;box.hidden=false;$('#catalog-total').textContent='—';}
}
async function openProduct(id){
  showMainView('product-detail');
  $('#product-detail-loading').hidden=false;$('#product-detail-content').hidden=true;
  $('#product-decision-card').hidden=true;
  $('#agent-analysis-card').hidden=true;
  try{
    const data=await api(`/api/catalog/items/${encodeURIComponent(id)}`);
    renderProductDetail(data);
  }catch(error){
    $('#product-detail-loading').replaceChildren(el('p',{className:'notice error',text:`جزئیات کالا بارگذاری نشد: ${error.message}`}));
  }
}

function renderAgentAnalysis(analysis){
  const root=$('#agent-analysis-card');
  const content=$('#agent-analysis-content');
  if(!root||!content)return;
  content.replaceChildren();
  if(!analysis){root.hidden=true;return;}
  const synthesis=analysis.artifacts?.synthesis||{};
  const gates=analysis.quality_gates||synthesis.quality_gates||{};
  const gateLabels={no_price_invention:'بدون ساختن قیمت',exact_sku_only:'فقط SKU دقیق',provenance_audited:'منشأ ممیزی شد'};
  const plan=analysis.execution_plan||{};
  const summary=el('div',{className:'agent-analysis-summary'},[
    el('p',{text:synthesis.summary_fa||'خلاصه‌ای از شواهد ثبت‌شده در دسترس نیست.'}),
    el('small',{text:`${analysis.execution_mode||'deterministic-local'} · شناسهٔ اجرا: ${analysis.run_id||'—'}`})
  ]);
  const executionPlan=el('section',{className:'agent-plan'},[
    el('div',{className:'agent-plan-heading'},[
      el('strong',{text:'برنامهٔ اجرا'}),
      el('span',{text:`سقف هم‌زمانی ${fa(plan.max_parallelism||1)} · ${plan.failure_mode||'fail-closed'}`})
    ]),
    el('div',{className:'agent-plan-layers'},(plan.layers||[]).map((layer,index)=>el('div',{className:'agent-plan-row'},[
      el('strong',{text:`لایهٔ ${fa(index)}`}),
      el('span',{text:layer.join(' + ')})
    ])))
  ]);
  const gateBox=el('div',{className:'agent-gates'},Object.entries(gateLabels).map(([key,label])=>el('span',{className:`agent-gate ${gates[key]?'passed':'failed'}`},[el('b',{text:gates[key]?'✓':'!'}),el('span',{text:`${label}: ${gates[key]?'تأیید':'نیازمند بررسی'}`})])));
  const trace=el('div',{className:'agent-trace'});
  (analysis.trace||[]).forEach(step=>{
    const skills=(step.skills||[]).map(skill=>el('span',{className:'agent-skill-chip',text:skill}));
    const row=el('article',{className:`agent-trace-row ${step.status==='completed'?'completed':'failed'}`},[
      el('div',{className:'agent-trace-main'},[
        el('div',{className:'agent-trace-title'},[el('strong',{text:step.agent_id}),el('span',{text:step.role})]),
        el('div',{className:'agent-skills'},skills)
      ]),
      el('div',{className:'agent-trace-meta'},[
        el('span',{text:step.status==='completed'?'کامل شد':'متوقف شد'}),
        el('span',{text:`${fa(step.evidence_count||0)} شاهد · ${fa(step.attempts||1)} تلاش · ${fa(step.duration_ms||0)} ms`})
      ])
    ]);
    trace.append(row);
  });
  content.append(summary,executionPlan,gateBox,el('div',{className:'agent-trace-heading'},[
    el('strong',{text:'ردیابی اجرای عامل‌ها'}),
    el('span',{text:`${fa(analysis.agent_count||0)} عامل در گراف وابستگی`})
  ]),trace);
  root.hidden=false;
  $('#agent-analysis-status').textContent=analysis.status==='completed'?'اجرا کامل شد':'نیازمند بررسی';
  $('#agent-analysis-status').className=`agent-status ${analysis.status==='completed'?'passed':'failed'}`;
}

function renderProductDetail(data){
  const item=data.item||{};const prices=data.prices||data.offers||[];const comparable=prices.filter(price=>Number.isInteger(price.price_irr)&&price.price_irr>0).sort((a,b)=>a.price_irr-b.price_irr);const lowest=comparable[0]?.price_irr;
  $('#product-detail-path').textContent=itemCategoryPath(item).join(' / ');
  $('#product-detail-title').textContent=item.name||'جزئیات کالا';
  $('#product-detail-id').textContent=`شناسهٔ کالا: ${item.id||'—'} · واحد پایه: ${item.base_unit||'عدد'}`;
  $('#product-detail-price-hero').replaceChildren(el('span',{text:'کمترین قیمت قابل‌مقایسه'}),el('strong',{text:lowest==null?'قیمت ثبت نشده':money(lowest)}),el('small',{text:lowest==null?'هنوز قیمت عددی برای این کالا ثبت نشده است':'بر اساس قیمت بستهٔ ثبت‌شده'}));
  $('#product-detail-summary').replaceChildren(el('span',{className:'detail-summary-chip',text:`${fa(prices.length)} ردیف منبع`}),el('span',{className:'detail-summary-chip',text:`${fa(comparable.length)} قیمت قابل‌مقایسه`}),el('span',{className:'detail-summary-chip',text:item.category||'کالای سازمانی'}));
  $('#product-price-count').textContent=`${fa(prices.length)} ردیف منبع`;
  const priceList=$('#product-price-list');priceList.replaceChildren();
  if(!prices.length)priceList.append(el('p',{className:'catalog-loading',text:'برای این کالا هنوز تأمین‌کننده‌ای در مجموعهٔ فعال ثبت نشده است.'}));
  const groups=data.source_comparison?.sources||[];
  const grouped=groups.length?groups:prices.reduce((map,price)=>{(map[price.supplier_id]??=[]).push(price);return map;},{});
  const sourceGroups=groups.length?groups:Object.entries(grouped).map(([supplier_id,records])=>({supplier_id,supplier_name:records[0]?.supplier_name,records,unknown_fields:[]}));
  sourceGroups.forEach(group=>{
    const records=group.records||[];const supplierKind=group.supplier_id==='digikala'?'دیجی‌کالا بیزینس':group.supplier_id==='v-torob'?'ترب':'تأمین‌کنندهٔ ثبت‌شده';
    const heading=el('div',{className:'source-group-heading'},[el('div',{},[el('strong',{text:group.supplier_name||group.supplier_id||'تأمین‌کننده'}),el('span',{className:'supplier-chip',text:supplierKind})]),el('span',{className:'source-match-status',text:group.sku_match_status==='exact'?'SKU دقیقاً تطبیق داده شد':'وضعیت تطبیق در این منبع ثبت نشده'})]);
    const unknown=(group.unknown_fields||[]).filter(Boolean);const meta=el('div',{className:'source-meta'},[el('span',{text:`منشأ: ${group.source_labels?.join('، ')||supplierKind}`}),el('span',{text:`${fa(records.length)} رکورد مشاهده‌شده`})]);
    (group.source_urls||[]).slice(0,2).forEach(url=>meta.append(el('a',{className:'source-url',href:url,target:'_blank',rel:'noreferrer',text:'URL منبع'})));
    if(unknown.length)meta.append(el('span',{className:'unknown-fields',text:`تفاوت نامعلوم: ${unknown.join('، ')}`}));
    const section=el('section',{className:'source-group'},[heading,meta]);
    records.forEach(price=>{
      const priced=Number.isInteger(price.price_irr)&&price.price_irr>0;const row=el('article',{className:`price-row ${priced?'':'price-row-unavailable'}`});
      const supplier=el('div',{className:'supplier-cell'},[el('strong',{text:price.supplier_name||price.supplier_id||'تأمین‌کننده'}),el('span',{className:'supplier-chip',text:price.source_label||supplierKind})]);
      const amount=el('div',{className:priced?'detail-price':'price-unavailable'},[el('strong',{text:priced?money(price.price_irr):(price.price_status==='unavailable'?'ناموجود':'قیمت نامعلوم')}),el('small',{text:priced?`بستهٔ ${fa(price.package_size_base)} ${item.base_unit||'عدد'}`:(price.raw_price_text||'متن قیمت از منبع قابل‌مقایسه نیست')})]);
      const facts=el('div',{className:'price-facts'},[el('span',{text:price.lead_days==null?'تحویل نامشخص':`تحویل ${fa(price.lead_days)} روز`}),el('span',{text:price.stock_packages==null?'موجودی از منبع گزارش نشده':`موجودی ${fa(price.stock_packages)} بسته`}),el('span',{text:price.invoice_status==='declared_yes'?'فاکتور: اعلام‌شده':'فاکتور: نامشخص'}),el('span',{text:price.valid_at?`برداشت: ${price.valid_at}`:'زمان برداشت نامعلوم'})]);
      const actions=el('div',{className:'price-row-actions'});if(price.offer_id)actions.append(el('button',{type:'button',className:'provenance-link',text:'مشاهدهٔ منشأ',on:{click:()=>openProvenance(price.offer_id)}}));else actions.append(el('span',{className:'muted',text:'منشأ این ردیف در دسترس نیست'}));
      row.append(supplier,amount,facts,actions);section.append(row);
    });
    priceList.append(section);
  });
  const specs=$('#product-specs');specs.replaceChildren();const specLabels={brand:'برند',color:'رنگ',tip_mm:'ضخامت نوک (میلی‌متر)',model:'مدل',connection:'نوع اتصال',capacity:'ظرفیت',interface:'رابط',condition:'وضعیت کالا',type:'نوع کالا',backrest:'پشتی',size:'اندازه',weight_gsm:'گرماژ',sheets_per_ream:'تعداد برگ'};const specValues={wired_usb:'USB باسیم',wireless:'بی‌سیم',external_hdd:'هارد اکسترنال',blue:'آبی',black:'مشکی',used:'استوک'};const values={واحد:item.base_unit||'عدد',دسته:item.category||'—',...((item.specs&&typeof item.specs==='object')?item.specs:{})};Object.entries(values).forEach(([key,value])=>specs.append(el('div',{className:'spec'},[el('span',{text:specLabels[key]||key}),el('b',{text:Array.isArray(value)?value.map(v=>specValues[v]||v).join('، '):String(specValues[value] ?? value ?? '—')})])));
  const qty=$('#product-detail-qty');const add=$('#product-detail-add');if(item.rfq_capable===false){qty.disabled=true;add.disabled=true;add.textContent='فقط مقایسهٔ منشأ';add.title='شرایط کامل رتبه‌بندی سفارش ثبت نشده است';}else{qty.disabled=false;add.disabled=false;add.textContent='افزودن به فهرست خرید';add.title='';add.onclick=()=>{const count=Number(qty.value);if(!Number.isInteger(count)||count<1){qty.setCustomValidity('تعداد باید عدد صحیح مثبت باشد');qty.reportValidity();return;}qty.setCustomValidity('');addCatalogItemToRequest(item,count);};}
  renderProductDecision(data.item?.decision);
  renderAgentAnalysis(data.agent_analysis);
  $('#product-detail-loading').hidden=true;$('#product-detail-content').hidden=false;
}
function renderProductDecision(decision){
  const root=$('#product-decision-card');root.replaceChildren();
  if(!decision){root.hidden=true;return;}
  const status=el('span',{className:`decision-status ${decisionStatusClass(decision.fitment_status)}`,text:decisionStatusLabel(decision.fitment_status)});
  const intro=el('div',{className:'decision-card-intro'},[el('div',{},[el('span',{className:'decision-kicker',text:'راهنمای تصمیم'}),el('h2',{id:'product-decision-title',text:decision.title||'قبل از خرید این کالا'}),el('p',{text:decision.context_summary||''})]),status]);
  root.append(intro,el('p',{className:'decision-summary',text:decision.summary||''}));
  const question=(decision.questions||[])[0];if(question)root.append(decisionQuestion(question,decision.context_id));
  const differences=decision.comparison?.differences||[];
  if(differences.length){
    const diff=el('div',{className:'decision-diff'});diff.append(el('div',{className:'decision-subheading'},[el('strong',{text:'فرق گزینه‌های هم‌خانواده'}),el('span',{text:'همهٔ این موارد از یک نوع کالا نیستند.'})]));
    differences.slice(0,5).forEach(entry=>{const row=el('div',{className:'decision-diff-row'},[el('b',{text:entry.label||entry.field})]);const values=el('div',{className:'decision-diff-values'});(entry.values||[]).slice(0,4).forEach(value=>values.append(el('span',{},[el('small',{text:value.product_name}),el('strong',{text:value.value})])));row.append(values);diff.append(row);});root.append(diff);
  }
  const claims=(decision.claims||[]).slice(0,6);if(claims.length){const claimsBox=el('div',{className:'decision-claims'},[el('div',{className:'decision-subheading'},[el('strong',{text:'آنچه دربارهٔ این کالا می‌دانیم'}),el('span',{text:'منبع: مشخصات کاتالوگ'})])]);const grid=el('div',{className:'decision-claim-grid'});claims.forEach(claim=>grid.append(el('span',{},[el('small',{text:claim.label||claim.field}),el('strong',{text:claim.value_text})])));claimsBox.append(grid);root.append(claimsBox);}
  const evidence=decision.supplier_evidence||[];root.append(el('p',{className:'decision-evidence',text:evidence.length?`${fa(evidence.length)} سیگنال منشأ قیمت از تأمین‌کننده‌ها ثبت شده؛ برای مقایسهٔ جزئیات، ردیف‌های قیمت پایین صفحه را ببین.`:'برای این کالا هنوز سیگنال کافی از تأمین‌کننده‌ها ثبت نشده است.'}));
  const checks=decision.checks_before_buying||[];if(checks.length)root.append(el('div',{className:'decision-checks'},[el('strong',{text:'قبل از سفارش چک کن'}),el('ul',{},checks.slice(0,4).map(check=>el('li',{text:check})))]));
  root.hidden=false;
}
document.addEventListener('DOMContentLoaded',()=>{
  $$('[data-view]').forEach(button=>button.addEventListener('click',()=>showMainView(button.dataset.view)));
  $('#brand-home').addEventListener('click',event=>{event.preventDefault();showMainView('business');});
  $('#catalog-query').addEventListener('input',event=>{shop.query=event.target.value;shop.page=1;$('#clear-catalog-query').hidden=!event.target.value;renderCatalog();loadDecision(event.target.value);});
  $('#clear-catalog-query').addEventListener('click',()=>{$('#catalog-query').value='';shop.query='';shop.page=1;$('#clear-catalog-query').hidden=true;renderCatalog();loadDecision('');$('#catalog-query').focus();});
  $('#clear-catalog-search').addEventListener('click',()=>{$('#catalog-query').value='';shop.query='';shop.categoryPath=[];shop.rankableOnly=false;shop.sort='relevance';shop.page=1;$('#catalog-rankable').checked=false;$('#catalog-sort').value='relevance';renderCategoryFilters();renderCatalog();loadDecision('');$('#catalog-query').focus();});
  $('#catalog-rankable').addEventListener('change',event=>{shop.rankableOnly=event.target.checked;shop.page=1;renderCatalog();});
  $('#catalog-sort').addEventListener('change',event=>{shop.sort=event.target.value;shop.page=1;renderCatalog();});
  $('#catalog-prev').addEventListener('click',()=>{if(shop.page>1){shop.page-=1;renderCatalog();$('#catalog-title').scrollIntoView({behavior:'smooth',block:'start'});}});
  $('#catalog-next').addEventListener('click',()=>{shop.page+=1;renderCatalog();$('#catalog-title').scrollIntoView({behavior:'smooth',block:'start'});});
  $('#business-start').addEventListener('click',()=>showMainView('workflow'));
  $('#business-catalog').addEventListener('click',()=>showMainView('storefront'));
  $('#back-to-catalog').addEventListener('click',()=>showMainView('storefront'));
  loadCatalog();
});
