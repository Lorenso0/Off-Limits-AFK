'use strict';

// ── State ────────────────────────────────────────────────────────────────────

const state = {
  scripts: [],
  selectedId: null,
  detail: null,
  status: null,
  keybindsInitialized: false,
  timingValues: {},
  pendingModal: null,
  activeTab: 'configure',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function $(id) { return document.getElementById(id); }
function setVisible(id, visible) {
  const el = typeof id === 'string' ? $(id) : id;
  el?.classList.toggle('hidden', !visible);
}

// ── Window drag ───────────────────────────────────────────────────────────────

let drag = null;

$('titlebar-drag').addEventListener('mousedown', async (e) => {
  if (e.button !== 0) return;
  const pos = await pywebview.api.get_position();
  drag = { sx: e.screenX, sy: e.screenY, wx: pos.x, wy: pos.y };
});

document.addEventListener('mousemove', (e) => {
  if (!drag) return;
  pywebview.api.move_window(drag.wx + (e.screenX - drag.sx), drag.wy + (e.screenY - drag.sy));
});

document.addEventListener('mouseup', () => { drag = null; });

// ── Init ──────────────────────────────────────────────────────────────────────

window.addEventListener('pywebviewready', async () => {
  try {
    const initial = await pywebview.api.get_initial_state();
    state.scripts = initial.scripts;
    state.keybindsInitialized = initial.keybinds_initialized;

    $('runtime-badge').textContent = initial.ahk_label || 'AHK v2';
    if (initial.version) $('version-badge').textContent = 'v' + initial.version;

    renderScriptList();
    renderPerks(initial.perks);
    pywebview.api.get_image_b64('pictures/logo.png').then(b64 => {
      if (b64) $('configure-logo').src = 'data:image/png;base64,' + b64;
    });

    if (initial.selected) {
      state.selectedId = initial.selected.id;
      state.detail = initial.selected;
      state.timingValues = Object.fromEntries(
        (initial.selected.timings || []).map(t => [t.key, t.value])
      );
      showDetail(initial.selected);
    }

    applyStatus(initial.status);
    updateKeybindBtn();
    pywebview.api.sync_scripts_cmd();
  } catch (e) {
    $('status-text').textContent = 'Init error: ' + e;
  }

  setInterval(pollStatus, 2500);
});

// ── Sync callback ─────────────────────────────────────────────────────────────

window.onSyncDone = function (scripts, summary, errors, updateInfo) {
  state.scripts = scripts;
  renderScriptList();
  $('sync-btn').disabled = false;
  $('sync-btn').textContent = 'Sync';
  $('status-text').textContent = 'Status: ' + summary;
  if (errors && errors.length) showModal('warning', 'Sync warning', errors.join('\n'));
  if (updateInfo && updateInfo.available && updateInfo.latest) {
    showModal('info', 'App update available',
      `A newer launcher version is available.\n\nCurrent: ${updateInfo.current}\nLatest:  ${updateInfo.latest}` +
      (updateInfo.url ? `\n\nDownload: ${updateInfo.url}` : ''));
  }
};

// ── Status polling ────────────────────────────────────────────────────────────

async function pollStatus() {
  try { applyStatus(await pywebview.api.get_status()); } catch (_) {}
}

function applyStatus(s) {
  if (!s) return;
  state.status = s;
  state.keybindsInitialized = s.keybinds_initialized;
  $('status-text').textContent = 'Status: ' + s.status_text;

  const btn = $('launch-btn');
  if (state.selectedId) {
    if (s.selected_is_running) {
      btn.textContent = (s.dirty_keys && s.dirty_keys.length) ? 'Relaunch with New Settings' : 'End Script';
      btn.className = 'launch-btn running';
    } else if (s.running) {
      btn.textContent = 'Launch Selected Script';
      btn.className = 'launch-btn inactive';
    } else {
      btn.textContent = 'Launch Selected Script';
      btn.className = 'launch-btn active';
    }
  }

  setVisible('dirty-badge', s.dirty_keys && s.dirty_keys.length > 0);
  setVisible('stop-all-btn', s.running || !!state.selectedId);
  setVisible('export-gpc-btn', !!state.detail?.has_gpc);
  updateKeybindBtn();
}

function updateKeybindBtn() {
  const attention = !state.keybindsInitialized;
  $('keybinds-btn').classList.toggle('attention', attention);
  setVisible('keybinds-dot', attention);
}

// ── Script list ───────────────────────────────────────────────────────────────

function renderScriptList() {
  const list = $('script-list');
  list.innerHTML = '';
  for (const s of state.scripts) {
    const item = document.createElement('div');
    item.className = 'script-item' +
      (s.disabled ? ' disabled' : '') +
      (s.id === state.selectedId ? ' selected' : '');

    const dot = document.createElement('span');
    dot.className = 'script-dot';
    if (s.id === state.selectedId) dot.style.background = s.accent;

    const name = document.createElement('span');
    name.textContent = s.name;

    item.append(dot, name);
    item.addEventListener('click', () => onScriptClick(s));
    list.appendChild(item);
  }
}

async function onScriptClick(script) {
  if (script.disabled) {
    showModal('info', 'Script unavailable', `${script.name} is currently disabled.`);
    return;
  }
  if (script.id === state.selectedId) return;

  const result = await pywebview.api.select_script(script.id);
  if (result.error) { showModal('error', 'Error', result.error); return; }

  state.selectedId = script.id;
  state.detail = result.detail;
  state.activePreset = null;
  state.timingValues = Object.fromEntries(
    (result.detail.timings || []).map(t => [t.key, t.value])
  );

  renderScriptList();
  showDetail(result.detail);
  applyStatus(result.status);
  loadSetupItems(result.detail.name);
}

// ── Detail / tabs ─────────────────────────────────────────────────────────────

function showDetail(detail) {
  setVisible('welcome', false);
  setVisible('detail', true);
  $('script-name').textContent = detail.name;
  renderTimings(detail.timings);
  loadSetupItems(detail.name);
  loadPresets(detail.id);
  switchTab(state.activeTab);
}

function switchTab(name) {
  state.activeTab = name;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === name);
  });
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('hidden', panel.id !== 'tab-' + name);
  });
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ── Timings ───────────────────────────────────────────────────────────────────

