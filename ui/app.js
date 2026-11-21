const $ = (id) => document.getElementById(id);
const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = (value) => escape(JSON.stringify(value, null, 2));
let selected = null;
let launching = false;
let lastRender = '';

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function details(title, content, id) {
  return `<details id="${id}"><summary>${title}</summary><pre>${content}</pre></details>`;
}

function render(run) {
  const signature = JSON.stringify(run);
  if (signature === lastRender) return;
  lastRender = signature;
  const open = [...document.querySelectorAll('details[open]')].map(el => el.id);
  const steps = run.plan?.steps || [];
  const report = run.validation;
  const events = run.turns.flatMap(turn => turn.steps || []);
  const toolResults = events.filter(event => event.type === 'code_execution_result');
  const toolCalls = events.filter(event => event.type === 'code_execution_call');
  const completed = run.turns.length && run.turns.every(turn => turn.status === 'completed');
  const downloaded = !!(run.plan || run.verified_result);
  const duration = steps.length ? Math.max(...steps.map(s => Number(s.start_s) + Number(s.duration_s))) : 0;
  const finiteDuration = Number.isFinite(duration) && duration > 0 ? duration : 1;
  const stages = [['Agent started', run.turns.length > 0], ['Agent completed', completed], ['Artifact retrieved', downloaded], ['Result verified', run.status === 'passed']];
  $('detail').innerHTML = `
    <div class="detail-header"><div><h2>${escape(run.label)}</h2><div class="mono">${escape(run.id)}</div></div><span class="badge ${escape(run.status)}">${escape(run.status)}</span></div>
    <div class="stages">${stages.map(([label, done], i) => `<div class="stage ${done ? 'done' : ''}">0${i+1} / ${label}</div>`).join('')}</div>
    ${run.kind === 'workcell-trials' ? `
    <div class="metrics"><div class="metric"><strong>${steps.length || '—'}</strong><span>PLANNED OPERATIONS</span></div><div class="metric"><strong>${report ? escape(report.errors.length) : '—'}</strong><span>VALIDATION ERRORS</span></div><div class="metric"><strong>${report?.makespan_s != null ? escape(report.makespan_s) + 's' : '—'}</strong><span>MODELED MAKESPAN</span></div></div>
    ${run.task ? `<div class="panel"><h3>The procedure</h3><p class="note">${escape(run.task.procedure)}</p></div>` : ''}
    ${steps.length ? `<div class="panel"><h3>Operation schedule</h3>${steps.map(step => {
      const start = Math.max(0, Math.min(100, Number(step.start_s) / finiteDuration * 100)) || 0;
      const width = Math.max(0, Math.min(100 - start, Number(step.duration_s) / finiteDuration * 100)) || 0;
      return `<div class="timeline-row"><div class="timeline-label">${escape(step.operation)}<small>${escape(step.machine)}</small></div><div class="track"><div class="bar" style="margin-left:${start}%;width:${width}%">${escape(step.duration_s)}s</div></div><span class="mono">${escape(step.start_s)}s</span></div>`;
    }).join('')}<p class="note">Declared operation timings, not measured execution. All steps reserve fixture_1.</p></div>` : `<div class="panel empty">${run.status === 'running' ? 'The agent is building a task graph and assigning equipment…' : 'No generated plan is available for this run.'}</div>`}
    ${report ? `<div class="panel"><h3>Independent verification</h3>${report.passed ? `<div class="checks">${['All operations present','Dependency order','Machine capabilities','Resource conflicts','Symbolic goal state'].map(x => `<span class="check">✓ ${x}</span>`).join('')}</div>` : `<pre>${pretty(report.errors)}</pre>`}<p class="note">Local validator uses trusted task semantics, not the agent’s self-reported success.</p></div>` : ''}
    ${report?.final_state ? `<div class="panel"><h3>Symbolic final state</h3><div class="state-grid">${Object.entries(report.final_state).map(([key,value]) => `<div class="state"><small>${escape(key)}</small><strong>${escape(value)}</strong></div>`).join('')}</div><p class="note">Inspection passes by assumption in this toy model. No camera or physical robot was used.</p><div class="trace">${(report.trace || []).map(t => `<p>${escape(t.operation)}<br><small class="mono">${escape(Object.entries(t.state).map(([k,v])=>`${k}: ${v}`).join(' · '))}</small></p>`).join('')}</div></div>` : ''}
    ` : `<div class="panel"><h3>Sandbox persistence test</h3><p class="note">Two agent turns create and update a file. Its downloaded contents are checked independently.</p>${run.verified_result ? `<pre>${pretty(run.verified_result)}</pre>` : ''}</div>`}
    ${toolCalls.length ? `<div class="panel"><h3>Agent tool activity · ${toolCalls.length} code calls</h3><p class="note">${toolResults.filter(event => event.is_error).length} tool errors recorded. Final validation and intermediate tool outcomes are separate.</p>${toolCalls.map((call, index) => {
      const result = toolResults.find(event => event.call_id === call.id);
      return details(`Attempt ${index + 1} · ${result ? (result.is_error ? 'tool error' : 'tool completed') : 'awaiting result'}`, escape(call.arguments?.code || '') + '\n\n' + escape(result?.result || ''), `tool-${index}`);
    }).join('')}</div>` : ''}
    ${details('Live runner output', escape(run.logs.join('\n') || 'No live log retained. Saved agent responses are available below.'), 'logs')}
    ${run.plan ? details('Generated plan JSON', pretty(run.plan), 'plan') : ''}
    ${report ? details('Validator report', pretty(report), 'report') : ''}
    ${details('Agent responses / tool events', pretty(run.turns), 'events')}
    <p class="mono">${escape(run.artifact_path)}</p>`;
  open.forEach(id => { if ($(id)) $(id).open = true; });
}

