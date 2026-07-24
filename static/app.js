const state = {
  dashboard: null,
  leads: [],
  opportunities: [],
  selectedOpportunityId: null,
  category: 'All',
};

const titles = {
  overview: 'Command Center',
  opportunities: 'Opportunities',
  leads: 'Lead Intelligence',
  advisor: 'AI Advisor',
  architecture: 'How MoodyAI Works',
};

const assetGroups = [
  {
    label: 'Content',
    items: [
      { type: 'blog_article', label: 'Blog Article', description: 'Create a complete long-form article.' },
      { type: 'linkedin_post', label: 'LinkedIn Post', description: 'Create a professional social post.' },
      { type: 'facebook_post', label: 'Facebook Post', description: 'Create a useful, conversational post.' },
      { type: 'video_script', label: 'Video Script', description: 'Create a concise 2–3 minute script.' },
      { type: 'google_ads', label: 'Google Ads', description: 'Create focused search-ad concepts.' },
    ],
  },
  {
    label: 'Client Communication',
    items: [
      { type: 'text_message', label: 'Client Text', description: 'Create a short, personal outreach message.' },
      { type: 'followup_email', label: 'Follow-up Email', description: 'Create a concise, relevant email.' },
      { type: 'call_script', label: 'Call Script', description: 'Create a natural conversation guide.' },
    ],
  },
];

const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  "'": '&#39;',
  '"': '&quot;',
}[character]));

const fmtCurrency = value => new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
}).format(Number(value || 0));

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const payload = await response.json();
      if (payload.detail) message = payload.detail;
    } catch (_) {
      // Keep the status-based message.
    }
    throw new Error(message);
  }
  return response.json();
}