function renderTimings(timings) {
  const wrap = $('timings-wrap');
  wrap.innerHTML = '';
  setVisible('no-timings', !timings || !timings.length);
  if (!timings || !timings.length) return;

  const checks = timings.filter(t => t.control === 'checkbox');
  const inputs = timings.filter(t => t.control !== 'checkbox');

  // Build a map of key → DOM row so we can cross-reference dependencies
  const rowMap = {};

  if (checks.length) {
    const section = document.createElement('div');
    section.className = 'timings-section checks';
    for (const t of checks) {
      const row = buildTimingRow(t);
      rowMap[t.key] = row;
      section.appendChild(row);
    }
    wrap.appendChild(section);
  }
  if (inputs.length) {
    const section = document.createElement('div');
    section.className = 'timings-section inputs';
    for (const t of inputs) {
      const row = buildTimingRow(t);
      rowMap[t.key] = row;
      section.appendChild(row);
    }
    wrap.appendChild(section);
  }

  // block_input is only meaningful when background_input is on
  if (rowMap['block_input'] && rowMap['background_input']) {
    const bgCheck = rowMap['background_input'].querySelector('.timing-check');
    const blockRow = rowMap['block_input'];
    const syncBlock = () => blockRow.classList.toggle('hidden', !bgCheck?.checked);
    syncBlock();
    bgCheck?.addEventListener('change', syncBlock);
  }

  // ads_wait is only meaningful when reticle_mode is on
  if (rowMap['ads_wait'] && rowMap['reticle_mode']) {
    const reticleCheck = rowMap['reticle_mode'].querySelector('.timing-check');
    const adsRow = rowMap['ads_wait'];
    const syncAds = () => adsRow.classList.toggle('hidden', !reticleCheck?.checked);
    syncAds();
    reticleCheck?.addEventListener('change', syncAds);
  }
}