async function refresh() {
  try {
    const data = await api('/api/runs');
    $('connection').textContent = 'Local connection · live';
    $('count').textContent = data.runs.length;
    $('launch').disabled = launching || !!data.active?.running;
    $('launch').textContent = data.active?.running ? '● Trial running…' : '＋ Run planning trial';
    if (data.active?.running && data.active.run_id && launching) {
      selected = `workcell-trials/${data.active.run_id}`;
      launching = false;
    }
    if (launching && data.active && !data.active.running) {
      launching = false;
      if (data.active.run_id) selected = `workcell-trials/${data.active.run_id}`;
      else throw new Error(data.active.logs.join('\n') || 'Trial failed before creating artifacts.');
    }
    if (!selected && data.runs.length) selected = `${data.runs[0].kind}/${data.runs[0].id}`;
    $('runs').innerHTML = data.runs.map(run => {
      const key = `${run.kind}/${run.id}`;
      return `<button class="run ${selected === key ? 'selected' : ''}" data-run="${escape(key)}"><span class="badge ${escape(run.status)}">${escape(run.status)}</span><strong>${escape(run.label)}</strong><small>${escape(new Date(run.created).toLocaleString())}<br>${escape(run.id.slice(0,12))}</small></button>`;
    }).join('') || '<p class="note">Your trials will appear here.</p>';
    if (selected) {
      const target = selected;
      const run = await api(`/api/runs/${target}`);
      if (target === selected) render(run);
    }
  } catch (error) {
    $('connection').textContent = 'Check connection';
    $('error').hidden = false;
    $('error').textContent = error.message;
  }
}

$('runs').addEventListener('click', event => {
  const button = event.target.closest('[data-run]');
  if (button) { selected = button.dataset.run; refresh(); }
});
$('launch').addEventListener('click', async () => {
  launching = true;
  $('launch').disabled = true;
  $('error').hidden = true;
  try {
    await api('/api/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    await refresh();
  } catch (error) {
    launching = false;
    $('launch').disabled = false;
    $('error').hidden = false;
    $('error').textContent = error.message;
  }
});
async function poll() { await refresh(); setTimeout(poll, 2000); }
poll();
