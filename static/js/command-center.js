// Odysseus Command Center — Hermes intelligence layer view
// Fetches live state and renders: system health, current identity, mission counters, agent status, workspace files, approvals queue

const API_BASE = window.location.origin;

async function odysseusFetch(path) {
  const res = await fetch(`${API_BASE}${path}`, { credentials: 'same-origin' });
  if (!res.ok) throw new Error(`${path} => ${res.status}`);
  return res.json();
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = value ?? '';
}

function setHtml(id, html) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = html;
}

function classForStatus(status) {
  if (!status) return 'muted';
  const s = String(status).toLowerCase();
  if (['healthy', 'ready', 'completed', 'active', 'ok'].includes(s)) return 'success';
  if (['error', 'failed', 'unhealthy'].includes(s)) return 'danger';
  if (['running', 'degraded', 'pending', 'in_progress'].includes(s)) return 'warn';
  return 'muted';
}

function badge(text) {
  return `<span class="badge ${classForStatus(text)}">${text}</span>`;
}

async function refreshAll() {
  setText('cmd-status-indicator', 'loading');
  setHtml('cmd-section-health', '<div>loading...</div>');
  setHtml('cmd-section-missions', '<div>loading...</div>');

  let health = {};
  let auth = {};
  let agents = [];
  try {
    const [h, a, ag] = await Promise.all([
      odysseusFetch('/api/health').catch(() => ({})),
      odysseusFetch('/api/auth/status').catch(() => ({})),
      odysseusFetch('/api/async-agents').catch(() => ({items: []})),
    ]);
    health = h || {};
    auth = a || {};
    agents = (ag && ag.items) ? ag.items : [];
  } catch (e) {
    setHtml('cmd-section-health', `error: ${e.message}`);
  }

  setText('cmd-status-indicator', health.status || health.state || 'ready');

  // Health
  const rows = [
    ['Platform Status', (health.status || health.state || 'unknown')],
    ['Runtime Status', health.runtime_status || ''],
    ['Hermes', health.hermes_status || ''],
    ['Runtime State', health.runtime_state || ''],
    ['Environment', health.env || ''],
    ['DB', health.db_status || ''],
    ['Update', String(health.update_available ?? '')],
  ];
  rows.forEach(([label, value]) => {
    const target = document.getElementById('cmd-section-health');
    if (!target) return;
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${label}</td><td>${badge(value || '—')}</td>`;
    target.appendChild(tr);
  });

  // Identity + privileges
  setText('cmd-identity', auth.username || '—');
  const priv = (auth.privileges && Array.isArray(auth.privileges))
    ? auth.privileges.join(', ')
    : '';
  setText('cmd-privileges', priv || 'default');
  setText('cmd-signup-enabled', String(Boolean(auth.signup_enabled)));

  // Mission counters: agents resource
  const total = agents.length;
  const active = agents.filter((x) => String((x.status || '')).toLowerCase() === 'active').length;
  setText('cmd-total-missions', String(total));
  setText('cmd-active-missions', String(active));
  setHtml(
    'cmd-agents',
    agents
      .slice()
      .sort((a, b) => (String(a.agent_id || '').localeCompare(String(b.agent_id || ''))))
      .map((x) => {
        const role = x.role || '';
        const status = x.status || '';
        const owner = (x.reporting && x.reporting.owner) || '';
        const tags = Array.isArray(x.tags) ? x.tags.join(', ') : '';
        return `
          <div class="row">
            <div>
              <div class="title">${x.display_name || x.agent_id}</div>
              <div class="sub">${role}${owner ? ' · ' + owner : ''}${tags ? ' · ' + tags : ''}</div>
            </div>
            <div class="actions">${badge(status)}</div>
          </div>
          <div class="divider" />`;
      })
      .join('') || '<div class="sub">No agents configured.</div>',
  );

  // Workspace + approvals queue
  try {
    const tasks = await odysseusFetch('/api/tasks').catch(() => ({tasks: []}));
    renderTaskQueue(tasks.tasks || []);
  } catch (_) {}
}

function renderTaskQueue(tasks) {
  const container = document.getElementById('cmd-approvals');
  if (!container) return;

  const pending = tasks
    .filter((t) => String(t.status || '').toLowerCase() === 'pending')
    .slice(0, 50);

  if (!pending.length) {
    container.innerHTML = '<div class="sub">No pending approvals.</div>';
    return;
  }

  container.innerHTML = pending
    .map((t) => `
      <button class="link-btn" type="button" data-task-id="${t.task_id || t.id || ''}">
        ${t.task_id || t.id} — ${t.kind || 'task'}
      </button>`)
    .join('');
}

function initCommandCenter() {
  refreshAll();
}

export default { initCommandCenter };