function buildTimingRow(t) {
  if (t.control === 'checkbox') {
    const wrap = document.createElement('div');
    wrap.className = 'timing-row';
    const label = document.createElement('label');
    label.className = 'timing-checkbox-wrap timing-label';
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.className = 'timing-check';
    check.checked = state.timingValues[t.key] === t.true_value;
    check.addEventListener('change', async () => {
      const val = check.checked ? t.true_value : t.false_value;
      state.timingValues[t.key] = val;
      const res = await pywebview.api.update_timing(t.key, val);
      setVisible('dirty-badge', res.dirty_keys && res.dirty_keys.length > 0);
      if (t.key === 'reticle_mode') onReticleModeToggled(check.checked);
      if (t.key === 'background_input') onBackgroundInputToggled(check.checked);
    });
    label.append(check, document.createTextNode(t.label));
    wrap.appendChild(label);
    return wrap;
  }

  const row = document.createElement('div');
  row.className = 'timing-row';

  const labelEl = document.createElement('span');
  labelEl.className = 'timing-label';
  labelEl.textContent = t.label;

  const inputGroup = document.createElement('div');
  inputGroup.className = 'timing-input-group';

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'timing-input';
  input.id = 'timing-' + t.key;
  input.value = state.timingValues[t.key] ?? t.value;
  input.addEventListener('input', async () => {
    state.timingValues[t.key] = input.value;
    const res = await pywebview.api.update_timing(t.key, input.value);
    input.classList.toggle('dirty', res.dirty_keys && res.dirty_keys.length > 0);
    setVisible('dirty-badge', res.dirty_keys && res.dirty_keys.length > 0);
  });
  inputGroup.appendChild(input);

  if (t.suffix) {
    const suf = document.createElement('span');
    suf.className = 'timing-suffix';
    suf.textContent = t.suffix;
    inputGroup.appendChild(suf);
  }

  if (t.key === 'pre_melee_wait') {
    const labelWrap = document.createElement('div');
    labelWrap.className = 'timing-label-wrap';
    const hint = document.createElement('span');
    hint.className = 'timing-hint';
    hint.textContent = 'If recoil climbs, increase this.';
    labelWrap.append(labelEl, hint);
    row.append(labelWrap, inputGroup);
  } else {
    row.append(labelEl, inputGroup);
  }

  return row;
}

// ── Presets ───────────────────────────────────────────────────────────────────

state.activePreset = null;

async function loadPresets(scriptId) {
  const presets = await pywebview.api.get_presets(scriptId);
  state.activePreset = null;
  updatePresetUI(presets);
}

function updatePresetUI(presets) {
  setVisible('preset-control', true);
  renderPresetMenu(presets);
  syncActivePresetLabel();
}

function syncActivePresetLabel() {
  $('preset-dropdown-label').textContent = state.activePreset || 'Presets';
  $('preset-dropdown-btn').classList.toggle('has-active', !!state.activePreset);
  setVisible('update-preset-btn', !!state.activePreset);
}

function renderPresetMenu(presets) {
  const list = $('preset-menu-list');
  list.innerHTML = '';
  if (!presets || !presets.length) {
    const empty = document.createElement('div');
    empty.className = 'preset-menu-empty';
    empty.textContent = 'No saved presets yet.';
    list.appendChild(empty);
    return;
  }
  for (const p of presets) {
    const row = document.createElement('div');
    row.className = 'preset-menu-item' + (p.name === state.activePreset ? ' active' : '');

    const nameEl = document.createElement('span');
    nameEl.className = 'preset-menu-name';
    nameEl.textContent = p.name;
    nameEl.addEventListener('click', () => applyPreset(p.name));

    const delBtn = document.createElement('button');
    delBtn.className = 'preset-menu-del';
    delBtn.textContent = '×';
    delBtn.title = 'Delete preset';
    delBtn.addEventListener('click', (e) => { e.stopPropagation(); removePreset(p.name); });

    row.append(nameEl, delBtn);
    list.appendChild(row);
  }
}