function activateView(name) {
  document.querySelectorAll('.view').forEach(view => view.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
  document.getElementById(`${name}-view`).classList.add('active');
  document.querySelector(`.nav-item[data-view="${name}"]`)?.classList.add('active');
  document.getElementById('pageTitle').textContent = titles[name];
  document.querySelector('.sidebar').classList.remove('open');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function categoryClass(category = '') {
  return String(category).toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

function urgencyClass(urgency = '') {
  const value = String(urgency).toLowerCase();
  if (value === 'immediate') return 'urgent';
  if (value === 'high') return 'high';
  if (value === 'medium') return 'medium';
  return 'low';
}

function opportunityRevenue(opportunity) {
  const revenue = opportunity.revenue || {};
  if (Number(revenue.high || 0) <= 0) return 'Not estimated';
  if (Number(revenue.low || 0) === Number(revenue.high || 0)) return fmtCurrency(revenue.high);
  return `${fmtCurrency(revenue.low)}–${fmtCurrency(revenue.high)}`;
}

function setEnvironment(data) {
  const isDemo = data.mode !== 'live';
  const badge = document.getElementById('environmentBadge');
  badge.textContent = isDemo ? 'Demo environment' : 'Live environment';
  badge.classList.toggle('live', !isDemo);
  document.getElementById('demoNote').hidden = !isDemo;
}

function renderDashboard(data) {
  state.dashboard = data;
  const top = data.top_opportunity;
  setEnvironment(data);

  document.getElementById('systemMode').textContent = data.opportunity_mode === 'live'
    ? 'Current opportunity report'
    : 'Representative business data';

  document.getElementById('metricsGrid').innerHTML = data.metrics.map(metric => `
    <article class="metric-card">
      <span>${escapeHtml(metric.label)}</span>
      <strong>${escapeHtml(metric.value)}</strong>
      <small>${escapeHtml(metric.detail)}</small>
    </article>
  `).join('');

  document.getElementById('systemStatus').innerHTML = Object.entries(data.system).map(([key, value]) => `
    <div class="system-item"><span>${escapeHtml(key)}</span><span>${escapeHtml(value)}</span></div>
  `).join('');

  document.getElementById('topOpportunityTitle').textContent = top.title;
  document.getElementById('topOpportunitySummary').textContent = top.executive_summary;
  document.getElementById('topOpportunityScore').textContent = top.opportunity_score;
  document.getElementById('topOpportunityBar').style.width = `${Number(top.opportunity_score || 0)}%`;
  document.getElementById('topOpportunityConfidence').textContent = `${top.confidence_percent}% · ${top.confidence_level}`;
  document.getElementById('topOpportunityUrgency').textContent = top.urgency;
  document.getElementById('topOpportunityHorizon').textContent = top.time_horizon || 'Not specified';
  document.getElementById('topOpportunityBadges').innerHTML = `
    <span class="category-pill ${categoryClass(top.category)}">${escapeHtml(top.category)}</span>
    <span class="urgency-pill ${urgencyClass(top.urgency)}">${escapeHtml(top.urgency)}</span>
  `;

  const firstAction = (top.actions || []).slice().sort((a, b) => Number(a.priority || 99) - Number(b.priority || 99))[0];
  const firstActionNode = document.getElementById('topFirstAction');
  if (firstAction) {
    firstActionNode.hidden = false;
    firstActionNode.innerHTML = `<span>Recommended first action</span><strong>${escapeHtml(firstAction.title)}</strong>`;
  } else {
    firstActionNode.hidden = true;
  }

  document.getElementById('viewTopOpportunity').onclick = () => openOpportunity(top.opportunity_id);
}

function opportunityPreviewCard(opportunity, rank) {
  return `
    <button class="preview-opportunity" data-opportunity-id="${escapeHtml(opportunity.opportunity_id)}">
      <span class="preview-rank">${String(rank).padStart(2, '0')}</span>
      <span class="preview-copy">
        <b>${escapeHtml(opportunity.title)}</b>
        <small>${escapeHtml(opportunity.category)} · ${escapeHtml(opportunity.time_horizon || '')}</small>
      </span>
      <span class="preview-score">
        <b>${escapeHtml(opportunity.opportunity_score)}</b>
        <small>${escapeHtml(opportunity.confidence_percent)}% confidence</small>
      </span>
      <span class="preview-arrow">→</span>
    </button>
  `;
}

function renderOpportunityPreview(items) {
  document.getElementById('opportunityPreview').innerHTML = items.slice(0, 4)
    .map((item, index) => opportunityPreviewCard(item, index + 1))
    .join('');

  document.querySelectorAll('.preview-opportunity').forEach(button => {
    button.addEventListener('click', () => openOpportunity(button.dataset.opportunityId));
  });
}

function renderTodayActions(items) {
  const actions = [];
  items.forEach(opportunity => {
    (opportunity.actions || []).forEach(action => {
      if (String(action.timeframe || '').toLowerCase() === 'today' && !action.completed) {
        actions.push({ ...action, opportunity: opportunity.title });
      }
    });
  });

  actions.sort((a, b) => Number(a.priority || 99) - Number(b.priority || 99));
  document.getElementById('todayActions').innerHTML = actions.length
    ? actions.slice(0, 5).map((action, index) => `
      <article class="today-action">
        <span>${index + 1}</span>
        <div>
          <b>${escapeHtml(action.title)}</b>
          <small>${escapeHtml(action.opportunity)}</small>
          <p>${escapeHtml(action.description || action.expected_result || '')}</p>
        </div>
      </article>
    `).join('')
    : '<p class="muted-copy">No immediate actions are assigned. Review the ranked opportunities for the next best move.</p>';
}

function renderFilters(items) {
  const categories = ['All', ...new Set(items.map(item => item.category).filter(Boolean))];
  document.getElementById('opportunityFilters').innerHTML = categories.map(category => `
    <button class="filter-button ${state.category === category ? 'active' : ''}" data-category="${escapeHtml(category)}">${escapeHtml(category)}</button>
  `).join('');

  document.querySelectorAll('.filter-button').forEach(button => {
    button.addEventListener('click', () => {
      state.category = button.dataset.category;
      renderFilters(state.opportunities);
      renderOpportunityList(state.opportunities);
    });
  });
}

function renderOpportunityList(items) {
  const filtered = state.category === 'All'
    ? items
    : items.filter(item => item.category === state.category);

  document.getElementById('opportunityList').innerHTML = filtered.length
    ? filtered.map(item => `
      <button class="opportunity-card ${state.selectedOpportunityId === item.opportunity_id ? 'active' : ''}" data-opportunity-id="${escapeHtml(item.opportunity_id)}">
        <div class="opportunity-card-top">
          <span class="rank-label">#${String(items.indexOf(item) + 1).padStart(2, '0')}</span>
          <span class="urgency-pill ${urgencyClass(item.urgency)}">${escapeHtml(item.urgency)}</span>
        </div>
        <div class="opportunity-card-score"><strong>${escapeHtml(item.opportunity_score)}</strong><span>/100</span></div>
        <span class="category-pill ${categoryClass(item.category)}">${escapeHtml(item.category)}</span>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.executive_summary)}</p>
        <footer><span>${escapeHtml(item.confidence_percent)}% confidence</span><span>${escapeHtml(item.time_horizon || '')}</span></footer>
      </button>
    `).join('')
    : '<div class="empty-state">No opportunities match this filter.</div>';

  document.querySelectorAll('.opportunity-card').forEach(button => {
    button.addEventListener('click', () => selectOpportunity(button.dataset.opportunityId));
  });
}

function renderEvidence(items = []) {
  return items.length
    ? items.map(item => `
      <article class="evidence-item">
        <span>✓</span>
        <div>
          <b>${escapeHtml(item.statement)}</b>
          <small>${escapeHtml(item.source || 'Source not specified')}${item.metric && item.value ? ` · ${escapeHtml(item.metric)}: ${escapeHtml(item.value)}` : ''}</small>
        </div>
      </article>
    `).join('')
    : '<p class="muted-copy">No supporting evidence was recorded for this opportunity.</p>';
}

function renderBullets(items = []) {
  return items.length
    ? items.map(item => `<li>${escapeHtml(item)}</li>`).join('')
    : '<li>No additional details were recorded.</li>';
}

function renderActions(items = []) {
  return items.length
    ? items.slice().sort((a, b) => Number(a.priority || 99) - Number(b.priority || 99)).map(action => `
      <article class="detail-action">
        <span class="action-priority">P${escapeHtml(action.priority || 1)}</span>
        <div>
          <div class="action-heading"><b>${escapeHtml(action.title)}</b><span>${escapeHtml(action.timeframe || '')}</span></div>
          <p>${escapeHtml(action.description || '')}</p>
          ${action.expected_result ? `<small>Expected result: ${escapeHtml(action.expected_result)}</small>` : ''}
        </div>
      </article>
    `).join('')
    : '<p class="muted-copy">No next steps were assigned.</p>';
}

function renderActionCenter() {
  return `
    <section class="detail-section action-center-section">
      <p class="section-label">ACTION CENTER</p>
      <h3>Choose how to act on this opportunity</h3>
      <p class="action-center-intro">Generate a finished draft or open the underlying prompt and customize the approach.</p>
      <div class="action-center-groups">
        ${assetGroups.map(group => `
          <div class="asset-group">
            <h4>${escapeHtml(group.label)}</h4>
            <div class="asset-list">
              ${group.items.map(asset => `
                <article class="asset-row" data-asset-type="${escapeHtml(asset.type)}">
                  <div class="asset-copy">
                    <strong>${escapeHtml(asset.label)}</strong>
                    <span>${escapeHtml(asset.description)}</span>
                  </div>
                  <div class="asset-actions">
                    <button class="execution-button primary" data-action="generate" data-asset-type="${escapeHtml(asset.type)}">Done for Me</button>
                    <button class="execution-button" data-action="prompt" data-asset-type="${escapeHtml(asset.type)}">Prompt</button>
                  </div>
                  <div class="asset-help">
                    <span><b>Done for Me</b> generates a polished draft.</span>
                    <span><b>Prompt</b> lets you customize the instructions first.</span>
                  </div>
                </article>
              `).join('')}
            </div>
          </div>
        `).join('')}
      </div>
      <div class="execution-workspace" id="executionWorkspace" hidden></div>
    </section>
  `;
}

function selectOpportunity(id) {
  const opportunity = state.opportunities.find(item => item.opportunity_id === id);
  if (!opportunity) return;

  state.selectedOpportunityId = id;
  renderOpportunityList(state.opportunities);

  const revenue = opportunity.revenue || {};
  const transactionRange = Number(revenue.transaction_high || 0) > 0
    ? `${revenue.transaction_low || 0}${revenue.transaction_low !== revenue.transaction_high ? `–${revenue.transaction_high}` : ''}`
    : 'Not estimated';

  const detail = document.getElementById('opportunityDetail');
  detail.className = 'opportunity-detail';
  detail.innerHTML = `
    <header class="detail-header">
      <div class="detail-kickers">
        <span class="category-pill ${categoryClass(opportunity.category)}">${escapeHtml(opportunity.category)}</span>
        <span class="urgency-pill ${urgencyClass(opportunity.urgency)}">${escapeHtml(opportunity.urgency)}</span>
      </div>
      <p class="section-label detail-opportunity-label">BUSINESS OPPORTUNITY</p>
      <h2>${escapeHtml(opportunity.title)}</h2>
      <p>${escapeHtml(opportunity.executive_summary)}</p>
      <div class="detail-score-grid">
        <article><span>Score</span><strong>${escapeHtml(opportunity.opportunity_score)}</strong><small>/100</small></article>
        <article><span>Confidence</span><strong>${escapeHtml(opportunity.confidence_percent)}%</strong><small>${escapeHtml(opportunity.confidence_level)}</small></article>
        <article><span>Revenue</span><strong class="smaller">${escapeHtml(opportunityRevenue(opportunity))}</strong><small>${escapeHtml(revenue.basis || '')}</small></article>
        <article><span>Transactions</span><strong>${escapeHtml(transactionRange)}</strong><small>${escapeHtml(opportunity.time_horizon || '')}</small></article>
      </div>
    </header>
    <section class="detail-section highlight-section">
      <p class="section-label">WHY NOW</p>
      <h3>The decision window</h3>
      <p>${escapeHtml(opportunity.why_now)}</p>
    </section>
    <section class="detail-section">
      <p class="section-label">WHAT WE FOUND</p>
      <h3>Supporting evidence</h3>
      <div class="evidence-list">${renderEvidence(opportunity.evidence)}</div>
    </section>
    <section class="detail-section">
      <p class="section-label">WHY THIS MATTERS</p>
      <h3>The business case</h3>
      <ol class="reasoning-list">${renderBullets(opportunity.reasoning)}</ol>
    </section>
    <section class="detail-section">
      <p class="section-label">RECOMMENDED NEXT STEPS</p>
      <h3>What to do next</h3>
      <div class="detail-actions">${renderActions(opportunity.actions || [])}</div>
    </section>
    ${renderActionCenter()}
    <section class="detail-section two-column-detail">
      <div>
        <p class="section-label">EXPECTED OUTCOME</p>
        <h3>What success looks like</h3>
        <p>${escapeHtml(opportunity.expected_outcome)}</p>
      </div>
      <div>
        <p class="section-label">RISKS</p>
        <h3>What could limit results</h3>
        <ul class="risk-list">${renderBullets(opportunity.risks)}</ul>
      </div>
    </section>
  `;

  bindActionCenter();
  detail.scrollTop = 0;
}

function bindActionCenter() {
  document.querySelectorAll('.execution-button').forEach(button => {
    button.addEventListener('click', () => {
      const assetType = button.dataset.assetType;
      if (button.dataset.action === 'generate') {
        generateAsset(assetType, button);
      } else {
        openPromptEditor(assetType, button);
      }
    });
  });
}

function selectedOpportunity() {
  return state.opportunities.find(item => item.opportunity_id === state.selectedOpportunityId);
}

function setRowBusy(assetType, busy, activeButton = null) {
  const row = document.querySelector(`.asset-row[data-asset-type="${assetType}"]`);
  if (!row) return;
  row.querySelectorAll('button').forEach(button => {
    button.disabled = busy;
    if (!busy) {
      button.textContent = button.dataset.action === 'generate' ? 'Done for Me' : 'Prompt';
    }
  });
  if (busy && activeButton) activeButton.textContent = activeButton.dataset.action === 'generate' ? 'Generating…' : 'Loading…';
}

function showWorkspace(html) {
  const workspace = document.getElementById('executionWorkspace');
  workspace.hidden = false;
  workspace.innerHTML = html;
  workspace.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  return workspace;
}

function loadingWorkspace(label) {
  return showWorkspace(`
    <div class="execution-panel loading-panel">
      <div class="execution-status"><span class="status-pulse"></span><div><strong>Creating ${escapeHtml(label)}</strong><small id="generationTimer">Starting…</small></div></div>
      <p id="generationMessage">Using the opportunity audience, evidence, reasoning, and business goal.</p>
    </div>
  `);
}

async function generateAsset(assetType, button, customPrompt = null) {
  const opportunity = selectedOpportunity();
  if (!opportunity) return;

  const asset = assetGroups.flatMap(group => group.items).find(item => item.type === assetType);
  const label = asset?.label || 'asset';
  setRowBusy(assetType, true, button);
  loadingWorkspace(label);

  const started = Date.now();
  const timer = window.setInterval(() => {
    const seconds = Math.max(1, Math.floor((Date.now() - started) / 1000));
    const timerNode = document.getElementById('generationTimer');
    const messageNode = document.getElementById('generationMessage');
    if (timerNode) timerNode.textContent = `${seconds} second${seconds === 1 ? '' : 's'}`;
    if (messageNode && seconds >= 8) messageNode.textContent = 'Still working. Longer assets can take a little more time.';
  }, 1000);

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 45000);

  try {
    const result = await request('/api/execution/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        opportunity_id: opportunity.opportunity_id,
        asset_type: assetType,
        prompt: customPrompt,
      }),
      signal: controller.signal,
    });
    renderGeneratedAsset(result);
  } catch (error) {
    const message = error.name === 'AbortError'
      ? 'Generation took too long. Please try again.'
      : error.message;
    showWorkspace(`
      <div class="execution-panel error-panel">
        <p class="section-label">COULD NOT COMPLETE</p>
        <h4>${escapeHtml(label)}</h4>
        <p>${escapeHtml(message)}</p>
        <button class="execution-button" id="closeExecution">Close</button>
      </div>
    `);
    document.getElementById('closeExecution')?.addEventListener('click', closeWorkspace);
  } finally {
    window.clearInterval(timer);
    window.clearTimeout(timeout);
    setRowBusy(assetType, false);
  }
}

