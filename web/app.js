'use strict';
(() => {
  const byId = id => document.getElementById(id);
  const make = (tag, className, text) => {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = String(text);
    return item;
  };
  let benchReport = null;
  let planReport = null;
  let demo = null;

  async function request(route, data) {
    const response = await fetch(route, {
      method: data === undefined ? 'GET' : 'POST',
      cache: 'no-store',
      headers: data === undefined ? {} : {
        'Content-Type': 'application/json', 'X-SqlBench-Request': '1'
      },
      body: data === undefined ? undefined : JSON.stringify(data)
    });
    const parsed = await response.json();
    if (!response.ok) throw new Error(parsed?.error?.message || `HTTP ${response.status}`);
    return parsed;
  }

  function message(id, content, level = '') {
    const element = byId(id);
    element.className = 'message' + (level ? ` ${level}` : '');
    element.textContent = content;
  }
  function busy(flag) {
    ['runSingle','runCompare','inspectPlan','comparePlans'].forEach(id => byId(id).disabled = flag);
  }
  function setTab(tab) {
    if (!['benchmark','plans','about'].includes(tab)) return;
    for (const section of document.querySelectorAll('.tab-view')) section.hidden = section.id !== tab;
    for (const button of document.querySelectorAll('[data-tab]')) {
      const active = button.dataset.tab === tab;
      button.classList.toggle('active',active);
      if (active) button.setAttribute('aria-current','page');
      else button.removeAttribute('aria-current');
    }
    byId('currentTab').textContent = {benchmark:'Benchmark Lab',plans:'Plan Inspector',about:'About & Safety'}[tab];
  }

  function addCard(container, title, number, note, className) {
    const el = make('article','result-card');
    el.append(make('span','',title));
    el.append(make('b',className || '',number));
    el.append(make('small','',note));
    container.append(el);
  }
  function showBench(report) {
    benchReport = report;
    byId('benchmarkResults').hidden = false;
    const cards = byId('benchCards'); cards.replaceChildren();
    const hasComparison = Boolean(report?.comparison);
    const left = hasComparison ? report.before : report;
    const right = hasComparison ? report.after : null;
    addCard(cards,'Baseline median',`${left.median_ms.toFixed(3)} ms`,'Warm-cache, local SQLite');
    if (right) {
      addCard(cards,'Candidate median',`${right.median_ms.toFixed(3)} ms`,'Measured on a synthetic copy');
      const delta = report.comparison.median_time_reduction_percent;
      addCard(cards,'Median time reduction',`${delta >= 0 ? '+' : ''}${delta.toFixed(2)}%`,
        'Positive means candidate was faster',delta>0?'good':'bad');
      addCard(cards,'Observed result match',report.comparison.same_results_in_demo?'YES':'NO',
        'Result fingerprints on test data',report.comparison.same_results_in_demo?'good':'bad');
    } else {
      addCard(cards,'P95 latency',`${left.p95_ms.toFixed(3)} ms`,'95th percentile');
      addCard(cards,'Result rows',left.row_count,'Per query execution');
      addCard(cards,'Stable results',left.results_consistent?'YES':'NO','Across measured iterations',
        left.results_consistent?'good':'bad');
    }
    const barHolder=byId('timingBars'); barHolder.replaceChildren();
    const samples = left.timings_ms.map((ms,i)=>({ms,label:'A'+(i+1),alt:false}));
    if (right) right.timings_ms.forEach((ms,i)=>samples.push({ms,label:'B'+(i+1),alt:true}));
    const max = Math.max(0.001,...samples.map(s=>s.ms));
    samples.forEach(sample=>{
      const wrap=make('div','bar-column'+(sample.alt?' alt':''));
      const bar=make('div','bar');
      bar.style.height = `${Math.max(5,sample.ms/max*123)}px`;
      bar.title = `${sample.label}: ${sample.ms.toFixed(4)} ms`;
      wrap.append(bar,make('span','',sample.label));
      barHolder.append(wrap);
    });
    byId('benchJSON').textContent=JSON.stringify(report,null,2);
  }
  async function benchmark(compare) {
    const sql=byId('sqlBefore').value;
    const after=byId('sqlAfter').value;
    const iterations=Number(byId('iterations').value);
    const warmups=Number(byId('warmups').value);
    if (!sql.trim() || (compare && !after.trim())) {
      return message('benchmarkMessage','Enter the required SQL query text first.','error');
    }
    busy(true); message('benchmarkMessage','Running bounded benchmark on synthetic data...');
    try {
      const body=compare ? {before:sql,after,iterations,warmups}:{sql,iterations,warmups};
      const response=await request(compare?'/api/benchmark/compare':'/api/benchmark',body);
      showBench(response.result);
      message('benchmarkMessage',compare ?
        'Comparison complete. Do not interpret small timing differences as statistically conclusive.' :
        'Benchmark complete. Timing is machine-dependent.','success');
    } catch (error) {message('benchmarkMessage',error.message,'error');}
    finally {busy(false);}
  }

  function showPlan(report) {
    planReport=report; byId('planResults').hidden=false;
    const cards=byId('planCards');cards.replaceChildren();
    const comparison=report.comparison;
    const before=comparison?report.before:report;
    const after=comparison?report.after:null;
    addCard(cards,'Baseline cost',before.estimated_statement_cost_total,'Estimated optimizer units');
    if(after){
      addCard(cards,'Candidate cost',after.estimated_statement_cost_total,'Estimated optimizer units');
      addCard(cards,'Estimated cost change',comparison.estimated_cost_delta_percent===null?'N/A':
        `${comparison.estimated_cost_delta_percent.toFixed(2)}%`,'Not execution milliseconds');
      addCard(cards,'Operators (before → after)',`${before.operator_count} → ${after.operator_count}`,
        'Relative plan shape');
    } else {
      addCard(cards,'Operator count',before.operator_count,'Relational operations');
      addCard(cards,'Statements',before.statement_count,'Query statements found');
      addCard(cards,'Missing-index hints',before.missing_indexes.length,'Requires workload review');
    }
    const findings=byId('planFindings');findings.replaceChildren();
    const reported=(after?[...before.findings.map(x=>({...x,where:'A'})),
      ...after.findings.map(x=>({...x,where:'B'}))]:before.findings);
    reported.forEach(f=>{
      const label=make('div','finding'+(f.level==='warning'?' warning':''),
        `${f.where?f.where+' · ':''}${f.message}`);
      findings.append(label);
    });
    byId('planJSON').textContent=JSON.stringify(report,null,2);
  }
  async function inspectPlan(compare) {
    const xml=byId('planBefore').value;
    const after=byId('planAfter').value;
    if(!xml.trim() || (compare && !after.trim())){
      return message('planMessage','Please load a plan XML file for each required input.','error');
    }
    busy(true);message('planMessage','Analyzing SQL Server execution plan XML...');
    try{
      const response=await request(compare?'/api/plan/compare':'/api/plan',
        compare?{before:xml,after}:{xml});
      showPlan(response.result);
      message('planMessage','Plan analysis complete. Optimizer costs are estimates only.','success');
    }catch(error){message('planMessage',error.message,'error');}
    finally{busy(false);}
  }
  function downloadJSON(name,report){
    if(!report)return;
    const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);
    const link=make('a');link.href=url;link.download=name;
    document.body.append(link);link.click();link.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function loadFile(inputId,fieldId){
    const input=byId(inputId);
    const file=input.files?.[0];
    if(!file)return;
    if(file.size>2*1024*1024){
      message('planMessage','Maximum supported plan size is 2 MiB.','error');return;
    }
    try {byId(fieldId).value=await file.text();message('planMessage',
      `${file.name} loaded locally. Ready to analyze.`,'success');}
    catch {message('planMessage','Could not read selected file.','error');}
  }
  function applyExamples(){
    if(!demo)return;
    byId('sqlBefore').value=demo.before;
    byId('sqlAfter').value=demo.after;
    message('benchmarkMessage','Example queries loaded. Compare to see runtime and result fingerprints.');
  }
  function applyPlanExamples(){
    if(!demo)return;
    byId('planBefore').value=demo.plan_before;
    byId('planAfter').value=demo.plan_after;
    message('planMessage','Synthetic SQL Server plan fixtures loaded.','success');
  }
  async function init(){
    document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',
      ()=>setTab(button.dataset.tab)));
    byId('runSingle').addEventListener('click',()=>benchmark(false));
    byId('runCompare').addEventListener('click',()=>benchmark(true));
    byId('inspectPlan').addEventListener('click',()=>inspectPlan(false));
    byId('comparePlans').addEventListener('click',()=>inspectPlan(true));
    byId('downloadBench').addEventListener('click',()=>downloadJSON('sql-benchmark-report.json',benchReport));
    byId('downloadPlan').addEventListener('click',()=>downloadJSON('sql-plan-report.json',planReport));
    byId('loadExamples').addEventListener('click',applyExamples);
    byId('loadPlanExamples').addEventListener('click',applyPlanExamples);
    byId('fileBefore').addEventListener('change',()=>loadFile('fileBefore','planBefore'));
    byId('fileAfter').addEventListener('change',()=>loadFile('fileAfter','planAfter'));
    try{
      await request('/api/health');
      demo=await request('/api/demo');
      applyExamples();applyPlanExamples();
      byId('connectionStatus').textContent='● Local engine connected';
    }catch(error){
      byId('connectionStatus').textContent='● Local engine unavailable';
      message('benchmarkMessage',error.message,'error');
    }
  }
  document.addEventListener('DOMContentLoaded',init);
})();