async function applyPreset(name) {
  if (!state.selectedId) return;
  const res = await pywebview.api.load_preset(state.selectedId, name);
  if (!res.ok) { showModal('error', 'Error', res.message); return; }
  state.activePreset = name;
  state.timingValues = Object.fromEntries(res.timings.map(t => [t.key, t.value]));
  if (state.detail) state.detail.timings = res.timings;
  renderTimings(res.timings);
  setVisible('dirty-badge', res.dirty_keys && res.dirty_keys.length > 0);
  closePresetDropdown();
  syncActivePresetLabel();
}

async function removePreset(name) {
  if (!state.selectedId) return;
  const res = await pywebview.api.delete_preset(state.selectedId, name);
  if (!res.ok) return;
  if (state.activePreset === name) {
    state.activePreset = null;
    syncActivePresetLabel();
  }
  renderPresetMenu(res.presets);
}

$('save-preset-btn').addEventListener('click', async () => {
  const input = $('preset-name-input');
  const name = input.value.trim();
  if (!name) { input.focus(); return; }
  if (!state.selectedId) return;
  const res = await pywebview.api.save_preset(state.selectedId, name);
  if (!res.ok) { showModal('error', 'Error', res.message); return; }
  input.value = '';
  state.activePreset = name;
  renderPresetMenu(res.presets);
  syncActivePresetLabel();
});

$('preset-name-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $('save-preset-btn').click();
  e.stopPropagation();
});

$('update-preset-btn').addEventListener('click', async () => {
  if (!state.selectedId || !state.activePreset) return;
  const res = await pywebview.api.save_preset(state.selectedId, state.activePreset);
  if (!res.ok) { showModal('error', 'Error', res.message); return; }
  renderPresetMenu(res.presets);
});

// Dropdown toggle
$('preset-dropdown-btn').addEventListener('click', (e) => {
  e.stopPropagation();
  const menu = $('preset-dropdown-menu');
  const opening = menu.classList.contains('hidden');
  menu.classList.toggle('hidden', !opening);
  if (opening) setTimeout(() => $('preset-name-input').focus(), 50);
});

function closePresetDropdown() {
  $('preset-dropdown-menu').classList.add('hidden');
}

document.addEventListener('click', (e) => {
  if (!$('preset-dropdown-wrap').contains(e.target)) closePresetDropdown();
});

// ── Background input ──────────────────────────────────────────────────────────

async function onBackgroundInputToggled(checked) {
  if (!checked) return;
  const pref = await pywebview.api.get_pref('suppress_background_input_warning');
  if (pref.value) return;
  showModal('warning', 'Background Input — Experimental',
    'This feature is experimental and may not work correctly on all systems.\n\n' +
    'Use the Launch button to start and stop the script. (Your toggle hotkey is disabled in this mode.)\n\n' +
    'The Call of Duty window must NOT be in focus when you start — alt-tab out before clicking Launch.\n\n' +
    'If inputs are not registering, try running the launcher as administrator.',
    'suppress_background_input_warning');
}

// ── Reticle mode ──────────────────────────────────────────────────────────────

async function onReticleModeToggled(checked) {
  const key = 'v_wait_time';
  const val = checked ? '900' : '550';
  const input = document.getElementById('timing-' + key);
  if (input) { input.value = val; state.timingValues[key] = val; await pywebview.api.update_timing(key, val); }
  if (!checked) return;
  const pref = await pywebview.api.get_pref('suppress_reticle_mode_warning');
  if (pref.value) return;
  showModal('info', 'Reticle Mode',
    'Reticle Mode aims down sight before each shot to satisfy the reticle tracking requirement.\n\n' +
    "Check your weapon's Aim Down Sight Speed stat — the ADS settle time must be ≥ that value, " +
    'or the reticle kill will not count.',
    'suppress_reticle_mode_warning');
}