function renderGeneratedAsset(result) {
  const grounding = result.grounding || [];
  showWorkspace(`
    <div class="execution-panel output-panel">
      <div class="execution-panel-heading">
        <div><p class="section-label">READY TO USE</p><h4>${escapeHtml(result.label)}</h4></div>
        <span class="generation-mode">${result.mode === 'live' ? 'Live AI' : 'Demo output'}</span>
      </div>
      <pre class="generated-output" id="generatedOutput">${escapeHtml(result.output)}</pre>
      <div class="execution-toolbar">
        <button class="execution-button primary" id="copyOutput">Copy</button>
        <button class="execution-button" id="regenerateOutput">Regenerate</button>
        <button class="execution-button quiet" id="closeExecution">Close</button>
      </div>
      <div class="grounding-note">
        <span>Built using</span>
        <div>${grounding.map(item => `<b>✓ ${escapeHtml(item)}</b>`).join('')}</div>
      </div>
    </div>
  `);

  document.getElementById('copyOutput')?.addEventListener('click', event => copyText(result.output, event.currentTarget));
  document.getElementById('regenerateOutput')?.addEventListener('click', event => generateAsset(result.asset_type, event.currentTarget, result.prompt));
  document.getElementById('closeExecution')?.addEventListener('click', closeWorkspace);
}

