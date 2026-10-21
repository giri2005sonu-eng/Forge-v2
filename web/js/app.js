function formatPrice(val) {
  if (val === null || val === undefined || isNaN(val)) return '—';
  return Number(val).toLocaleString();
}

document.addEventListener('DOMContentLoaded', async () => {
  const state = {
    stage: 'pick',
    questions: [],
    currentStep: 0,
    answers: {},
    activeProject: null,
    recommendations: [],
    catalog: [],
    activeBom: null,
    wiringData: null
  };

  // ── 1. Init & Sync State ──
  try {
    const s = await api.getState();
    state.stage = s.stage || 'pick';
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

  // ── Step Tracker Click Handlers ──
  document.querySelectorAll('.fg-step-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const targetStage = pill.dataset.stage;
      switchStage(targetStage);
    });
  });

  // ── Navigation Buttons ──
  document.getElementById('btn-goto-competition')?.addEventListener('click', () => switchStage('competition'));
  document.getElementById('btn-back-to-questions')?.addEventListener('click', () => switchStage('pick'));
  document.getElementById('btn-back-from-competition')?.addEventListener('click', () => switchStage('pick'));
  document.getElementById('btn-skip-discovery')?.addEventListener('click', () => switchStage('bom'));

  function switchStage(stageName) {
    state.stage = stageName;
    const stages = ['pick', 'results', 'competition', 'bom'];
    const currIdx = stages.indexOf(stageName);

    // Update Tracker Pills
    document.querySelectorAll('.fg-step-pill').forEach((pill, idx) => {
      const pStage = pill.dataset.stage;
      const numSpan = pill.querySelector('.fg-step-num');
      pill.classList.remove('active', 'completed', 'pending');

      if (idx < currIdx) {
        pill.classList.add('completed');
        if (numSpan) numSpan.textContent = '✓';
      } else if (idx === currIdx) {
        pill.classList.add('active');
        if (numSpan) numSpan.textContent = String(idx + 1);
      } else {
        pill.classList.add('pending');
        if (numSpan) numSpan.textContent = String(idx + 1);
      }
    });

    // Toggle Views
    document.getElementById('view-discovery').style.display = (stageName === 'pick') ? 'block' : 'none';
    document.getElementById('view-results').style.display = (stageName === 'results') ? 'block' : 'none';
    document.getElementById('view-competition').style.display = (stageName === 'competition') ? 'block' : 'none';
    document.getElementById('view-bom').style.display = (stageName === 'bom') ? 'block' : 'none';

    if (stageName === 'pick') renderSurveyStep(state.currentStep);
    if (stageName === 'competition') loadCompetitionEvents();
    if (stageName === 'bom' && !state.activeBom) loadInitialBom();
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

  async function triggerRecommendationRanking() {
    try {
      const res = await api.rankProjects(state.answers, 5);
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
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'card';
      card.style.cursor = 'pointer';
      card.innerHTML = `
        <div style="font-size:1.6rem;font-weight:800;color:var(--primary-orange);">${item.score}%</div>
        <div style="font-size:1.05rem;font-weight:700;margin:4px 0;">${item.label}</div>
        <p class="caption">${item.desc}</p>
        <div style="margin:10px 0;font-size:0.8rem;color:var(--text-secondary);">
          ${item.domain} · ${item.build_hours} hrs · ₹${formatPrice(item.cost_inr)}
        </div>
        <button class="btn primary" style="width:100%;margin-top:6px;">Choose</button>
      `;
      card.addEventListener('click', () => inspectProjectDetail(item));
      grid.appendChild(card);
    });

    if (items.length > 0) inspectProjectDetail(items[0]);
  }

  function inspectProjectDetail(item) {
    state.activeProject = item.key;
    const inspector = document.getElementById('project-detail-inspector');
    inspector.style.display = 'block';

    document.getElementById('detail-project-title').textContent = `${item.label} · ${item.score}% fit`;
    document.getElementById('detail-project-desc').textContent = item.desc;
    document.getElementById('detail-meta-list').innerHTML = `
      <div><b>Domain:</b> ${item.domain}</div>
      <div><b>Estimated build time:</b> ${item.build_hours} hours</div>
      <div><b>Estimated cost:</b> ₹${formatPrice(item.cost_inr)}</div>
      <div><b>Parts availability in India:</b> ${item.parts_availability_india}/5</div>
      <div><b>Tools required:</b> ${item.tools_required.join(', ') || 'Standard hand tools'}</div>
      <div><b>Required skills:</b> ${item.required_skills.join(', ') || 'Beginner friendly'}</div>
    `;

    const tbody = document.querySelector('#detail-fit-table tbody');
    tbody.innerHTML = '';
    (item.fit_breakdown || []).forEach(row => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${row.factor}</td><td>${row.rating}</td><td><b>${row.fit}</b></td>`;
      tbody.appendChild(tr);
    });

    // Render SVG Radar Chart
    document.getElementById('detail-radar-chart').innerHTML = item.chart_svg || '';

    // Action button
    const btn = document.getElementById('btn-build-bom-for-pick');
    btn.onclick = async () => {
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

    renderComponentCards(bom.parts || {}, bom.bill?.lines || []);
    renderChecks(bom.checks || []);
    renderBillTable(bom.bill);
    loadWiringStudio();
    loadDeliveryOptimizer();
  }

  function renderComponentCards(parts, lines) {
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

      const card = document.createElement('div');
      card.className = 'component-card';
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
            <p class="caption">Click <b>⚡ Find live prices</b> above to scan Indian electronic shops.</p>
          </div>
        </div>
      `;

      card.querySelector('.component-card-header').onclick = () => {
        card.classList.toggle('open');
      };

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
        const updatedBill = await api.getBill();
        renderBillTable(updatedBill);
        document.getElementById('metric-total-cost').textContent = `₹${formatPrice(updatedBill.total ?? updatedBill.grand_total ?? 0)}`;
        document.getElementById('metric-live-priced').textContent = `${updatedBill.live_priced_count || 0} live`;
      }
    );
  });

  // ── 7. Hardware Wiring Studio ──
  async function loadWiringStudio() {
    try {
      const w = await api.getWiring();
      state.wiringData = w;
      document.getElementById('wiring-svg-container').innerHTML = w.svg_canvas || '';
      document.getElementById('wokwi-json-preview').value = w.wokwi_json_str || '{}';
      document.getElementById('firmware-code-preview').textContent = w.arduino_code || '';

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
