function formatPrice(val) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  return Number(val).toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

document.addEventListener('DOMContentLoaded', async () => {
  const state = {
    stage: 'home',
    questions: [],
    currentStep: 0,
    answers: {},
    activeProject: null,
    recommendations: [],
    catalog: [],
    starProjects: [],
    selectedStarProject: null,
    starsLoaded: false,
    activeBom: null,
    completedProjects: [],
    recommendationResponse: null,
    optimizerOpen: false,
    optimizerRole: null,
    optimizerCandidate: null,
    optimizerEvaluation: null,
    optimizerNotice: '',
    optimizerLoadId: 0,
    wiringData: null
  };
  const stageHistory = [];

  // ── 1. Init & Sync State ──
  try {
    const s = await api.getState();
    state.currentStep = s.survey_step || 0;
    state.answers = s.survey_answers || {};
  } catch (err) {
    console.warn('Could not restore state from server:', err);
  }

  // Load Survey Questions & Catalog
  try {
    state.questions = await api.getQuestions();
    const cat = await api.getCatalog();
    state.catalog = cat.options || [];
    populateCatalogDropdown(state.catalog);
  } catch (err) {
    console.error('Initialization error:', err);
  }

  // Set initial view
  switchStage(state.stage);

  // ── Navigation ──
  document.querySelectorAll('[data-go]').forEach(button => {
    button.addEventListener('click', () => switchStage(button.dataset.go));
  });
  document.getElementById('btn-universal-back')?.addEventListener('click', goBack);
  document.getElementById('btn-back-to-questions')?.addEventListener('click', goBack);
  document.getElementById('btn-back-from-competition')?.addEventListener('click', goBack);
  document.getElementById('btn-skip-discovery')?.addEventListener('click', () => switchStage('bom'));

  function switchStage(stageName, { recordHistory = true } = {}) {
    if (stageName === 'pick') stageName = 'discovery';
    const validStages = ['home', 'discovery', 'results', 'competition', 'stars', 'bom'];
    if (!validStages.includes(stageName)) {
      console.error(`Unknown FORGE view: ${stageName}`);
      return;
    }
    if (recordHistory && stageName !== state.stage) stageHistory.push(state.stage);
    state.stage = stageName;
    document.getElementById('btn-universal-back').hidden = stageName === 'home';
    document.querySelectorAll('#app-viewport > .view-panel').forEach(view => {
      view.style.display = 'none';
    });
    document.getElementById(`view-${stageName}`).style.display = 'block';

    if (stageName === 'discovery') renderSurveyStep(state.currentStep);
    if (stageName === 'competition') loadCompetitionEvents();
    if (stageName === 'stars') loadStarProjects();
    if (stageName === 'bom' && !state.activeBom) loadInitialBom();
  }

  function goBack() {
    const previousStage = stageHistory.pop() || 'home';
    switchStage(previousStage, { recordHistory: false });
  }

  document.getElementById('star-project-sort')?.addEventListener('change', renderStarProjects);

  async function loadStarProjects() {
    if (state.starsLoaded) return renderStarProjects();
    const count = document.getElementById('star-project-count');
    count.textContent = 'Loading curated builds…';
    try {
      const response = await api.getStarProjects();
      state.starProjects = response.projects || [];
      state.starsLoaded = true;
      renderStarProjects();
    } catch (err) {
      count.textContent = `Could not load star projects: ${err.message}`;
    }
  }

  function renderStarProjects() {
    const grid = document.getElementById('star-project-grid');
    const count = document.getElementById('star-project-count');
    if (!grid || !count) return;
    const projects = [...state.starProjects];
    const sortValue = document.getElementById('star-project-sort').value;
    const [sortField, sortDirection] = sortValue.split('_');
    if (sortField !== 'default') {
      const field = sortField === 'hours' ? 'build_hours' : 'cost_inr';
      const direction = sortDirection === 'desc' ? -1 : 1;
      projects.sort((left, right) => {
        const leftValue = left[field];
        const rightValue = right[field];
        if (leftValue == null && rightValue != null) return 1;
        if (rightValue == null && leftValue != null) return -1;
        if (leftValue != null && rightValue != null && leftValue !== rightValue) {
          return (leftValue - rightValue) * direction;
        }
        return left.name.localeCompare(right.name);
      });
    }
    grid.replaceChildren();
    count.textContent = `${projects.length} curated projects`;

    projects.forEach(project => {
      const card = document.createElement('article');
      card.className = 'card star-project-card';
      const heading = document.createElement('div');
      heading.className = 'star-project-heading';
      const title = document.createElement('h2');
      title.textContent = project.name;
      const tier = document.createElement('span');
      tier.className = 'star-project-tier';
      tier.textContent = '✦ STAR';
      heading.append(title, tier);

      const domain = document.createElement('p');
      domain.className = 'star-project-domain';
      domain.textContent = project.domain.replaceAll('_', ' ');
      const description = document.createElement('p');
      description.className = 'text-secondary star-project-description';
      description.textContent = project.description;
      const metrics = document.createElement('div');
      metrics.className = 'star-project-metrics';
      [
        `Difficulty ${project.difficulty}/5`,
        `${project.build_hours} build hours`,
        project.cost_inr == null
          ? 'Price estimate withheld pending verification'
          : `Rough estimate: ₹${formatPrice(project.cost_inr)} · not a quote`
      ].forEach(value => {
        const metric = document.createElement('span');
        metric.textContent = value;
        metrics.appendChild(metric);
      });

      const details = document.createElement('details');
      details.className = 'star-project-details';
      const summary = document.createElement('summary');
      summary.textContent = 'Skills, tools & build notes';
      const detailList = document.createElement('dl');
      [
        ['Skills', project.skills],
        ['Prerequisites', project.prerequisites],
        ['Tools', project.tools],
        ['Safety', project.safety],
        ['Parts availability', [`${project.parts_availability}/5`]]
      ].forEach(([label, values]) => {
        if (!values?.length) return;
        const term = document.createElement('dt');
        term.textContent = label;
        const definition = document.createElement('dd');
        definition.textContent = values.join(', ').replaceAll('_', ' ');
        detailList.append(term, definition);
      });
      details.append(summary, detailList);
      const selectButton = document.createElement('button');
      selectButton.className = 'btn star-project-select';
      selectButton.type = 'button';
      selectButton.textContent = state.selectedStarProject?.key === project.key
        ? 'Selected'
        : 'Select project';
      selectButton.setAttribute('aria-pressed', String(state.selectedStarProject?.key === project.key));
      selectButton.addEventListener('click', () => {
        state.selectedStarProject = project;
        renderStarProjects();
      });
      card.classList.toggle('star-project-card-selected', state.selectedStarProject?.key === project.key);
      card.append(heading, domain, description, metrics, details, selectButton);
      grid.appendChild(card);
    });
    renderSelectedStarProject();
  }

  function renderSelectedStarProject() {
    const container = document.getElementById('star-project-selection');
    const project = state.selectedStarProject;
    if (!container) return;
    container.hidden = !project;
    if (!project) {
      container.replaceChildren();
      return;
    }

    const title = document.createElement('h3');
    title.textContent = `Selected project: ${project.name}`;
    const description = document.createElement('p');
    description.className = 'text-secondary';
    description.textContent = project.description;
    const action = document.createElement('button');
    action.className = 'btn primary';
    action.type = 'button';
    if (project.bom_supported) {
      action.textContent = 'Build this project';
      action.addEventListener('click', async () => {
        action.disabled = true;
        try {
          const bom = await api.generateBom({
            project: project.key,
            budget: project.cost_inr ?? 3500
          });
          renderBomView(bom);
          switchStage('bom');
        } catch (err) {
          action.disabled = false;
          document.getElementById('star-project-selection-status').textContent =
            `Could not open this build: ${err.message}`;
        }
      });
    } else {
      action.textContent = 'BOM not available yet';
      action.disabled = true;
      action.title = 'This curated project has no catalog bill of materials yet.';
    }

    const status = document.createElement('p');
    status.id = 'star-project-selection-status';
    status.className = 'caption';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.textContent = project.bom_supported
      ? 'This project has a catalog BOM ready to open.'
      : 'Project selected. A catalog BOM is not available for this build yet.';
    container.replaceChildren(title, description, action, status);
  }

  document.getElementById('btn-toggle-optimizer')?.addEventListener('click', async () => {
    state.optimizerOpen = !state.optimizerOpen;
    const content = document.getElementById('optimizer-content');
    const button = document.getElementById('btn-toggle-optimizer');
    content.hidden = !state.optimizerOpen;
    button.setAttribute('aria-expanded', String(state.optimizerOpen));
    button.textContent = state.optimizerOpen ? 'Close optimizer' : 'Open optimizer';
    if (state.optimizerOpen) {
      renderOptimizerRoles();
      await loadOptimizerCandidates();
    }
  });

  document.getElementById('optimizer-role-select')?.addEventListener('change', async event => {
    state.optimizerRole = event.target.value;
    state.optimizerEvaluation = null;
    state.optimizerNotice = '';
    document.getElementById('optimizer-result').hidden = true;
    document.getElementById('optimizer-actions').hidden = true;
    await loadOptimizerCandidates();
  });
  document.getElementById('optimizer-part-select')?.addEventListener('change', event => {
    state.optimizerCandidate = event.target.value;
    state.optimizerEvaluation = null;
    state.optimizerNotice = '';
    document.getElementById('optimizer-result').hidden = true;
    document.getElementById('optimizer-actions').hidden = true;
  });

  document.getElementById('btn-evaluate-swap')?.addEventListener('click', evaluateOptimizerSwap);
  document.getElementById('btn-keep-swap')?.addEventListener('click', async () => {
    if (!state.optimizerRole || !state.optimizerCandidate || !state.optimizerEvaluation?.summary?.ready) return;
    const button = document.getElementById('btn-keep-swap');
    button.disabled = true;
    try {
      await api.applySwap(state.optimizerRole, state.optimizerCandidate);
      state.optimizerNotice = 'Replacement applied. The BOM, bill, wiring, and compatibility data now use the updated build.';
      renderBomView(await api.getBom());
    } catch (err) {
      state.optimizerNotice = '';
      document.getElementById('optimizer-message').textContent = `Could not apply replacement: ${err.message}`;
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById('btn-reset-swaps')?.addEventListener('click', async () => {
    const button = document.getElementById('btn-reset-swaps');
    button.disabled = true;
    try {
      await api.resetSwaps();
      state.optimizerNotice = 'All optimizer replacements were undone.';
      renderBomView(await api.getBom());
    } catch (err) {
      state.optimizerNotice = '';
      document.getElementById('optimizer-message').textContent = `Could not undo replacements: ${err.message}`;
    } finally {
      button.disabled = false;
    }
  });

  function renderOptimizerRoles() {
    const selector = document.getElementById('optimizer-role-select');
    const parts = Object.entries(state.activeBom?.parts || {}).filter(([, part]) => part && !part.none);
    selector.replaceChildren();
    parts.forEach(([key, part]) => {
      const option = document.createElement('option');
      option.value = key;
      option.textContent = `${part.role || key}: ${part.name}`;
      selector.appendChild(option);
    });
    if (!parts.some(([key]) => key === state.optimizerRole)) {
      state.optimizerRole = parts[0]?.[0] || null;
    }
    selector.value = state.optimizerRole || '';
    selector.disabled = parts.length === 0;
    if (!parts.length) {
      document.getElementById('optimizer-message').textContent = 'This BOM has no replaceable components.';
    }
  }

  async function loadOptimizerCandidates() {
    const selector = document.getElementById('optimizer-part-select');
    const message = document.getElementById('optimizer-message');
    const evaluateButton = document.getElementById('btn-evaluate-swap');
    const role = state.optimizerRole;
    const current = state.activeBom?.parts?.[role];
    const requestId = ++state.optimizerLoadId;
    selector.replaceChildren();
    state.optimizerCandidate = null;
    evaluateButton.disabled = true;
    if (!role || !current) {
      message.textContent = 'Choose a component from the active BOM.';
      return;
    }
    message.textContent = state.optimizerNotice || 'Loading replacement options…';
    try {
      const candidates = await api.getOptimizerCandidates(role);
      if (requestId !== state.optimizerLoadId) return;
      candidates.filter(candidate => candidate.id !== current.id).forEach(candidate => {
        const option = document.createElement('option');
        option.value = candidate.id;
        option.textContent = `${candidate.name}${candidate.price == null ? ' · price unknown' : ` · ₹${formatPrice(candidate.price)}`}`;
        selector.appendChild(option);
      });
      if (!selector.options.length) {
        message.textContent = 'No alternative components are available for this role yet.';
        return;
      }
      state.optimizerCandidate = selector.value;
      evaluateButton.disabled = false;
      message.textContent = state.optimizerNotice || 'Select an alternative and compare it with the current configuration.';
    } catch (err) {
      if (requestId === state.optimizerLoadId) message.textContent = `Could not load replacements: ${err.message}`;
    }
  }

  async function evaluateOptimizerSwap() {
    if (!state.optimizerRole || !state.optimizerCandidate) return;
    const button = document.getElementById('btn-evaluate-swap');
    button.disabled = true;
    state.optimizerNotice = '';
    document.getElementById('optimizer-message').textContent = 'Calculating component and system impact…';
    try {
      state.optimizerEvaluation = await api.evaluateSwap(state.optimizerRole, state.optimizerCandidate);
      renderOptimizerEvaluation(state.optimizerEvaluation);
    } catch (err) {
      document.getElementById('optimizer-message').textContent = `Could not compare this replacement: ${err.message}`;
      document.getElementById('optimizer-result').hidden = true;
      document.getElementById('optimizer-actions').hidden = true;
    } finally {
      button.disabled = false;
    }
  }

  function renderOptimizerEvaluation(payload) {
    const result = document.getElementById('optimizer-result');
    const actions = document.getElementById('optimizer-actions');
    const evaluation = payload.evaluation || {};
    const summary = payload.summary || {};
    result.replaceChildren();

    const status = document.createElement('div');
    status.className = `alert ${summary.ready ? 'success' : 'warn'}`;
    status.textContent = summary.ready
      ? `Proposed build has no failed compatibility rules (${summary.warn || 0} warnings, ${summary.unknown || 0} unknown).`
      : `Proposed build has ${summary.fail || 0} failed compatibility rule(s). Review the results before applying.`;
    result.appendChild(status);

    if (evaluation.chips?.length) {
      const chips = document.createElement('div');
      chips.className = 'optimizer-chips';
      evaluation.chips.forEach(item => {
        const chip = document.createElement('span');
        chip.className = `optimizer-chip ${item.tone || ''}`;
        chip.textContent = item.text;
        chips.appendChild(chip);
      });
      result.appendChild(chips);
    }

    const table = document.createElement('table');
    table.className = 'fg-t optimizer-results-table';
    table.innerHTML = '<thead><tr><th>Impact</th><th>Current</th><th>Proposed</th><th>Change</th><th>Status</th></tr></thead>';
    const tbody = document.createElement('tbody');
    (evaluation.rows || []).forEach(row => {
      const tr = document.createElement('tr');
      const changed = row.diff == null ? '—' : `${row.diff > 0 ? '+' : ''}${Number(row.diff).toLocaleString(undefined, { maximumFractionDigits: 2 })}${row.unit ? ` ${row.unit}` : ''}${row.pct == null ? '' : ` (${row.pct > 0 ? '+' : ''}${Number(row.pct).toFixed(1)}%)`}`;
      const formatValue = value => {
        if (value == null) return '—';
        if (row.key === 'cost' && typeof value === 'number') return `₹${formatPrice(value)}`;
        return typeof value === 'number' ? `${formatPrice(value)}${row.unit ? ` ${row.unit}` : ''}` : String(value);
      };
      [row.metric, formatValue(row.original), formatValue(row.proposed), changed, row.status || '—'].forEach(value => {
        const td = document.createElement('td');
        td.textContent = value;
        tr.appendChild(td);
      });
      tr.title = row.reason || '';
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    result.appendChild(table);

    if (evaluation.compat_proposed?.length) {
      const rules = document.createElement('div');
      rules.className = 'optimizer-rule-list';
      evaluation.compat_proposed.forEach(rule => {
        const item = document.createElement('p');
        const badge = document.createElement('span');
        badge.className = `b ${rule.status}`;
        badge.textContent = rule.status;
        item.append(badge, ' ');
        const title = document.createElement('b');
        title.textContent = rule.title;
        item.append(title, ` · ${rule.explanation || ''}`);
        if (rule.action) item.append(` Suggested action: ${rule.action}`);
        rules.appendChild(item);
      });
      result.appendChild(rules);
    }

    result.hidden = false;
    actions.hidden = false;
    document.getElementById('btn-keep-swap').disabled = !summary.ready;
    document.getElementById('optimizer-message').textContent = summary.ready
      ? 'Numbers are calculated from FORGE’s catalog and available component profiles; unknown values are shown as unavailable.'
      : 'This replacement is not ready to apply because at least one compatibility rule fails.';
  }

  // ── 2. Survey Engine ──
  function renderSurveyStep(step) {
    if (!state.questions || state.questions.length === 0) return;
    state.currentStep = Math.max(0, Math.min(step, state.questions.length - 1));
    const q = state.questions[state.currentStep];

    document.getElementById('survey-step-indicator').textContent = `QUESTION ${String(state.currentStep + 1).padStart(2, '0')} / ${String(state.questions.length).padStart(2, '0')}`;
    const pct = ((state.currentStep + 1) / state.questions.length) * 100;
    document.getElementById('survey-progress-bar').style.width = `${pct}%`;
    document.getElementById('survey-question-text').textContent = q.question;

    const container = document.getElementById('survey-input-container');
    container.innerHTML = '';

    const currentVal = state.answers[q.key] || (q.multi ? [] : '');

    // Options Pills
    if (q.options && q.options.length > 0) {
      const pGroup = document.createElement('div');
      pGroup.className = 'pills-group';
      q.options.forEach(opt => {
        const pBtn = document.createElement('div');
        const isSelected = q.multi ? (currentVal || []).includes(opt) : currentVal === opt;
        pBtn.className = `pill-opt ${isSelected ? 'selected' : ''}`;
        pBtn.textContent = opt;
        pBtn.addEventListener('click', () => {
          if (q.multi) {
            let list = Array.isArray(state.answers[q.key]) ? [...state.answers[q.key]] : [];
            if (list.includes(opt)) list = list.filter(x => x !== opt);
            else list.push(opt);
            state.answers[q.key] = list;
          } else {
            state.answers[q.key] = opt;
          }
          api.saveSurveyAnswers(state.answers, state.currentStep);
          renderSurveyStep(state.currentStep);
        });
        pGroup.appendChild(pBtn);
      });
      container.appendChild(pGroup);
    }

    // Specific text/number inputs
    if (q.key === 'career') {
      const inp = document.createElement('input');
      inp.type = 'text';
      inp.placeholder = 'Dream job, destination company, or target industry';
      inp.value = state.answers['dream_job'] || '';
      inp.addEventListener('change', () => {
        state.answers['dream_job'] = inp.value;
        api.saveSurveyAnswers(state.answers, state.currentStep);
      });
      container.appendChild(inp);
    } else if (q.key === 'budget') {
      const inp = document.createElement('input');
      inp.type = 'number';
      inp.placeholder = 'Maximum budget in ₹ (0 = not specified)';
      inp.value = state.answers['budget_inr'] || '';
      inp.addEventListener('change', () => {
        state.answers['budget_inr'] = parseInt(inp.value) || null;
        api.saveSurveyAnswers(state.answers, state.currentStep);
      });
      container.appendChild(inp);
    } else if (q.key === 'schedule') {
      const schedule = state.answers.schedule || {};
      const scheduleInputs = document.createElement('div');
      scheduleInputs.className = 'schedule-inputs';

      const hoursLabel = document.createElement('label');
      hoursLabel.textContent = 'Hours available each week';
      const hoursInput = document.createElement('input');
      hoursInput.type = 'number';
      hoursInput.min = '1';
      hoursInput.max = '80';
      hoursInput.step = '1';
      hoursInput.placeholder = 'e.g. 6';
      hoursInput.value = schedule.hours_per_week || '';
      hoursInput.addEventListener('change', () => {
        state.answers.schedule = {
          ...state.answers.schedule,
          hours_per_week: Number(hoursInput.value) || null
        };
        state.answers.hours_per_week = Number(hoursInput.value) || null;
        api.saveSurveyAnswers(state.answers, state.currentStep);
      });
      hoursLabel.appendChild(hoursInput);

      const deadlineLabel = document.createElement('label');
      deadlineLabel.textContent = 'Target completion';
      const deadlineSelect = document.createElement('select');
      [
        ['', 'No fixed deadline'],
        ['2', 'Within 2 weeks'],
        ['4', 'Within 1 month'],
        ['8', 'Within 2 months'],
        ['12', 'Within 3 months'],
        ['24', 'Within 6 months']
      ].forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        deadlineSelect.appendChild(option);
      });
      deadlineSelect.value = schedule.deadline_weeks || '';
      deadlineSelect.addEventListener('change', () => {
        state.answers.schedule = {
          ...state.answers.schedule,
          deadline_weeks: Number(deadlineSelect.value) || null
        };
        state.answers.deadline_weeks = Number(deadlineSelect.value) || null;
        api.saveSurveyAnswers(state.answers, state.currentStep);
      });
      deadlineLabel.appendChild(deadlineSelect);
      scheduleInputs.append(hoursLabel, deadlineLabel);
      container.appendChild(scheduleInputs);
    }

    // Buttons
    document.getElementById('survey-prev-btn').disabled = (state.currentStep === 0);
    const count = Object.values(state.answers).filter(Boolean).length;
    document.getElementById('survey-answered-count').textContent = `${count} of ${state.questions.length} questions answered`;
  }

  document.getElementById('survey-prev-btn')?.addEventListener('click', () => {
    if (state.currentStep > 0) renderSurveyStep(state.currentStep - 1);
  });

  document.getElementById('survey-next-btn')?.addEventListener('click', () => {
    if (state.currentStep < state.questions.length - 1) {
      renderSurveyStep(state.currentStep + 1);
    } else {
      triggerRecommendationRanking();
    }
  });

  document.getElementById('btn-get-recommendations')?.addEventListener('click', triggerRecommendationRanking);

  const completedProjectSearch = document.getElementById('completed-project-search');
  const completedProjectToggle = document.getElementById('has-completed-projects');
  const completedProjectControls = document.getElementById('completed-project-controls');
  completedProjectToggle?.addEventListener('change', () => {
    completedProjectControls.hidden = !completedProjectToggle.checked;
    if (!completedProjectToggle.checked) {
      document.getElementById('completed-project-search-results').innerHTML = '';
    }
  });
  let projectSearchTimer;
  completedProjectSearch?.addEventListener('input', () => {
    clearTimeout(projectSearchTimer);
    projectSearchTimer = setTimeout(async () => {
      const query = completedProjectSearch.value.trim();
      const results = document.getElementById('completed-project-search-results');
      if (query.length < 2) {
        results.innerHTML = '';
        return;
      }
      try {
        const response = await api.searchProjects(query);
        const selectedIds = new Set(state.completedProjects.map(project => project.key));
        results.innerHTML = response.projects
          .filter(project => !selectedIds.has(project.key))
          .map(project => `
            <button class="project-search-option" type="button" role="option"
              data-project-key="${escapeHtml(project.key)}"
              data-project-label="${escapeHtml(project.label)}">
              ${escapeHtml(project.label)} <span class="caption">${escapeHtml(project.domain)}</span>
            </button>
          `).join('');
        results.querySelectorAll('[data-project-key]').forEach(button => {
          button.addEventListener('click', () => {
            state.completedProjects.push({
              key: button.dataset.projectKey,
              label: button.dataset.projectLabel
            });
            completedProjectSearch.value = '';
            results.innerHTML = '';
            renderCompletedProjectSelection();
          });
        });
      } catch (err) {
        results.innerHTML = `<div class="caption" style="padding:9px;">${escapeHtml(err.message)}</div>`;
      }
    }, 180);
  });

  function renderCompletedProjectSelection() {
    const container = document.getElementById('completed-project-selection');
    container.innerHTML = state.completedProjects.map(project => `
      <span class="completed-project-chip">
        ${escapeHtml(project.label)}
        <button type="button" data-remove-project="${escapeHtml(project.key)}" aria-label="Remove ${escapeHtml(project.label)}">×</button>
      </span>
    `).join('');
    container.querySelectorAll('[data-remove-project]').forEach(button => {
      button.addEventListener('click', () => {
        state.completedProjects = state.completedProjects.filter(
          project => project.key !== button.dataset.removeProject
        );
        renderCompletedProjectSelection();
      });
    });
  }

  async function triggerRecommendationRanking() {
    try {
      const status = document.getElementById('recommendation-status');
      const surveyStatus = document.getElementById('survey-rank-status');
      surveyStatus.textContent = '';
      const schedule = state.answers.schedule || {};
      const hours = Number(schedule.hours_per_week || state.answers.hours_per_week);
      const deadline = Number(schedule.deadline_weeks || state.answers.deadline_weeks);
      const res = await api.rankProjects(state.answers, 5, {
        hours_per_week: hours || null,
        deadline_weeks: deadline || null,
        completed_project_ids: completedProjectToggle?.checked
          ? state.completedProjects.map(project => project.key)
          : []
      });
      state.recommendationResponse = res;
      if (res.needs_more_info) {
        surveyStatus.textContent = `A little more information is needed: ${(res.missing || []).join(', ')}.`;
        return;
      }
      status.hidden = true;
      state.recommendations = res.results || [];
      renderRecommendations(state.recommendations);
      switchStage('results');
    } catch (err) {
      alert('Ranking failed: ' + err.message);
    }
  }

  // ── 3. Recommendations & Detail Inspector ──
  function renderRecommendations(items) {
    const grid = document.getElementById('recommendations-grid');
    grid.innerHTML = '';
    document.getElementById('recommendation-status').hidden = true;
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'card';
      card.style.cursor = 'pointer';
      card.innerHTML = `
        <span class="tier-badge">${escapeHtml(item.tier || 'Baseline')}</span>
        <div style="font-size:1.05rem;font-weight:700;margin:8px 0 4px;">${escapeHtml(item.label)}</div>
        <p class="caption">${escapeHtml(item.desc)}</p>
        <div style="margin:10px 0;font-size:0.8rem;color:var(--text-secondary);">
          ${escapeHtml(item.domain)} · ${item.build_hours || '—'} hrs · ₹${formatPrice(item.cost_inr)}
        </div>
        <button class="btn primary" type="button" data-choose-project style="width:100%;margin-top:6px;">View explanation</button>
        <div class="recommendation-feedback" aria-label="Recommendation feedback">
          <button class="btn ghost" type="button" data-feedback="built">Built</button>
          <button class="btn ghost" type="button" data-feedback="too_hard">Too hard</button>
          <button class="btn ghost" type="button" data-feedback="too_easy">Too easy</button>
          <button class="btn ghost" type="button" data-feedback="not_interested">Not interested</button>
        </div>
        <span class="caption" data-feedback-status role="status"></span>
      `;
      card.addEventListener('click', () => inspectProjectDetail(item));
      card.querySelector('[data-choose-project]').addEventListener('click', event => {
        event.stopPropagation();
        inspectProjectDetail(item);
      });
      card.querySelectorAll('[data-feedback]').forEach(button => {
        button.addEventListener('click', async event => {
          event.stopPropagation();
          const status = card.querySelector('[data-feedback-status]');
          button.disabled = true;
          try {
            const level = Number(state.answers.skill_level || state.answers.level);
            await api.sendRecommendationFeedback(item.key, button.dataset.feedback, {
              level: Number.isInteger(level) && level >= 1 && level <= 5 ? level : null,
              role: String(state.answers.career || 'undecided').slice(0, 40)
            });
            status.textContent = 'Feedback recorded';
          } catch (err) {
            status.textContent = `Could not record feedback: ${err.message}`;
            button.disabled = false;
          }
        });
      });
      grid.appendChild(card);
    });

    renderStarGoal(state.recommendationResponse?.goal);
    if (items.length > 0) inspectProjectDetail(items[0]);
  }

  function renderStarGoal(goal) {
    const container = document.getElementById('star-goal-card');
    if (!goal) {
      container.innerHTML = '<p class="caption">A separate Star Project goal will appear when a profile has enough information.</p>';
      return;
    }
    const steps = goal.step_labels || goal.steps || [];
    const priceLabel = goal.price_status === 'pending_verification'
      ? 'Price pending verification'
      : 'Rough estimate; not a quote';
    container.innerHTML = `
      <p class="eyebrow">LONG-TERM STAR PROJECT GOAL</p>
      <h3>${escapeHtml(goal.label)}</h3>
      <p class="text-secondary">${escapeHtml(goal.desc)}</p>
      <p class="caption">Estimated cost: ₹${formatPrice(goal.cost_inr)} · ${priceLabel}</p>
      <p class="caption">${goal.eligible ? 'Current prerequisite path is reachable.' : 'Build the foundations below before attempting this goal.'}</p>
      <h4>Prerequisite path</h4>
      ${steps.length
        ? `<ol class="goal-step-list">${steps.map(step => `<li>${escapeHtml(step)}</li>`).join('')}</ol>`
        : '<p class="caption">No remaining prerequisite steps.</p>'}
    `;
  }

  function inspectProjectDetail(item) {
    state.activeProject = item.key;
    const inspector = document.getElementById('project-detail-inspector');
    inspector.style.display = 'block';

    document.getElementById('detail-project-title').textContent = item.tier
      ? `${item.label} · ${item.tier.replaceAll('_', ' ')}`
      : `${item.label} · baseline recommendation`;
    document.getElementById('detail-project-desc').textContent = item.desc;
    document.getElementById('detail-meta-list').innerHTML = `
      <div><b>Domain:</b> ${escapeHtml(item.domain)}</div>
      <div><b>Estimated build time:</b> ${item.build_hours || '—'} hours</div>
      <div><b>Estimated cost:</b> ₹${formatPrice(item.cost_inr)} <span class="caption">${item.price_status ? `(${escapeHtml(item.price_status.replaceAll('_', ' '))})` : '(rough estimate; not a quote)'}</span></div>
      <div><b>Parts availability in India:</b> ${item.parts_availability_india ?? '—'}/5</div>
      <div><b>Tools required:</b> ${escapeHtml((item.tools_required || []).join(', ') || 'Standard hand tools')}</div>
      <div><b>Required skills:</b> ${escapeHtml((item.required_skills || []).join(', ') || 'See skills to practise')}</div>
    `;

    document.getElementById('detail-reasons').innerHTML = (item.reasons || [])
      .map(reason => `<span class="recommendation-chip">${escapeHtml(reason)}</span>`).join('')
      || '<span class="caption">Reason details are available for the v2 scorer.</span>';
    document.getElementById('detail-learn-skills').innerHTML = (item.learn_skills || [])
      .map(skill => `<span class="recommendation-chip">${escapeHtml(skill)}</span>`).join('')
      || '<span class="caption">No specific new skill tags are listed.</span>';
    document.getElementById('detail-unlocks').innerHTML = (item.unlocks || [])
      .map(key => `<span class="recommendation-chip">${escapeHtml(key.replaceAll('_', ' '))}</span>`).join('')
      || '<span class="caption">No specific next projects are listed.</span>';

    const factorRows = [...(item.fit_breakdown || [])]
      .sort((left, right) => (right.fit_score ?? 0) - (left.fit_score ?? 0));
    const factorTableBody = document.querySelector('#detail-fit-table tbody');
    factorTableBody.replaceChildren();
    factorRows.forEach((row, index) => {
      const tableRow = document.createElement('tr');
      [String(index + 1), row.factor, row.fit].forEach(value => {
        const cell = document.createElement('td');
        cell.textContent = value;
        tableRow.appendChild(cell);
      });
      factorTableBody.appendChild(tableRow);
    });
    document.getElementById('detail-radar-chart').innerHTML = item.chart_svg || '';
    const flagLabels = {
      cost_unverified: 'Cost has not been verified',
      slightly_over_budget: 'Slightly above the stated budget',
      low_information: 'Limited preference information',
      build_first: 'A prerequisite should be built first'
    };
    document.getElementById('detail-flags').textContent = (item.flags || [])
      .map(flag => flagLabels[flag] || flag.replaceAll('_', ' ')).join(' · ');

    // Action button
    const btn = document.getElementById('btn-build-bom-for-pick');
    btn.disabled = !item.bom_supported;
    btn.title = item.bom_supported ? '' : 'BOM generation is not available for this recommendation yet.';
    btn.textContent = item.bom_supported ? '⚡ Build the BOM for this project' : 'BOM not available for this project';
    btn.onclick = async () => {
      if (!item.bom_supported) return;
      try {
        await api.generateBom({ project: item.key, budget: item.cost_inr || 3500 });
        switchStage('bom');
      } catch (err) {
        alert('Could not open BOM: ' + err.message);
      }
    };
  }

  // Free-text Idea Match
  document.getElementById('btn-submit-idea')?.addEventListener('click', async () => {
    const input = document.getElementById('input-idea-match');
    const txt = (input.value || '').trim();
    if (!txt) return;
    try {
      const res = await api.matchIdea(txt);
      const out = document.getElementById('idea-match-result');
      if (res.supported && res.project) {
        out.innerHTML = `<div class="alert success">Closest supported project: <b>${res.label}</b>. <button class="btn primary" id="btn-use-matched-idea" style="margin-left:10px;">Build BOM</button></div>`;
        document.getElementById('btn-use-matched-idea')?.addEventListener('click', async () => {
          await api.generateBom({ project: res.project });
          switchStage('bom');
        });
      } else {
        out.innerHTML = `<div class="alert warn">${res.reason}</div>`;
      }
    } catch (err) {
      alert('Idea match failed: ' + err.message);
    }
  });

  // ── 4. Competition Shortlist ──
  async function loadCompetitionEvents() {
    try {
      const evs = await api.getCompetitionEvents();
      const sel = document.getElementById('select-competition-event');
      sel.innerHTML = '';
      evs.forEach(e => {
        const opt = document.createElement('option');
        opt.value = e.name;
        opt.textContent = `${e.name} · ${e.mentions} project mentions`;
        sel.appendChild(opt);
      });
      sel.onchange = () => loadEventProjects(sel.value);
      if (evs.length > 0) loadEventProjects(evs[0].name);
    } catch (err) {
      console.error('Failed to load competition events:', err);
    }
  }

  async function loadEventProjects(eventName) {
    try {
      const res = await api.getCompetitionProjects(eventName);
      const container = document.getElementById('competition-projects-container');
      container.innerHTML = '';
      (res.projects || []).forEach(p => {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:flex-start;">
            <h3>${p.label}</h3>
            <button class="btn primary btn-comp-plan" data-key="${p.key}">⚡ Plan &amp; Build BOM</button>
          </div>
          <p class="caption">${p.desc}</p>
          <div style="margin:10px 0;font-size:0.82rem;color:var(--text-secondary);">
            Estimated ${p.build_hours} hours · ₹${formatPrice(p.cost_inr)} · Availability ${p.parts_availability_india}/5
          </div>
          <div class="caption"><b>Constraints:</b> ${p.constraints || 'Standard competition constraints'}</div>
        `;
        card.querySelector('.btn-comp-plan').onclick = async () => {
          try {
            await api.generateBom({ project: p.key, budget: p.cost_inr || 3500 });
            switchStage('bom');
          } catch (err) {
            alert('Failed to generate competition BOM: ' + err.message);
          }
        };
        container.appendChild(card);
      });
    } catch (err) {
      console.error('Failed to load event projects:', err);
    }
  }

  // ── 5. Planning & BOM Studio ──
  function populateCatalogDropdown(options) {
    const sel = document.getElementById('select-catalog-project');
    if (!sel) return;
    sel.innerHTML = '';
    options.forEach(o => {
      const opt = document.createElement('option');
      opt.value = o.key;
      opt.textContent = o.label;
      sel.appendChild(opt);
    });
  }

  document.getElementById('btn-generate-catalog-bom')?.addEventListener('click', async () => {
    const sel = document.getElementById('select-catalog-project');
    const budget = parseInt(document.getElementById('bom-budget-input').value) || 3500;
    const bt = document.getElementById('bom-bluetooth-toggle').checked;
    try {
      const bom = await api.generateBom({ project: sel.value, budget, bluetooth: bt });
      renderBomView(bom);
    } catch (err) {
      alert('Error generating BOM: ' + err.message);
    }
  });

  document.getElementById('btn-plan-custom-build')?.addEventListener('click', async () => {
    const inp = document.getElementById('input-custom-build');
    const txt = (inp.value || '').trim();
    if (!txt) return;
    const budget = parseInt(document.getElementById('bom-budget-input').value) || 3500;
    const bt = document.getElementById('bom-bluetooth-toggle').checked;
    try {
      const bom = await api.generateBom({ custom_idea: txt, budget, bluetooth: bt });
      if (bom.status === 'suggest') {
        alert('Suggested similar catalog projects available.');
      } else {
        renderBomView(bom);
      }
    } catch (err) {
      alert('Planning custom build failed: ' + err.message);
    }
  });

  async function loadInitialBom() {
    try {
      const bom = await api.generateBom({ project: 'general:line_follower', budget: 3500 });
      renderBomView(bom);
    } catch (err) {
      console.warn('Initial BOM load:', err);
    }
  }

  function renderBomView(bom) {
    state.activeBom = bom;
    state.optimizerEvaluation = null;
    document.getElementById('bom-project-heading').textContent = `${bom.label} — Architecture & Planning`;
    const totCost = bom.bill?.grand_total ?? bom.bill?.parts_subtotal ?? 0;
    document.getElementById('metric-total-cost').textContent = `₹${formatPrice(totCost)}`;
    document.getElementById('metric-components-count').textContent = `${bom.parts_count || 0} parts`;
    document.getElementById('metric-live-priced').textContent = `${bom.bill?.live_priced_count || 0} / ${bom.parts_count || 0} live`;

    // Render Origin Banner
    const originMap = {
      rule: 'Rule-checked build: parts chosen by compatibility rules (no AI).',
      dataset: 'Component list read from the FORGE dataset. No Gemini call.',
      learned: 'Reused a plan Gemini made earlier for this idea. No new Gemini call.',
      gemini: 'Gemini planned this build.'
    };
    document.getElementById('bom-origin-banner').innerHTML = `<div class="alert success">${originMap[bom.origin] || 'Verified architecture.'}</div>`;

    renderComponentCards(bom.parts || {}, bom.bill?.lines || [], bom.parts_offers || {}, bom.choice || {}, bom.manual || {});
    renderOptimizerRoles();
    document.getElementById('optimizer-content').hidden = !state.optimizerOpen;
    document.getElementById('btn-toggle-optimizer').setAttribute('aria-expanded', String(state.optimizerOpen));
    document.getElementById('btn-toggle-optimizer').textContent = state.optimizerOpen ? 'Close optimizer' : 'Open optimizer';
    document.getElementById('optimizer-result').hidden = true;
    document.getElementById('optimizer-actions').hidden = true;
    if (state.optimizerOpen) loadOptimizerCandidates();
    renderChecks(bom.checks || []);
    renderBillTable(bom.bill);
    loadWiringStudio();
    loadDeliveryOptimizer();
  }

  function renderComponentCards(parts, lines, partsOffers = {}, choice = {}, manual = {}) {
    const container = document.getElementById('bom-components-container');
    container.innerHTML = '';
    const lineMap = {};
    lines.forEach(l => { lineMap[l.part_id] = l; });

    Object.entries(parts).forEach(([role, part]) => {
      if (part.none) return;
      const line = lineMap[part.id] || { qty: 1, unit: part.seed_price ?? null, source: 'estimate' };
      const statusLabel = line.source === 'live' ? 'LIVE PRICE' : (line.source === 'manual' ? 'YOUR PICK' : 'ESTIMATED');
      const badgeCls = line.source === 'live' ? 'PASS' : (line.source === 'manual' ? 'WARN' : 'UNKNOWN');
      const priceText = (line.unit !== null && line.unit !== undefined) ? `₹${formatPrice(line.unit * line.qty)}` : '—';
      const offerInfo = partsOffers[part.id] || { verified: [], unverified: [] };
      const chosenUrl = manual[part.id] ? null : (choice[part.id] || (offerInfo.verified[0]?.url));

      const card = document.createElement('div');
      card.className = 'component-card';

      let offersHtml = '';
      if (offerInfo.warning) {
        offersHtml += `<div class="alert warning" style="margin-bottom:8px;">${offerInfo.warning}</div>`;
      }

      if (offerInfo.verified && offerInfo.verified.length > 0) {
        offersHtml += `<div style="font-size:0.75rem;font-weight:700;color:var(--text-secondary);margin:8px 0 6px 0;letter-spacing:0.04em;">VERIFIED PRICES · LOWEST FIRST</div>`;
        offerInfo.verified.forEach(o => {
          const isSelected = (chosenUrl === o.url);
          offersHtml += `
            <div class="offer-row ${isSelected ? 'selected' : ''}">
              <div style="flex:1;">
                <div style="display:flex;align-items:center;gap:8px;">
                  <b>${o.vendor}</b>
                  <span class="caption">${(o.name || '').slice(0, 70)}</span>
                  ${o.suspect ? '<span class="b FAIL">CHECK SUSPECT</span>' : ''}
                </div>
                <div class="caption" style="margin-top:4px;">
                  ${o.quote ? `Evidence: “${o.quote.slice(0, 100)}” · ` : ''}
                  Checked ${o.checked_at || 'live'} · Method: ${o.method || 'page rules'}
                </div>
              </div>
              <div style="text-align:right;min-width:140px;">
                <div style="font-size:1.1rem;font-weight:700;color:var(--primary-orange);">₹${formatPrice(o.price)}</div>
                <div style="display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:6px;">
                  <a href="${o.url}" target="_blank" rel="noopener noreferrer" class="caption" style="color:var(--text-secondary);text-decoration:underline;">View product ↗</a>
                  ${isSelected
                    ? '<span class="b PASS">SELECTED</span>'
                    : `<button class="btn btn-sm btn-pick-offer" data-pid="${part.id}" data-url="${o.url}">Use this</button>`}
                </div>
              </div>
            </div>
          `;
        });
      }

      if (offerInfo.unverified && offerInfo.unverified.length > 0) {
        offersHtml += `
          <div style="font-size:0.75rem;font-weight:700;color:var(--text-secondary);margin:14px 0 6px 0;letter-spacing:0.04em;">PRICE NOT VERIFIED</div>
          <p class="caption">These pages were found, but no price could be confirmed from their text. You may choose one and type the price you saw:</p>
        `;
        offerInfo.unverified.forEach(uo => {
          const manualEntry = manual[part.id] || {};
          const isManual = (manualEntry.url === uo.url);
          offersHtml += `
            <div class="offer-row ${isManual ? 'selected' : ''}" style="margin-top:6px;">
              <div style="flex:1;">
                <div style="display:flex;align-items:center;gap:8px;">
                  <b>${uo.vendor}</b>
                  <span class="caption">${(uo.name || 'Listing name not verified').slice(0, 60)}</span>
                  <span class="b UNKNOWN">PRICE NOT VERIFIED</span>
                  ${isManual ? '<span class="b WARN">YOUR PICK</span>' : ''}
                </div>
                <div style="display:flex;align-items:center;gap:8px;margin-top:8px;">
                  <input type="number" class="manual-price-val" placeholder="Price seen (₹)" style="width:130px;padding:4px 8px;font-size:0.85rem;" value="${isManual ? (manualEntry.price || '') : ''}">
                  <button class="btn btn-sm btn-save-manual" data-pid="${part.id}" data-url="${uo.url}" data-name="${uo.name || ''}">Use this listing</button>
                  <a href="${uo.url}" target="_blank" rel="noopener noreferrer" class="caption" style="color:var(--text-secondary);text-decoration:underline;margin-left:8px;">View product ↗</a>
                </div>
              </div>
            </div>
          `;
        });
      }

      if (!offerInfo.verified?.length && !offerInfo.unverified?.length) {
        if (part.seed_price !== null && part.seed_price !== undefined) {
          offersHtml += `<p class="caption">No verified shop price found yet. Using team estimate of ₹${formatPrice(part.seed_price)} (not checked on any page).</p>`;
        } else {
          offersHtml += `<p class="caption">No verified shop price found yet. This part is not included in the total until a price is verified or entered.</p>`;
        }
        offersHtml += `<p class="caption" style="margin-top:6px;color:var(--primary-orange);">Click <b>⚡ Find live prices</b> above to scan vendors with TinyFish.</p>`;
      }

      card.innerHTML = `
        <div class="component-card-header">
          <div style="display:flex;align-items:center;gap:12px;">
            <span class="arrow-icon">▶</span>
            <b>${part.name}</b>
            <span class="caption" style="text-transform:uppercase;">${role} × ${line.qty}</span>
            <span class="b ${badgeCls}">${statusLabel}</span>
          </div>
          <div style="font-weight:700;">${priceText}</div>
        </div>
        <div class="component-card-body">
          <p class="caption">${part.note || part.why || 'Engineering component'}</p>
          <div class="offer-list" style="margin-top:10px;">
            ${offersHtml}
          </div>
        </div>
      `;

      card.querySelector('.component-card-header').onclick = () => {
        card.classList.toggle('open');
      };

      // Button handlers inside card
      card.querySelectorAll('.btn-pick-offer').forEach(btn => {
        btn.onclick = async (e) => {
          e.stopPropagation();
          const pid = btn.dataset.pid;
          const url = btn.dataset.url;
          await api.setChoice('pick', pid, url);
          const updatedBom = await api.getBom();
          renderBomView(updatedBom);
        };
      });

      card.querySelectorAll('.btn-save-manual').forEach(btn => {
        btn.onclick = async (e) => {
          e.stopPropagation();
          const pid = btn.dataset.pid;
          const url = btn.dataset.url;
          const name = btn.dataset.name;
          const parentRow = btn.closest('.offer-row');
          const input = parentRow.querySelector('.manual-price-val');
          const val = parseFloat(input?.value);
          if (isNaN(val) || val <= 0) {
            alert('Please enter a valid price in ₹');
            return;
          }
          await api.setChoice('manual', pid, url, val, name);
          const updatedBom = await api.getBom();
          renderBomView(updatedBom);
        };
      });

      container.appendChild(card);
    });
  }

  function renderChecks(checks) {
    const list = document.getElementById('bom-checks-list');
    list.innerHTML = '';
    if (checks.length === 0) {
      list.innerHTML = '<div class="caption">Architecture follows standard rule constraints.</div>';
      return;
    }
    checks.forEach(c => {
      const row = document.createElement('div');
      row.style.margin = '4px 0';
      row.innerHTML = `<span class="b ${c.status}">${c.status}</span> <span style="font-weight:600;margin-left:6px;">${c.title}</span> <span class="caption">${c.msg || ''}</span>`;
      list.appendChild(row);
    });
  }

  function renderBillTable(billData) {
    if (!billData) return;
    document.getElementById('bill-ref-label').textContent = `REF: ${billData.ref || 'FG-001'}`;
    document.getElementById('bill-meta-date').textContent = billData.date || new Date().toISOString().slice(0, 10);
    const tbody = document.querySelector('#bill-table-view tbody');
    tbody.innerHTML = '';

    (billData.lines || []).forEach(l => {
      const tr = document.createElement('tr');
      const unitText = (l.unit !== null && l.unit !== undefined) ? `₹${formatPrice(l.unit)}` : '—';
      const totText = (l.unit !== null && l.unit !== undefined) ? `₹${formatPrice(l.unit * l.qty)}` : (l.total !== null && l.total !== undefined ? `₹${formatPrice(l.total)}` : '—');
      tr.innerHTML = `
        <td><b>${l.name}</b></td>
        <td>${l.role}</td>
        <td>${l.qty}</td>
        <td>${unitText}</td>
        <td><b>${totText}</b></td>
      `;
      tbody.appendChild(tr);
    });

    const totalTr = document.createElement('tr');
    totalTr.className = 'fg-total-row';
    const grandTot = billData.grand_total ?? billData.total ?? billData.parts_subtotal ?? 0;
    totalTr.innerHTML = `
      <td colspan="4">GRAND TOTAL</td>
      <td>₹${formatPrice(grandTot)}</td>
    `;
    tbody.appendChild(totalTr);
  }

  // ── 6. Live Sourcing SSE Stream ──
  document.getElementById('btn-find-live-prices')?.addEventListener('click', () => {
    const box = document.getElementById('sourcing-log-box');
    box.style.display = 'block';
    box.textContent = 'Connecting to TinyFish live sourcing stream...\n';

    api.streamSourcing(
      (line) => {
        box.textContent += line + '\n';
        box.scrollTop = box.scrollHeight;
      },
      async () => {
        box.textContent += 'Done! Re-computing verified bill...\n';
        const updatedBom = await api.getBom();
        renderBomView(updatedBom);
      }
    );
  });

  // ── 7. Hardware Wiring Studio ──
  let mermaidRenderCount = 0;

  async function renderMermaidDiagram(source) {
    const container = document.getElementById('mermaid-diagram');
    const status = document.getElementById('mermaid-render-status');
    if (!container || !status) return;

    container.replaceChildren();
    if (!source) {
      status.textContent = 'No Mermaid wiring data is available for this build.';
      return;
    }
    if (!window.mermaid) {
      status.textContent = 'Diagram renderer unavailable; use the Mermaid source below.';
      return;
    }

    try {
      window.mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'dark',
        flowchart: { htmlLabels: false, curve: 'basis' }
      });
      const rendered = await window.mermaid.render(
        `forge-wiring-diagram-${++mermaidRenderCount}`,
        source
      );
      container.innerHTML = rendered.svg;
      status.textContent = 'Diagram generated from the active build wiring.';
    } catch (err) {
      status.textContent = 'Diagram rendering failed; use the Mermaid source below.';
      console.warn('Could not render Mermaid wiring diagram:', err);
    }
  }

  async function loadWiringStudio() {
    try {
      const w = await api.getWiring();
      state.wiringData = w;
      document.getElementById('wiring-svg-container').innerHTML = w.svg_canvas || '';
      document.getElementById('wokwi-json-preview').value = w.wokwi_json_str || '{}';
      document.getElementById('firmware-code-preview').textContent = w.arduino_code || '';
      document.getElementById('mermaid-source-preview').textContent = w.mermaid_code || '';
      await renderMermaidDiagram(w.mermaid_code || '');

      const pbody = document.querySelector('#pinout-table tbody');
      pbody.innerHTML = '';
      (w.connections || []).forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${c.from_part || ''} ${c.from_pin}</td><td>➔</td><td>${c.to_pin}</td><td>${c.color || 'Signal'}</td>`;
        pbody.appendChild(tr);
      });
    } catch (err) {
      console.warn('Could not load wiring studio:', err);
    }
  }

  // Wiring Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const tabKey = btn.dataset.wiringTab;
      document.querySelectorAll('.wiring-tab-pane').forEach(p => p.style.display = 'none');
      const target = document.getElementById(`tab-content-${tabKey}`);
      if (target) target.style.display = 'block';
    });
  });

  document.getElementById('btn-copy-mermaid')?.addEventListener('click', async () => {
    const source = document.getElementById('mermaid-source-preview').textContent;
    const status = document.getElementById('mermaid-render-status');
    try {
      await navigator.clipboard.writeText(source);
      status.textContent = 'Mermaid source copied.';
    } catch (err) {
      status.textContent = 'Could not copy source; select it from “View Mermaid source”.';
      console.warn('Could not copy Mermaid source:', err);
    }
  });

  document.getElementById('btn-prepare-wokwi')?.addEventListener('click', () => {
    window.open('https://wokwi.com/', '_blank', 'noopener,noreferrer');
    document.getElementById('wokwi-open-status').textContent =
      'The starter bundle is downloading and Wokwi is opening. Import diagram.json and sketch.ino there, then start the simulation.';
  });

  // ── 8. Delivery Optimizer ──
  async function loadDeliveryOptimizer() {
    try {
      const opt = await api.optimizeDelivery();
      const grid = document.getElementById('delivery-strategies-grid');
      grid.innerHTML = '';

      ['split', 'consolidated', 'smart'].forEach(key => {
        const s = opt[key];
        if (!s) return;
        const card = document.createElement('div');
        card.className = 'card';
        card.style.padding = '1rem';
        const isSmart = (key === 'smart');
        card.innerHTML = `
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:${isSmart ? 'var(--status-pass)' : 'var(--text-secondary)'};">
            ${isSmart ? '⚡ SMART LANDING COST' : (key === 'consolidated' ? '🏢 CONSOLIDATED' : '🏪 SPLIT STORES')}
          </div>
          <div style="font-size:1.15rem;font-weight:700;margin:4px 0;">₹${formatPrice(s.packages_info?.total_landing_cost ?? s.landing_cost ?? 0)}</div>
          <div class="caption">Parts: ₹${formatPrice(s.packages_info?.total_parts ?? s.parts_cost ?? 0)}</div>
          <div class="caption">Shipping: ₹${formatPrice(s.packages_info?.total_shipping ?? s.shipping_cost ?? 0)}</div>
          <button class="btn ${isSmart ? 'primary' : ''}" style="width:100%;margin-top:10px;">Apply Strategy</button>
        `;
        card.querySelector('button').onclick = async () => {
          await api.applyDeliveryStrategy(key);
          const updated = await api.getBill();
          renderBillTable(updated);
        };
        grid.appendChild(card);
      });
    } catch (err) {
      console.warn('Delivery optimizer:', err);
    }
  }

  // Resume Upload Trigger
  document.getElementById('btn-trigger-upload')?.addEventListener('click', () => {
    document.getElementById('resume-file-input').click();
  });

  document.getElementById('resume-file-input')?.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    document.getElementById('resume-status-label').textContent = `Uploading ${file.name}...`;
    try {
      const res = await api.uploadResume(file);
      document.getElementById('resume-status-label').textContent = `Read ${file.name}. Confirmed ${res.skills?.length || 0} factors.`;
    } catch (err) {
      document.getElementById('resume-status-label').textContent = `Upload error: ${err.message}`;
    }
  });
});