async function openPromptEditor(assetType, button) {
  const opportunity = selectedOpportunity();
  if (!opportunity) return;

  setRowBusy(assetType, true, button);
  const asset = assetGroups.flatMap(group => group.items).find(item => item.type === assetType);
  showWorkspace(`
    <div class="execution-panel loading-panel">
      <div class="execution-status"><span class="status-pulse"></span><div><strong>Preparing ${escapeHtml(asset?.label || 'prompt')}</strong><small>Loading editable instructions…</small></div></div>
    </div>
  `);

  try {
    const result = await request('/api/execution/prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ opportunity_id: opportunity.opportunity_id, asset_type: assetType }),
    });
    renderPromptEditor(result);
  } catch (error) {
    showWorkspace(`
      <div class="execution-panel error-panel">
        <p class="section-label">COULD NOT LOAD PROMPT</p>
        <p>${escapeHtml(error.message)}</p>
        <button class="execution-button" id="closeExecution">Close</button>
      </div>
    `);
    document.getElementById('closeExecution')?.addEventListener('click', closeWorkspace);
  } finally {
    setRowBusy(assetType, false);
  }
}

function renderPromptEditor(result) {
  showWorkspace(`
    <div class="execution-panel prompt-panel">
      <div class="execution-panel-heading">
        <div><p class="section-label">EDITABLE PROMPT</p><h4>${escapeHtml(result.label)}</h4></div>
      </div>
      <textarea class="prompt-editor" id="promptEditor" spellcheck="true">${escapeHtml(result.prompt)}</textarea>
      <div class="execution-toolbar">
        <button class="execution-button primary" id="generateFromPrompt">Generate from Prompt</button>
        <button class="execution-button" id="copyPrompt">Copy Prompt</button>
        <button class="execution-button quiet" id="closeExecution">Close</button>
      </div>
    </div>
  `);

  document.getElementById('generateFromPrompt')?.addEventListener('click', event => {
    const prompt = document.getElementById('promptEditor').value.trim();
    generateAsset(result.asset_type, event.currentTarget, prompt);
  });
  document.getElementById('copyPrompt')?.addEventListener('click', event => {
    copyText(document.getElementById('promptEditor').value, event.currentTarget);
  });
  document.getElementById('closeExecution')?.addEventListener('click', closeWorkspace);
}