// ── Setup ─────────────────────────────────────────────────────────────────────

async function loadSetupItems(scriptName) {
  renderSetup(await pywebview.api.get_setup_items(scriptName));
}

function renderSetup(data) {
  const stepsEl = $('setup-steps');
  stepsEl.innerHTML = '';

  for (const item of data.items) {
    const row = document.createElement('div');
    row.className = 'setup-step';
    const bullet = document.createElement('span');
    bullet.className = 'setup-bullet';
    bullet.textContent = '→';
    const text = document.createElement('span');
    text.textContent = item;
    row.append(bullet, text);
    stepsEl.appendChild(row);
  }

  if (data.tip) {
    const tipRow = document.createElement('div');
    tipRow.className = 'setup-tip-row';
    const bullet = document.createElement('span');
    bullet.className = 'setup-bullet';
    bullet.textContent = '→';
    const tipText = document.createElement('span');
    tipText.className = 'setup-tip-text';
    tipText.textContent = data.tip;
    tipRow.append(bullet, tipText);
    stepsEl.appendChild(tipRow);
  }

  // Setup position image (large preview card, top-left)
  const setupBtn = $('setup-img-btn');
  const setupImg = $('setup-image');
  if (data.setup_image) {
    pywebview.api.get_image_b64('pictures/Spot.png').then(b64 => {
      if (b64) {
        setupImg.src = 'data:image/png;base64,' + b64;
        setupBtn.onclick = () => openPreview(setupImg.src);
      }
    });
  }

  // Tip image (large preview card, top-right)
  const tipBtn = $('tip-img-btn');
  const tipImg = $('tip-image');
  if (data.tip_image) {
    setVisible(tipBtn, true);
    pywebview.api.get_image_b64('pictures/Closed.png').then(b64 => {
      if (b64) {
        tipImg.src = 'data:image/png;base64,' + b64;
        tipBtn.onclick = () => openPreview(tipImg.src);
      }
    });
  } else {
    setVisible(tipBtn, false);
  }
}

// ── Perks ─────────────────────────────────────────────────────────────────────

function renderPerks(perks) {
  renderPerkCol($('perks-required'), perks.required);
  renderPerkCol($('perks-recommended'), perks.recommended);
}

function renderPerkCol(container, perks) {
  container.innerHTML = '';
  for (const perk of perks) {
    const card = document.createElement('div');
    card.className = 'perk-card';

    // Icon
    const iconWrap = document.createElement('div');
    iconWrap.className = 'perk-icon-wrap';
    if (perk.image) {
      const img = document.createElement('img');
      img.alt = perk.name;
      iconWrap.appendChild(img);
      pywebview.api.get_image_b64(perk.image).then(b64 => {
        if (b64) img.src = 'data:image/png;base64,' + b64;
        else iconWrap.innerHTML = '<div class="perk-icon-placeholder">?</div>';
      });
    } else {
      iconWrap.innerHTML = '<div class="perk-icon-placeholder">?</div>';
    }

    // Details
    const details = document.createElement('div');
    details.className = 'perk-details';

    const name = document.createElement('div');
    name.className = 'perk-name';
    name.textContent = perk.name;
    details.appendChild(name);

    if (perk.augments && perk.augments.length) {
      const list = document.createElement('div');
      list.className = 'augments-list';

      for (const aug of perk.augments) {
        const row = document.createElement('div');
        row.className = 'augment-row';

        const augImgWrap = document.createElement('div');
        augImgWrap.className = 'augment-img-wrap';
        if (aug.image) {
          const augImg = document.createElement('img');
          augImg.alt = aug.name;
          augImgWrap.appendChild(augImg);
          pywebview.api.get_image_b64(aug.image).then(b64 => {
            if (b64) augImg.src = 'data:image/png;base64,' + b64;
          });
        }

        const slot = document.createElement('span');
        slot.className = 'augment-slot ' + aug.slot.toLowerCase();
        slot.textContent = aug.slot === 'Major' ? 'Maj' : 'Min';

        const augName = document.createElement('span');
        augName.className = 'augment-name';
        augName.textContent = aug.name;

        row.append(augImgWrap, slot, augName);
        list.appendChild(row);
      }
      details.appendChild(list);
    }

    card.append(iconWrap, details);
    container.appendChild(card);
  }
}