function closeWorkspace() {
  const workspace = document.getElementById('executionWorkspace');
  if (!workspace) return;
  workspace.hidden = true;
  workspace.innerHTML = '';
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    const original = button.textContent;
    button.textContent = 'Copied';
    window.setTimeout(() => { button.textContent = original; }, 1400);
  } catch (_) {
    button.textContent = 'Copy failed';
  }
}

function openOpportunity(id) {
  activateView('opportunities');
  window.setTimeout(() => selectOpportunity(id), 50);
}

function leadRows(items) {
  return `
    <div class="lead-table-row header">
      <span>LEAD</span><span>STAGE</span><span>SOURCE</span><span>SCORE</span><span>STATUS</span><span>RECOMMENDED ACTION</span>
    </div>
    ${items.map(lead => `
      <div class="lead-table-row">
        <strong>${escapeHtml(lead.name)}</strong>
        <span>${escapeHtml(lead.stage)}</span>
        <span>${escapeHtml(lead.source)}</span>
        <strong>${escapeHtml(lead.score)}</strong>
        <span class="tag ${String(lead.temperature).toLowerCase()}">${escapeHtml(lead.temperature)}</span>
        <span class="action">${escapeHtml(lead.recommendedAction)}</span>
      </div>
    `).join('')}
  `;
}

function renderLeads(items) {
  state.leads = items;
  document.getElementById('allLeads').innerHTML = items.length
    ? leadRows(items)
    : '<div class="empty-state">No lead activity is available. Connect Follow Up Boss or use the demonstration data.</div>';
}

async function boot() {
  try {
    const [dashboard, opportunities, leads] = await Promise.all([
      request('/api/dashboard'),
      request('/api/opportunities'),
      request('/api/demo/leads'),
    ]);

    state.opportunities = opportunities.items || [];
    renderDashboard(dashboard);
    renderOpportunityPreview(state.opportunities);
    renderTodayActions(state.opportunities);
    renderFilters(state.opportunities);
    renderOpportunityList(state.opportunities);
    renderLeads(leads.items || []);
    if (state.opportunities.length) selectOpportunity(state.opportunities[0].opportunity_id);
  } catch (error) {
    document.getElementById('systemMode').textContent = 'Connection unavailable';
    document.getElementById('opportunityPreview').innerHTML = '<div class="empty-state">MoodyAI could not load the current opportunity report.</div>';
    document.getElementById('opportunityList').innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function addMessage(role, text) {
  const wrap = document.getElementById('chatWindow');
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = `
    <span class="message-icon">${role === 'user' ? 'Y' : 'M'}</span>
    <div><strong>${role === 'user' ? 'You' : 'MoodyAI'}</strong><p>${escapeHtml(text)}</p></div>
  `;
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
  return div;
}

document.querySelectorAll('.nav-item').forEach(button => {
  button.addEventListener('click', () => activateView(button.dataset.view));
});

document.querySelectorAll('[data-view-button]').forEach(button => {
  button.addEventListener('click', event => {
    event.preventDefault();
    activateView(button.dataset.viewButton);
  });
});

document.querySelectorAll('[data-open-advisor]').forEach(button => {
  button.addEventListener('click', () => {
    activateView('advisor');
    window.setTimeout(() => document.getElementById('advisorInput').focus(), 250);
  });
});

document.getElementById('mobileMenu').addEventListener('click', () => {
  document.querySelector('.sidebar').classList.toggle('open');
});

document.querySelectorAll('.prompt-list button').forEach(button => {
  button.addEventListener('click', () => {
    document.getElementById('advisorInput').value = button.textContent;
    document.getElementById('advisorInput').focus();
  });
});

document.getElementById('advisorForm').addEventListener('submit', async event => {
  event.preventDefault();
  const input = document.getElementById('advisorInput');
  const question = input.value.trim();
  if (!question) return;

  addMessage('user', question);
  input.value = '';
  const pending = addMessage('assistant', 'Reviewing current opportunities…');

  try {
    const result = await request('/api/advisor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    pending.querySelector('p').textContent = result.answer;
    document.getElementById('advisorMode').textContent = result.mode === 'live'
      ? 'Answer generated with live OpenAI intelligence.'
      : 'Answer generated using demonstration logic.';
  } catch (error) {
    pending.querySelector('p').textContent = `I could not complete that analysis: ${error.message}`;
  }
});

boot();