// ── Launch / stop ─────────────────────────────────────────────────────────────

$('launch-btn').addEventListener('click', async () => {
  const s = state.status;
  if (s && s.selected_is_running && !(s.dirty_keys && s.dirty_keys.length)) {
    const res = await pywebview.api.stop_selected();
    applyStatus(res.status);
    return;
  }
  if (!state.selectedId) return;
  const res = await pywebview.api.launch_selected();
  if (!res.ok) showModal('error', 'Launch failed', res.message);
  applyStatus(res.status);
});

$('stop-all-btn').addEventListener('click', async () => {
  applyStatus((await pywebview.api.stop_all()).status);
});

$('sync-btn').addEventListener('click', () => {
  $('sync-btn').disabled = true;
  $('sync-btn').textContent = 'Syncing…';
  $('status-text').textContent = 'Status: Checking for updates…';
  pywebview.api.sync_scripts_cmd();
});

// ── Keybinds ──────────────────────────────────────────────────────────────────

$('keybinds-btn').addEventListener('click', openKeybinds);

async function openKeybinds() {
  const keybinds = await pywebview.api.get_keybinds();
  const container = $('kb-inputs');
  container.innerHTML = '';
  for (const kb of keybinds) {
    const row = document.createElement('div');
    row.className = 'kb-row';
    const label = document.createElement('span');
    label.className = 'kb-label';
    label.textContent = kb.label;
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'kb-input';
    input.dataset.key = kb.key;
    input.value = kb.value;
    if (kb.placeholder) input.placeholder = kb.placeholder;
    input.addEventListener('input', () => { input.value = input.value.toUpperCase(); });
    row.append(label, input);
    container.appendChild(row);
  }
  setVisible('kb-overlay', true);
}

function closeKeybinds() { setVisible('kb-overlay', false); }

async function saveKeybinds() {
  const data = Array.from(document.querySelectorAll('#kb-inputs .kb-input')).map(inp => ({
    key: inp.dataset.key, value: inp.value,
  }));
  const res = await pywebview.api.save_keybinds(data);
  if (res.ok) { state.keybindsInitialized = true; updateKeybindBtn(); closeKeybinds(); }
}

// ── Modal ─────────────────────────────────────────────────────────────────────

function showModal(level, title, message, suppressKey) {
  const badge = $('modal-badge');
  badge.className = 'badge ' + (level === 'error' ? 'badge-error' : level === 'warning' ? 'badge-warn' : 'badge-info');
  badge.textContent = level.toUpperCase();
  $('modal-title-text').textContent = title;
  $('modal-message').textContent = message;
  state.pendingModal = suppressKey ? { suppressKey } : null;
  $('modal-suppress-check').checked = false;
  setVisible('modal-suppress-wrap', !!suppressKey);
  setVisible('modal-overlay', true);
}

function closeModal() {
  if (state.pendingModal && $('modal-suppress-check').checked)
    pywebview.api.suppress_warning(state.pendingModal.suppressKey);
  state.pendingModal = null;
  setVisible('modal-overlay', false);
}

// ── Preview ───────────────────────────────────────────────────────────────────

function openPreview(src) {
  if (!src) return;
  $('preview-img').src = src;
  setVisible('preview-overlay', true);
}

function closePreview() { setVisible('preview-overlay', false); }
