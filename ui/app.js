// Save Garage - Copyright (C) 2026 NotHGM - GNU GPL v3 with the additional terms in NOTICE; see LICENSE.
'use strict';
// Save Garage: redesigned UI for the local save editor service (same /api as the original UI, plus /api/slot and /api/stats).
(() => {
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const T = s => window.SGI18N?.tr(s) ?? s;          // text shown outside the page (dialogs) in the chosen language
  const nf = new Intl.NumberFormat('en-US');
  const nf2 = new Intl.NumberFormat('en-US', {maximumFractionDigits: 2});
  const main = $('#main'), routeEl = $('#route'), statusEl = $('#status'), pendingEl = $('#pending'), toastEl = $('#toast');

  const STEPS = [['connect', 'Connect'], ['signin', 'Sign in'], ['pair', 'Pair'], ['download', 'Download'], ['edit', 'Edit'], ['send', 'Send back']];
  const OWNER = {0: 'Total', 1: 'Lucia', 2: 'Jason'};
  const MONEY_GROUP = '$0x97232209';
  const PS5_TRANSFER = 'Settings, then System, then System Software, then Data Transfer';
  const PS5_DELETE = 'Settings, then Saved Data and Game/App Settings, then Saved Data (PS5), then Console Storage, then Delete';
  const CATS = [
    ['progress', 'Progress', 'Percentages and counters from the stats screen.'],
    ['skills', 'Skills', 'Overpowers and buffs for health, stamina and focus, plus workouts and meditations. The total updates itself to Lucia plus Jason.'],
    ['time', 'Time and distance', 'Time played and how you got around. Times are in hours.'],
    ['earnings', 'Money earned', 'Records of money you earned. Changing these does not add money. Use the Money tab for that.'],
    ['wanted', 'Wanted levels', 'How often and how long the police were after you. Times are in hours.'],
    ['records', 'Records', 'Combat, vehicle and other counters.'],
    ['trophies', 'Trophy counters', 'Counters behind some of the trophies. A PS5 keeps edited values, even above the game\u2019s own totals. Raising one may make the game award the trophy the next time the counter goes up, and trophy sites such as PSNProfiles may flag that. The things a counter counts are not changed, so the numbers can stop matching.'],
    ['gadgets', 'Gadgets', 'Flags for gadgets you picked up.']];
  const TYPE_MAX = {int32: 2147483647, u32: 4294967295, int64: 9007199254740991, int16: 32767, u8: 127, float: 1e12};
  const STAGE = {
    pair_waiting_console: 'Waiting for the PS5', pair_reading: 'Reading the pairing request', paired: 'Paired',
    connecting: 'Connecting to your PS5', key_retry: 'The key service was slow, trying again', need_power: 'Press the PS5 power button', reading_list: 'Reading the save list',
    key_rate_wait: 'GarlicSaves is getting too many requests right now, so it is briefly limiting them.',
    choose_account: 'Choose the PS5 account', downloading: 'Downloading your save', decrypting: 'Decrypting your save', ready: 'Your save is ready to edit',
    patching: 'Applying your edits', encrypting: 'Encrypting the edited save', importing: 'Getting the save ready to send',
    ready_to_upload: 'Edits saved and ready to send', preparing: 'Preparing the transfer',
    resigning: 'Signing the saves for the other account', resign_check: 'Checking the copy for the other account', waiting_console: 'Waiting for Data Transfer on the PS5',
    console_connected: 'PS5 connected. Keep this page open.', transferring: 'Sending your save', uploaded: 'Your save is back on the PS5', starting: 'Starting'};
  // GarlicSaves limits the jobs it takes from each sign-in's key: in a download's key requests (key_rate_limited) or in
  // decrypting and encrypting a save (garlic_rate_limited)
  const RATE_LIMITED = 'GarlicSaves is getting too many requests right now, so it is briefly limiting them. Wait a minute and try again. Nothing is wrong with your PS5 or Save Garage.';
  const ERR = {
    garlic_unreachable: 'The decryption service (garlicsaves.com) can’t be reached. Check your internet connection, then try again.',
    not_paired: 'This PS5 isn’t paired yet. Pair it first.',
    power_timeout: 'The power-button wait timed out. Go back to the PS5 home screen and try again.',
    key_timeout: 'GarlicSaves’ key service didn’t answer in time. Its worker consoles are busy, so wait a minute and try again. Nothing is wrong with your PS5 or Save Garage.',
    key_rate_limited: RATE_LIMITED,
    // GarlicSaves turned down the key of this computer's sign-in (HTTP 401, or 403 from its API): the job box offers Sign in again
    key_disabled: 'GarlicSaves refused your sign-in for key requests. It may have been turned off, or it may have expired. Sign in again, then try once more.',
    garlic_rate_limited: RATE_LIMITED,
    garlic_key_disabled: 'GarlicSaves refused your sign-in for decrypting and encrypting saves. It may have been turned off, or it may have expired. Sign in again, then try once more.',
    not_signed_in: 'Sign in to GarlicSaves first. Save Garage needs your sign-in to pair, download, save edits and send saves back.',
    console_timeout: 'The PS5 didn’t answer. Go back to the PS5 home screen, make sure no other tool is using Data Transfer, and try again.',
    console_rejected: 'The PS5 refused the request. Sign in with the account you paired with, or pair again.',
    no_gta_save: 'No GTA VI save was found on the PS5. Save once in the game, then try again.',
    no_story_slot: 'No story save was found. Save once in story mode, then try again.',
    // sending to another account on the PS5: GarlicSaves' resign failed, or the copy didn't check out (nothing was sent)
    resign_failed: 'GarlicSaves couldn’t sign the saves for the other account, so nothing was sent. Try again in a minute.',
    // GarlicSaves kept sending back a damaged copy of every story save in the download (issue #11)
    decrypt_bad: 'None of the saves in this download could be read, even after asking GarlicSaves to decrypt them again. The saves on your PS5 are fine. Wait a few minutes, then download again.',
    pair_failed: 'Pairing failed or timed out. Start pairing again.',
    save_layout_changed: 'The save layout is different from what this editor knows. Download again. If it still fails, the editor needs an update.',
    save_verify_failed: 'A value in the save didn’t match what was expected. Download again and redo the edit.',
    save_stale_item: 'Some values changed since this page loaded them. Reload the page and redo the edit.',
    save_protected_stat: 'That stat is kept in sync by the Money tab and can’t be edited directly.',
    save_bad_value: 'One of the new values isn’t valid for its field.',
    save_out_of_range: 'One of the new values is outside the allowed range.',
    save_bad_time: 'The time of day needs an hour from 0 to 23 and a minute from 0 to 59.',
    save_fog_version: 'This save’s map data has a version Save Garage doesn’t know yet, so the map is left alone.',
    save_fog_entry: 'An entry in this save’s map data doesn’t look the way Save Garage expects, so the map is left alone.',
    save_fog_repeat: 'This save’s map data lists a region twice, so the map is left alone.',
    save_attributes_layout: 'This character’s attributes don’t have the 37 values Save Garage expects, so they are left alone.',
    save_relationship_locked: 'The game has locked the relationship at this point in the story, so it can’t be changed.',
    save_relationship_disabled: 'The game has switched the relationship off at this point in the story, so it can’t be changed.',
    save_no_vest: 'This character wears no armour and has no vest in the wardrobe to put on.',
    save_guns_layout: 'This character’s inventory doesn’t look the way Save Garage expects, so no guns are added.',
    save_inventory_damaged: 'This character’s inventory already breaks a rule the game keeps, such as an item listed twice, so guns are left alone to keep it safe.',
    save_item_limit: 'There isn’t room in the inventory for these guns, because Save Garage always leaves 300 slots free.',
    save_not_offered: 'That gun can’t be added to this character. Reload the page and try again.',
    save_cheats_layout: 'This save’s cheat trackers don’t look the way Save Garage expects, so they are left alone.',
    save_read_only: 'That part of the save is read-only.',
    save_not_editable: 'Only numbers and true/false values can be changed.',
    save_bad_request: 'The edit didn’t match this save. Reload the page and try again.',
    no_change: 'Nothing changed. Edit a value first.',
    port_in_use: 'Ports 1004 to 1006 are already in use. Close any other save-transfer tool or another copy of Save Garage.',
    upload_failed: 'Sending failed. Check the PS5 and the network, then try again.',
    download_failed: 'The download failed. Go back to the PS5 home screen and try again.',
    // the PS5 asked for IPv6 data, psutil couldn't be loaded and Windows' own adapter list couldn't be read (PR #18)
    adapter_query_failed: 'Windows couldn’t list this computer’s network adapters. Unzip the whole Save Garage download into a new folder and start it from there.',
    tool_failed: 'Save processing failed. Open the details below.',
    internal: 'Something went wrong. Open the details below.',
    busy: 'Another task is running. Wait for it to finish.',
    bad_request: 'That choice is no longer available. Start the download again.',
    no_console: 'No PS5 selected. Connect first.',
    no_session: 'No save downloaded yet.',
    nothing_to_upload: 'There are no saved edits to send.',
    console_not_found: 'No PS5 answered at that address. Check the IP address and that the PS5 is on.',
    no_update: 'There’s no update ready to install.',
    request_failed: 'Save Garage didn’t answer. Check that it is still running.'};
  // why an update was refused or rolled back (state.update.error), after "Update failed:"
  const UPD_WHY = {
    network: 'the download didn’t finish', unsigned: 'the release isn’t signed', bad_signature: 'the release signature isn’t valid',
    bad_version: 'the release files carry the wrong version', no_asset: 'the release has no download for this computer',
    bad_checksum: 'the download doesn’t match its signed checksum', too_large: 'the download is larger than allowed',
    bad_archive: 'the download holds unsafe files', bad_package: 'the download isn’t a Save Garage build for this computer',
    disk: 'the update couldn’t be saved on this computer', install_failed: 'the new version couldn’t be put in place',
    start_failed: 'the new version didn’t start', internal: 'something went wrong'};
  const RELEASES = 'https://github.com/NotHGM/save-garage/releases';
  // why a GarlicSaves sign-in stopped (state.garlic.signin.error; {0} is the HTTP status of GarlicSaves' answer)
  const SIGNIN_ERR = {
    unreachable: ERR.garlic_unreachable, rate_limited: RATE_LIMITED,
    expired: 'The code expired before the sign-in was approved. Start again for a new code.',
    refused: 'GarlicSaves refused the sign-in. If you didn’t mean to turn it down, start again.',
    unavailable: 'GarlicSaves couldn’t handle the sign-in just now (HTTP {0}). Try again in a few minutes.',
    bad_answer: 'GarlicSaves sent an answer Save Garage doesn’t understand (HTTP {0}). Try again later. If it keeps happening, Save Garage may need an update.',
    bad_link: 'GarlicSaves sent a sign-in link that isn’t a web address, so Save Garage won’t open it. Try again later. If it keeps happening, Save Garage may need an update.',
    not_saved: 'Save Garage couldn’t save the sign-in in its data folder. Check that the folder can be written to, then sign in again.',
    internal: 'Something went wrong while signing in. Try again.'};
  const signinError = s => (SIGNIN_ERR[s.error] || SIGNIN_ERR.internal).replace('{0}', Number.isInteger(s.http) ? s.http : '?');
  // the step to come back to after signing in, for a job that needs the sign-in
  const SIGNIN_BACK = {pair: 'pair', download: 'download', patch: 'edit', upload: 'send', restore: 'send'};
  // a sign-in link GarlicSaves gave (the server only passes on http and https addresses; checked again here)
  const webLink = v => typeof v === 'string' && /^https?:\/\/[!-~]+$/i.test(v) ? v : null;

  const S = {
    state: null, failures: 0, offline: false, manualView: null, consoles: null, searching: false, mainKey: '',
    slot: null, tab: 'money', detail: {}, stats: {}, comp: {}, world: {}, sd: {}, stuntSel: {}, stuntKeys: {}, drafts: {}, sig: '', deleted: false, reviewOpen: false,
    preview: {}, compExp: {}, keep: {},
    find: {q: '', varies: true, named: false, game: false, limit: 150}, lastJob: '', localError: null,
    restarting: null, updAuto: null, signinFor: null, lastSignin: null};

  // ------------------------------------------------------------ api
  async function api(path, body) {
    const post = body !== undefined;
    const r = await fetch(path, post
      ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal: AbortSignal.timeout(90000)}
      : {cache: 'no-store', signal: AbortSignal.timeout(30000)});
    let data = null;
    try { data = await r.json(); } catch { /* empty body */ }
    if (!r.ok) {
      const e = new Error((data && data.error) || 'request_failed');
      e.code = (data && data.error) || 'request_failed';
      e.detail = data && data.detail;
      throw e;
    }
    return data;
  }

  async function act(path, body, after) {
    S.localError = null;
    try {
      const out = await api(path, body ?? {});
      if (after) after(out);
    } catch (e) {
      S.localError = {code: e.code || 'request_failed', detail: e.detail || ''};
      renderJob();
    }
  }

  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toast.t);
    toast.t = setTimeout(() => toastEl.classList.remove('show'), 4200);
  }

  // ------------------------------------------------------------ state
  const slotsSig = st => (st.slots || []).map(s => s.file + ':' + s.revision).join('|') + '|' + st.entryId;
  const slotOf = file => (S.state?.slots || []).find(s => s.file === file);
  const running = () => S.state?.job?.status === 'running';
  const label = s => s.file === 'sdimg_sce_sdmemory' ? 'Autosave' : 'Manual save';
  const missionName = s => String(s.subtitle || s.file).replace(/^\(Autosave\)\s*/, '');
  // a slot left out of the download because it couldn't be read (state.skipped): its title, else its file's number
  const skippedName = s => s.subtitle ? missionName(s) : s.file.replace(/^sdimg_(SAVEDATA)?/, '');
  // the steps: a Save Garage from before 1.30.0 has no GarlicSaves sign-in (no state.garlic), so no Sign in step either
  const stepsOf = st => st?.garlic ? STEPS : STEPS.filter(([id]) => id !== 'signin');
  const stepNo = (id, st) => stepsOf(st).findIndex(([x]) => x === id) + 1;
  // pairing, downloads, saving edits and sending go through GarlicSaves: without a sign-in the page asks for one first
  const mustSignIn = st => !!(st?.garlic && !st.garlic.signedIn);

  function viewFor(st) {
    const job = st.job || {};
    if (job.status === 'running') return {pair: 'pair', download: 'download', patch: 'edit', restore: 'send', upload: 'send'}[job.kind] || 'edit';
    const ok = id => available(id, st);
    if (S.manualView && ok(S.manualView)) return S.manualView;
    if (!st.console) return 'connect';
    if (mustSignIn(st)) return 'signin';
    if (!st.paired) return 'pair';
    if (!st.hasSession) return 'download';
    if (job.kind === 'upload' && job.stage === 'uploaded') return 'send';
    return 'edit';
  }

  function available(id, st) {
    return {connect: true, signin: !!st.garlic, pair: !!st.console, download: !!(st.console && st.paired), edit: !!st.hasSession, send: !!st.hasSession}[id];
  }

  function onState(st) {
    if (S.restarting && (S.restarting.down || st.version !== S.restarting.from) && !st.update?.restarting) {
      const host = S.restarting.host;           // Save Garage is back after Restart now: check the service, pick the PS5 again
      S.restarting = null;
      api('/api/network', {}).catch(() => {});
      if (host && !st.console) api('/api/console', {host}).then(s => { S.manualView = null; onState(s); }).catch(() => {});
    }
    const prevJob = S.lastJob;
    const job = st.job || {};
    const jobKey = job.id + ':' + job.status;
    const sig = slotsSig(st);
    if (sig !== S.sig) {                         // new download: forget per-save data
      S.sig = sig; S.detail = {}; S.stats = {}; S.comp = {}; S.world = {}; S.sd = {}; S.stuntSel = {}; S.stuntKeys = {}; S.drafts = {};
      const slots = sortedSlots(st);
      S.slot = slots.length ? slots[0].file : null;
    }
    S.state = st;
    if (prevJob && prevJob !== jobKey && job.status === 'done') jobDone(job);
    if (prevJob && prevJob !== jobKey && job.status === 'error') S.localError = null;
    S.lastJob = jobKey;
    const signin = st.garlic?.signin?.status;
    if (S.lastSignin && S.lastSignin !== 'done' && signin === 'done') signedIn();
    S.lastSignin = signin || null;
    for (const s of st.slots || []) seedDraft(s);
    renderStatus();
    renderFoot();
    renderRoute();
    renderMain();
    renderSigninLeft();
    renderJob();
    renderPending();
  }

  // a sign-in just went through: say so, then go back to what needed it (or on to the next step)
  function signedIn() {
    passed('Signed in', 'GarlicSaves approved Save Garage on this computer.');
    S.manualView = S.signinFor || null;
    S.signinFor = null; S.localError = null; S.mainKey = '';
  }

  // show the sign-in step; back: the step that needed the sign-in, to return to once signed in; start: begin at once
  function goSignIn(back, start) {
    S.localError = null; S.signinFor = back || S.signinFor || null; S.manualView = 'signin'; S.mainKey = '';
    renderRoute(); renderMain(); renderSigninLeft(); renderJob(); renderPending(); main.focus();
    if (start) {
      act('/api/signin', {}, g => { if (S.state) S.state.garlic = g; S.mainKey = ''; renderStatus(); renderMain(); renderSigninLeft(); });
    }
  }

  function jobDone(job) {
    const s = slotOf(S.slot);
    const msg = {pair: 'PS5 paired. Next: download your save.', download: 'Save downloaded. Pick what to change.',
                 patch: 'Edits saved. Send the save back when you’re done.',
                 restore: 'Originals are back in place. Send them to the PS5 to undo your edits.', upload: 'Save sent to the PS5.'}[job.kind];
    if (job.kind === 'patch') passed('Edits saved', 'Ready to send back to your PS5');
    else if (job.kind === 'upload') passed('Save delivered', 'Load it in GTA VI to check your changes');
    else if (msg) toast(msg);
    if (job.kind === 'pair' || job.kind === 'download') S.manualView = null;
    if (job.kind === 'upload') S.deleted = false;
  }

  async function poll() {
    try {
      const st = await api('/api/state');
      S.failures = 0; S.offline = false;
      onState(st);
    } catch {
      if (S.restarting) {
        S.restarting.down = true;
        if (Date.now() - S.restarting.at > 180000) S.restarting = null;
      }
      if (++S.failures >= 3) { S.offline = true; renderStatus(); }
    } finally {
      setTimeout(poll, 1000);
    }
  }

  // ------------------------------------------------------------ header and route
  function renderFoot() {
    const st = S.state || {};
    $('#version').textContent = st.version ? 'Version ' + st.version : '';
    $('#quit').hidden = !st.canQuit;
    renderUpdate();
  }

  // the update row of the footer: what the updater is doing (state.update, see docs/API.md) and its controls
  function renderUpdate() {
    const box = $('#update'), u = S.state?.update;
    if (!u) { box.hidden = true; return; }       // a Save Garage from before 1.30.0
    const link = typeof u.notes === 'string' && u.notes.startsWith(RELEASES + '/') ? u.notes : RELEASES;
    const pct = u.status === 'downloading' && u.total > 0 && u.progress >= 0 ? Math.min(100, Math.floor(100 * u.progress / u.total)) : null;
    const [dot, text] = S.restarting || u.restarting ? ['wait', 'Restarting Save Garage…']
      : u.status === 'checking' ? ['wait', 'Checking for updates…']
      : u.status === 'downloading' ? ['wait', `Downloading Save Garage ${u.latest}`]
      : u.status === 'ready' ? ['ok', `${u.latest} will install next time you start Save Garage.`]
      : u.status === 'failed' ? ['bad', `Update failed: ${UPD_WHY[u.error] || UPD_WHY.internal}, Save Garage stays on ${u.current}.`]
      : u.status === 'available' ? ['wait', `A new version is out: ${u.latest}.`]
      : u.status === 'check_failed' ? ['bad', 'Couldn’t reach GitHub to check for updates.']
      : u.installed ? ['ok', `Save Garage was updated to ${u.installed}.`]
      : u.status === 'current' ? ['ok', 'Up to date'] : ['', ''];
    const status = text ? `<span class="dot ${dot}"></span><span>${esc(text)}</span>${pct != null ? `<span class="pct" data-no-i18n>${pct}%</span>` : ''}` : '';
    const auto = S.updAuto ?? u.auto, busy = running(), restarting = !!(S.restarting || u.restarting);
    const actions = [
      u.status === 'ready' && !restarting ? `<button class="btn small primary" type="button" data-act="update-restart" ${u.canRestart && !busy ? '' : 'disabled'}${busy ? ` title="${esc(ERR.busy)}"` : ''}>Restart now</button>` : '',
      u.status === 'available' ? `<a class="link" href="${esc(link)}" target="_blank" rel="noopener noreferrer">Download it</a>`
        : `<a class="link" href="${esc(link)}" target="_blank" rel="noopener noreferrer">Release notes</a>`,
      `<button class="link" type="button" data-act="update-check" ${['checking', 'downloading'].includes(u.status) || restarting ? 'disabled' : ''}>Check for updates</button>`,
      `<label class="toggle"><input type="checkbox" data-act="update-auto" ${auto ? 'checked' : ''}> Update automatically</label>`].join('');
    const sEl = $('#update-status'), aEl = $('#update-actions');
    if (sEl.dataset.html !== status) { sEl.innerHTML = status; sEl.dataset.html = status; }
    if (aEl.dataset.html !== actions) { aEl.innerHTML = actions; aEl.dataset.html = actions; }
    box.hidden = false;
  }

  function passed(big, small) {
    const el = $('#passed');
    el.innerHTML = `<div class="band"><div class="big">${esc(big)}</div><div class="small">${esc(small)}</div></div>`;
    el.hidden = false;
    clearTimeout(passed.t);
    passed.t = setTimeout(() => { el.hidden = true; }, 2600);
  }

  function renderStatus() {
    const st = S.state || {};
    const c = st.console;
    const net = st.network;
    const g = st.garlic;
    const sign = !g ? null : !g.signedIn ? ['wait', 'Not signed in to GarlicSaves'] : g.refused ? ['bad', 'GarlicSaves sign-in refused'] : ['ok', 'Signed in to GarlicSaves'];
    const html = [
      S.offline && !S.restarting ? '<span class="pill"><span class="dot bad"></span><b>Editor service not answering</b></span>' : '',
      c ? `<span class="pill"><span class="dot ${st.paired ? 'ok' : 'wait'}"></span><b>${esc(c.name)}</b>${st.paired ? 'paired' : 'not paired'}</span>` : '<span class="pill"><span class="dot"></span>No PS5 selected</span>',
      `<span class="pill"><span class="dot ${net ? (net.ok ? 'ok' : 'bad') : 'wait'}"></span>${net ? (net.ok ? 'Decryption service online' : 'Decryption service offline') : 'Checking the decryption service'}</span>`,
      sign ? `<span class="pill"><span class="dot ${sign[0]}"></span>${sign[1]}</span>` : ''
    ].join('');
    if (statusEl.dataset.html !== html) { statusEl.innerHTML = html; statusEl.dataset.html = html; }   // a live region: only real changes
  }

  function renderRoute() {
    const st = S.state;
    if (!st) return;
    const view = viewFor(st);
    const steps = stepsOf(st);
    const idx = steps.findIndex(x => x[0] === view);
    routeEl.innerHTML = steps.map(([id, name], i) => {
      const done = id === 'signin' ? !!(st.garlic?.signedIn && !st.garlic.refused)
        : i < idx || (id === 'pair' && st.paired) || (id === 'connect' && st.console) || (id === 'download' && st.hasSession);
      return `<button class="step ${id === view ? 'current' : done ? 'done' : ''}" data-act="go" data-view="${id}" ${available(id, st) && !running() ? '' : 'disabled'} aria-current="${id === view ? 'step' : 'false'}"><span class="n">${i + 1}</span>${name}</button>`;
    }).join('');
  }

  // ------------------------------------------------------------ main views
  function renderMain() {
    const st = S.state;
    const view = viewFor(st);
    const job = st.job || {};
    const s = slotOf(S.slot);
    const key = [view, st.console?.host, st.paired, st.hasSession, S.sig, st.readyToUpload,
      view === 'edit' ? [S.slot, S.tab, S.detail[S.slot] ? 1 : 0, S.stats[S.slot] ? 1 : 0, s?.modified, JSON.stringify(s?.applied || null)].join(',') : '',
      view === 'connect' ? [S.searching, JSON.stringify(S.consoles)].join(',') : '',
      view === 'send' ? [job.kind === 'upload' && job.stage === 'uploaded', (st.slots || []).map(x => x.modified).join(''),
        (st.users || []).map(u => u.id).join(' '), S.sendTo || ''].join(',') : '',
      ['signin', 'pair', 'download'].includes(view) ? signinKey(st) : ''].join('|');
    if (key === S.mainKey) return;
    const codeShown = !!main.querySelector('[data-signin-code]');
    S.mainKey = key;
    const scroll = window.scrollY;
    main.innerHTML = ({connect: viewConnect, signin: viewSignin, pair: viewPair, download: viewDownload, edit: viewEdit, send: viewSend})[view]();
    if (view === 'edit') { afterEdit(); window.scrollTo(0, scroll); }
    if (!codeShown && main.querySelector('[data-signin-code]')) main.querySelector('[data-signin-open]')?.focus();   // the code came: next, open GarlicSaves
  }

  // what the sign-in step (and the callouts on Pair and Download) show; the countdown is renderSigninLeft's
  const signinKey = st => {
    const g = st.garlic || {}, s = g.signin || {};
    return [g.signedIn, g.username, g.stored, g.devKey, g.refused, s.status, s.code, s.link, s.error, s.http, S.signinFor, st.console?.host, st.paired, st.hasSession].join(',');
  };

  const jobBox = kinds => `<div data-job="${kinds}"></div>`;

  function viewConnect() {
    const list = S.consoles;
    return `
      <section class="title-card"><span class="chip">Step 1</span><h1>Find your PS5</h1>
        <p>Turn the PS5 on and leave it on the home screen. It has to be on the same home network as this computer.</p></section>
      <div class="stack">
        <div class="row">
          <button class="btn primary" data-act="discover" ${S.searching ? 'disabled' : ''}>${S.searching ? 'Searching…' : 'Find my PS5'}</button>
          <form class="row" data-form="ip"><label class="note" for="ip">Or type its IP address</label>
            <input id="ip" class="ip" inputmode="decimal" autocomplete="off" placeholder="192.168.1.50">
            <button class="btn" type="submit">Use this address</button></form>
        </div>
        ${list ? (list.length ? `<div class="fields">${list.map(c => `
          <div class="field"><div class="name">${esc(c.name)}<span class="help">${esc(c.host)}, system software ${esc(fw(c.firmware))}</span></div>
          <div class="inputs"><button class="btn primary small" data-act="pick" data-host="${esc(c.host)}">Use this PS5</button></div></div>`).join('')}</div>`
          : '<div class="empty">No PS5 answered. Check it is on and on the same network, or type its IP address.</div>') : ''}
        ${jobBox('connect')}
      </div>
      <section class="caps" aria-labelledby="caps-h"><h2 id="caps-h">What you can change</h2>
        <p class="note">Story mode only. Every edit is made on a copy, checked against the value it replaces, and can be put back.</p>
        <dl>${CAPS.map(([name, what, risk]) => `<div><dt>${name}</dt><dd>${what}</dd><dd class="r">${riskTag(risk)}</dd></div>`).join('')}</dl>
      </section>`;
  }

  const CAPS = [
    ['Money', 'Bank account and Family Savings, up to what the game can hold.', 'tested'],
    ['Ammo', 'Refill or set the ammo for every weapon Lucia and Jason carry. Adding guns they don’t have yet is experimental.', 'tested'],
    ['Stats', 'Fitness, overpowers and buffs, time played, distances, earnings, wanted levels and trophy counters, with the game’s own labels.', 'tested'],
    ['Completion', 'Complete lines of the 100% checklist: robberies, fencing, collectibles, races and activities, stunts, challenges, hoops and the compendium. The new percentage shows before you save. Partly tested on PS5.', 'caution'],
    ['World', 'Time of day, health, armour and the map, plus Lucia’s and Jason’s skills, special meter, criminal profile and relationship.', 'caution'],
    ['All stats and Save data', 'Every one of the save’s values, with names or descriptions for almost all of them. For experts.', 'danger']];

  const fw = f => /^[0-9a-f]{8}$/i.test(f || '') ? `${Number(f.slice(0, 2))}.${f.slice(2, 4)}` : (f || 'unknown');

  // ---- signing in to GarlicSaves (state.garlic): the code to enter on GarlicSaves, the wait, the result
  function viewSignin() {
    const st = S.state, g = st.garlic || {}, s = g.signin || {};
    const chip = `<span class="chip">Step ${stepNo('signin', st)}</span>`;
    const busy = s.status === 'starting' || s.status === 'waiting';
    const err = s.status === 'error' ? `<div class="callout danger" role="alert">${esc(signinError(s))}</div>` : '';
    if (g.signedIn && !busy) {
      return `
      <section class="title-card">${chip}<h1>Signed in to GarlicSaves</h1>
        ${g.username ? `<p>GarlicSaves account: <strong data-no-i18n>${esc(g.username)}</strong></p>` : ''}
        <p>Save Garage needs your sign-in to pair, download, save edits and send saves back.</p></section>
      <div class="stack">
        ${g.refused ? '<div class="callout danger" role="alert">GarlicSaves refused this sign-in. It may have been turned off, or it may have expired. Sign in again to go on.</div>' : ''}
        ${err}
        <div class="row">${g.refused ? '<button class="btn primary" data-act="signin">Sign in again</button>' : '<button class="btn primary" data-act="signin-done">Continue</button>'}
          ${g.stored ? `<button class="btn" data-act="signout" ${running() ? 'disabled' : ''}>Sign out</button>` : ''}</div>
        ${g.stored ? '<p class="note">Signing out only forgets the key on this computer.</p>' : ''}
        ${jobBox('signin')}
      </div>`;
    }
    const link = webLink(s.link);
    const waiting = s.status === 'waiting' && s.code ? `
        <div class="panel signin-code" data-signin-code>
          <div class="lbl">Enter this code on GarlicSaves</div>
          <div class="code" data-no-i18n>${esc(s.code)}</div>
          ${link ? `<a class="btn primary" data-signin-open href="${esc(link)}" target="_blank" rel="noopener noreferrer">Open GarlicSaves</a>
          <p class="note">To use another device, open this address there: <span class="addr" data-no-i18n>${esc(link)}</span></p>` : ''}
        </div>` : '';
    return `
      <section class="title-card">${chip}<h1>Sign in to GarlicSaves</h1>
        <p>Save Garage decrypts and encrypts saves through GarlicSaves, which now asks each app that uses it to sign in with your own GarlicSaves account. You do this once on this computer.</p></section>
      <div class="stack">
        ${S.signinFor && !busy ? `<div class="callout">${esc(ERR.not_signed_in)}</div>` : ''}
        ${err}
        ${busy ? `${waiting}
        <div class="job" role="status"><div class="stage">${s.status === 'waiting' ? 'Waiting for you to approve the sign-in on GarlicSaves' : 'Asking GarlicSaves for a sign-in code…'}</div>
          ${s.status === 'waiting' ? '<div class="detail" data-signin-left></div>' : ''}
          <div class="bar"><span></span></div>
          <div class="row" style="margin-top:10px"><button class="link" data-act="signin-cancel">Cancel</button></div></div>` : `
        <ol class="how">
          <li><strong>Click Sign in to GarlicSaves below.</strong><span class="path">Save Garage asks GarlicSaves for a code.</span></li>
          <li><strong>Open the GarlicSaves page, sign in and enter the code.</strong><span class="path">You can open it on this computer or on your phone.</span></li>
          <li><strong>Come back here.</strong><span class="path">Save Garage carries on by itself once you have approved the sign-in.</span></li>
        </ol>
        <div class="row"><button class="btn primary" data-act="signin">Sign in to GarlicSaves</button></div>`}
        <p class="note">GarlicSaves gives Save Garage on this computer a key of its own. Save Garage keeps it in its data folder, readable only by you, and sends it only to GarlicSaves. It never appears on this page.</p>
        ${jobBox('signin')}
      </div>`;
  }

  // the minutes left to enter the code, updated in place (the page polls every second)
  function renderSigninLeft() {
    const el = $('[data-signin-left]'), s = S.state?.garlic?.signin;
    if (!el || !s) return;
    const t = s.expiresIn != null ? `The code expires in ${Math.max(1, Math.ceil(s.expiresIn / 60))} min.` : '';
    if (el.dataset.en !== t) { el.textContent = t; el.dataset.en = t; }
  }

  // on a step whose task goes through GarlicSaves, while not signed in: why, and the way to sign in
  const signinFirst = back => mustSignIn(S.state)
    ? `<div class="callout signin-first"><span>${esc(ERR.not_signed_in)}</span><button class="btn small primary" data-act="signin" data-back="${back}">Sign in to GarlicSaves</button></div>` : '';

  function viewPair() {
    return `
      <section class="title-card"><span class="chip">Step ${stepNo('pair', S.state)}</span><h1>Pair your PS5</h1>
        <p>You only do this once for each PS5. Pairing waits up to 5 minutes for you.</p></section>
      <div class="stack">
        ${signinFirst('pair')}
        <ol class="how">
          <li><strong>Click Start pairing below.</strong></li>
          <li><strong>On the PS5, open Data Transfer.</strong><span class="path">${PS5_TRANSFER}.</span></li>
          <li><strong>Pick “Save Garage Pairing” from the list.</strong><span class="path">The PS5 then says it can’t transfer data. That’s expected: the pairing has already happened.</span></li>
        </ol>
        <div class="row"><button class="btn primary" data-act="pair" ${running() ? 'disabled' : ''}>Start pairing</button></div>
        ${jobBox('pair')}
      </div>`;
  }

  function viewDownload() {
    const again = S.state.hasSession;
    return `
      <section class="title-card"><span class="chip">Step ${stepNo('download', S.state)}</span><h1>Download your save</h1>
        <p>The PS5 restarts into transfer mode during the download and restarts again when it’s done.</p></section>
      <div class="stack">
        ${signinFirst('download')}
        ${again ? '<div class="callout">You already have a save downloaded. Downloading again replaces it here, and edits you haven’t sent are lost.</div>' : ''}
        <ol class="how">
          <li><strong>In GTA VI, save your game, then go back to the PS5 home screen.</strong></li>
          <li><strong>Click Download save.</strong></li>
          <li><strong>When this page asks, hold the PS5 power button for about one second, then let go. It beeps after you let go.</strong></li>
        </ol>
        <div class="row"><button class="btn primary" data-act="download" ${running() ? 'disabled' : ''}>Download save</button></div>
        ${jobBox('download')}
      </div>`;
  }

  // the save's 100% figure, from the Completion tab's checklist when it's loaded, else from the stats
  function overallOf(s) {
    const c = S.comp[s.file]?.checklist?.overall;
    if (c) return c.stored ?? c.computed;
    const f = (S.detail[s.file]?.featured || []).find(x => x.id === 'overall_pct');
    const v = f?.entries?.[0]?.value;
    return typeof v === 'number' ? v : null;
  }

  // the figure after the edits picked so far, once the app has worked it out
  function afterOf(s) {
    const P = S.preview[s.file], d = S.drafts[s.file];
    if (!P?.data?.ok || P.busy || !d || (!Object.keys(d.completion || {}).length && !Object.keys(d.stats || {}).length && !gunCount(d.guns))) return null;
    return P.data.overall.computed;
  }

  function sortedSlots(st) {
    return [...(st.slots || [])].sort((a, b) => (b.file === 'sdimg_sce_sdmemory') - (a.file === 'sdimg_sce_sdmemory') || b.file.localeCompare(a.file));
  }

  function moneySummary(s) {
    const get = k => (s.items || []).filter(x => x.kind === k).reduce((a, x) => a + x.value, 0);
    const parts = [['bank', 'Bank'], ['savings', 'Family Savings'], ['cash', 'Cash']].filter(([k]) => (s.items || []).some(x => x.kind === k))
      .map(([k, n]) => `${n} <span class="cash">$${nf.format(get(k))}</span>`);
    return parts.join(', ');
  }

  function viewEdit() {
    const st = S.state;
    const s = slotOf(S.slot);
    if (!s) return '<div class="empty">No story saves were found in this download.</div>';
    const tabs = [['money', 'Money'], ['ammo', 'Ammo'], ['stats', 'Stats'], ['completion', 'Completion'], ['world', 'World'], ['all', 'All stats'], ['data', 'Save data'], ['trophies', 'Trophies']];
    return `
      <section class="title-card"><span class="chip">${label(s)}</span><h1 data-no-i18n>${esc(missionName(s))}</h1>
        ${st.user?.name ? `<p>PS5 account: <strong>${esc(st.user.name)}</strong></p>` : ''}
        <p>${moneySummary(s) || 'No money balances in this save'}.${overallOf(s) != null ? ` 100% completion: <strong>${nf2.format(overallOf(s))}%</strong>${afterOf(s) != null ? `, <strong class="gold">${nf2.format(afterOf(s))}%</strong> after your edits` : ''}.` : ''}${s.file === 'sdimg_sce_sdmemory' ? ' Continue in the game loads this save.' : ''}${s.modified ? ' This save has edits waiting to be sent.' : ''}</p></section>
      <div class="saves" role="group" aria-label="Choose a save">${sortedSlots(st).map(x => `
        <button class="save" data-act="slot" data-file="${esc(x.file)}" aria-pressed="${x.file === s.file}">
          <span class="k">${label(x)}</span><span class="t" data-no-i18n>${esc(missionName(x))}</span>${x.modified ? '<span class="m">Edited</span>' : ''}</button>`).join('')}</div>
      ${(st.skipped || []).length ? `<div class="callout skipped"><div>Save Garage couldn’t read these saves, so they can’t be edited this time. They stay on the PS5 as they are, and you can edit the other saves as usual. Downloading again later may help.<ul class="skipped-list">${st.skipped.map(x => `
        <li><span>${label(x)}</span>: <span data-no-i18n>${esc(skippedName(x))}</span></li>`).join('')}</ul></div></div>` : ''}
      <div class="editor">
        <div class="tabs" role="tablist" aria-label="What to edit">${tabs.map(([id, name]) => `
          <button role="tab" aria-selected="${S.tab === id}" data-act="tab" data-tab="${id}">${name}<span class="count" data-count="${id}"></span></button>`).join('')}</div>
        <section role="tabpanel" id="panel">${panel(s)}</section>
      </div>`;
  }

  function panel(s) {
    if (S.tab === 'trophies') return panelTrophies();
    if (S.tab === 'money') return panelMoney(s);
    const d = S.detail[s.file];
    if (!d) return '<div class="empty">Reading this save…</div>';
    if (d.failed) return `<div class="callout danger">${esc(ERR[d.failed] || ERR.internal)} <button class="btn small" data-act="reload">Try again</button></div>`;
    if (S.tab === 'all' && S.stats[s.file]?.failed) return `<div class="callout danger">${esc(ERR[S.stats[s.file].failed] || ERR.internal)} <button class="btn small" data-act="reload">Try again</button></div>`;
    if (S.tab === 'ammo') return panelAmmo(s, d);
    if (S.tab === 'stats') return panelStats(s, d);
    if (S.tab === 'data') return S.sd[s.file]?.failed ? `<div class="callout danger">${esc(ERR[S.sd[s.file].failed] || ERR.internal)} <button class="btn small" data-act="reload">Try again</button></div>`
      : S.sd[s.file] ? panelData(s) : '<div class="empty">Reading this save…</div>';
    if (S.tab === 'world') return S.world[s.file]?.failed ? `<div class="callout danger">${esc(ERR[S.world[s.file].failed] || ERR.internal)} <button class="btn small" data-act="reload">Try again</button></div>`
      : S.world[s.file] ? panelWorld(s) : '<div class="empty">Reading this save…</div>';
    if (S.tab === 'completion') return S.comp[s.file]?.failed ? `<div class="callout danger">${esc(ERR[S.comp[s.file].failed] || ERR.internal)} <button class="btn small" data-act="reload">Try again</button></div>`
      : S.comp[s.file] ? panelCompletion(s) : '<div class="empty">Reading this save…</div>';
    if (S.tab === 'all') return S.stats[s.file] ? panelAll(s) : '<div class="empty">Loading every stat in this save…</div>';
    return '';
  }

  const riskTag = r => ({tested: '<span class="risk tested">Tested on PS5</span>', caution: '<span class="risk caution">Not tested yet</span>',
                         danger: '<span class="risk danger">Can break your save</span>', untested: '<span class="risk caution">Not tested on a PS5 yet</span>',
                         experimental: '<span class="risk caution">Experimental, not tested on a PS5 yet</span>',
                         stacks: '<span class="risk caution">May not be spendable</span>'})[r] || '';

  // ---- drafts: what the user wants each save to look like, always relative to the original save
  function seedDraft(s) {
    if (S.drafts[s.file]) return;
    const d = {money: {}, ammo: {}, stats: {}, world: {}, raw: {}, completion: {}, guns: {}, stacksOn: {}};
    const a = s.applied || {};
    if (a.world) d.world = JSON.parse(JSON.stringify(a.world));
    if (a.completion) d.completion = JSON.parse(JSON.stringify(a.completion));
    if (a.guns) d.guns = JSON.parse(JSON.stringify(a.guns));
    for (const c of a.raw || []) d.raw[rawKey(c.section, c.path)] = c;
    for (const c of a.money || []) {
      d.money[`${c.inv}:${c.idx}`] = c;
      if (c.stacks) d.stacksOn[`${c.inv}:${c.idx}`] = true;       // saved with the bank's extra stacks: the box stays ticked
    }
    for (const c of a.ammo || []) d.ammo[`${c.inv}:${c.idx}`] = c;
    for (const c of a.stats || []) d.stats[`${c.group}:${c.row}`] = c;
    S.drafts[s.file] = d;
  }

  const rawKey = (sec, path) => sec + ':' + JSON.stringify(path);
  const draftOf = file => S.drafts[file] || (S.drafts[file] = {money: {}, ammo: {}, stats: {}, world: {}, raw: {}, completion: {}, guns: {}, stacksOn: {}});
  // the bank's experimental extra stacks, ticked for this bank field ("inv:idx"); its changes then carry stacks: true
  const stacksOn = (file, key) => !!draftOf(file).stacksOn?.[key];
  const draftList = d => ({money: Object.values(d.money), ammo: Object.values(d.ammo), stats: Object.values(d.stats), world: {...(d.world || {})},
                           raw: Object.values(d.raw || {}), completion: JSON.parse(JSON.stringify(d.completion || {})), guns: JSON.parse(JSON.stringify(d.guns || {}))});
  const compCount = c => ['compendium', 'discovery', 'challenges', 'gyms', 'activities', 'robberies', 'fencing', 'activities2', 'hoops', 'vehicles', 'collectibles', 'cheats'].filter(k => c && c[k]).length;
  // World edits: each key is one change, except a character's object ({meter, skills, profile, vest}), where each counts,
  // and the levels and capacities ({lucia: {muscle, cardio, focus}, jason: {...}}), where each value counts
  const worldCount = w => Object.entries(w || {}).reduce((n, [k, v]) => n + (k === 'lucia' || k === 'jason' ? Object.keys(v || {}).length
    : k === 'levels' || k === 'growth' ? Object.values(v || {}).reduce((m, c) => m + Object.keys(c || {}).length, 0) : 1), 0);
  // guns to add: {lucia: [weapon ids], jason: [...]}, each gun one change
  const gunCount = g => Object.values(g || {}).reduce((n, v) => n + (v || []).length, 0);
  const editCount = d => Object.keys(d.money).length + Object.keys(d.ammo).length + Object.keys(d.stats).length + worldCount(d.world)
                         + Object.keys(d.raw || {}).length + compCount(d.completion) + gunCount(d.guns);
  const stable = v => v && typeof v === 'object' && !Array.isArray(v) ? `{${Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + stable(v[k])).join(',')}}` : JSON.stringify(v);
  const worldKey = w => stable(w || {});
  const gunsKey = g => stable(Object.fromEntries(Object.entries(g || {}).filter(([, v]) => (v || []).length).map(([k, v]) => [k, [...v].sort()])));
  const norm = e => JSON.stringify(['money', 'ammo', 'stats'].map(k => (e?.[k] || []).map(c => [c.inv, c.idx, c.group, c.row, c.newValue]).sort())) + worldKey(e?.world)
    + JSON.stringify((e?.raw || []).map(c => [rawKey(c.section, c.path), c.newValue]).sort()) + worldKey(e?.completion) + gunsKey(e?.guns);
  const dirty = s => norm(draftList(draftOf(s.file))) !== norm(s.applied);

  // a numeric input cell. kind: money|ammo|stat; init = value shown in the field
  function cell(o) {
    const {kind, key, label, value, display, unit, type, step, max, attrs = '', wide, narrow, money, extra = ''} = o;
    const wasText = ['money', 'count'].includes(unit) && Number.isInteger(value) ? nf.format(value) : display;
    const dr = draftOf(S.slot)[kind === 'stat' ? 'stats' : kind][key];
    const shown = dr ? toDisplay(dr.newValue, unit) : display;
    const changed = dr && true;
    if (type === 'bool') {
      const on = dr ? !!dr.newValue : !!value;
      return `<div class="cell ${changed ? 'changed' : ''}"><span class="lbl">${esc(label)}</span>
        <label class="toggle"><input type="checkbox" data-edit="${kind}" data-key="${esc(key)}" data-unit="flag" data-type="bool" data-orig="${value ? 1 : 0}" ${attrs} ${on ? 'checked' : ''}> ${on ? 'Yes' : 'No'}</label>
        <span class="was">${changed ? 'was ' + (value ? 'yes' : 'no') : ''}</span></div>`;
    }
    const id = 'f' + Math.random().toString(36).slice(2, 9);
    return `<div class="cell ${wide ? 'wide' : ''} ${narrow ? 'narrow' : ''} ${money ? 'money' : ''} ${changed ? 'changed' : ''}"><label for="${id}">${esc(label)}</label>
      <span class="with-unit"><input id="${id}" type="number" min="${o.min ?? 0}" ${max != null ? `max="${max}"` : ''} step="${step || 1}" value="${esc(shown)}"
        data-edit="${kind}" data-key="${esc(key)}" data-unit="${unit}" data-type="${type}" data-init="${esc(display)}" data-was="${esc(wasText)}" data-orig="${esc(JSON.stringify(value))}" ${attrs}>
        ${extra}</span>
      <span class="was">${changed ? 'was ' + esc(wasText) : ''}</span></div>`;
  }

  function toDisplay(raw, unit) {
    if (unit === 'ms') return (raw / 3600000).toFixed(2);
    if (unit === 'distance') return (raw / 1000).toFixed(2);
    if (unit === 'percent') return Number(raw).toFixed(2);
    if (unit === 'raw-float') return String(Number(raw));
    return String(raw);
  }

  function fromDisplay(str, unit, type) {
    const v = Number(str);
    if (str === '' || !Number.isFinite(v)) return null;
    if (unit === 'ms') return Math.round(v * 3600000);
    if (unit === 'distance') return v * 1000;
    if (type === 'float') return v;
    return Number.isInteger(v) ? v : null;
  }

  // ---- money
  // The bank goes up to what its own money boxes hold (max), which shops spend from. Past them it can take extra $85,000
  // stacks (maxStacks), but only when the user ticks the experimental option: a player couldn't spend them (issue #8),
  // and with thousands of them the game nearly froze whenever it paid (issue #21), so at most stackCap count.
  function panelMoney(s) {
    const items = (s.items || []).filter(x => x.kind !== 'other');
    const name = x => ({bank: 'Bank account', savings: 'Family Savings', cash: 'Cash, ' + (x.inv === 0 ? 'Lucia' : 'Jason')})[x.kind];
    // a bank already past its own boxes (versions 1.26 to 1.30 put the rest in extra stacks); stuck money has its own fix
    const over = x => x.kind === 'bank' && !(x.stuck > 0) && x.value > x.max;
    const help = x => ({bank: x.stuck > 0
                          ? `BuckMe shows $${nf.format(x.value)}, but $${nf.format(x.stuck)} of it sits in Family Savings boxes that an older version of Save Garage put under the bank, and the game can’t spend it. Moving it puts as much as fits, up to $${nf.format(x.max)}, in the bank’s own money boxes.`
                          : over(x)
                          ? `$${nf.format(x.value - x.max)} of the $${nf.format(x.value)} in the bank sits in extra stacks the game may not let you spend. Setting the bank to $${nf.format(x.max)} or less keeps everything spendable.`
                            + (x.stacks > (x.stackCap ?? 100) ? ' This many stacks can make the game nearly freeze when it pays.' : '')
                          : `Up to $${nf.format(x.max)}: what the bank’s own money boxes hold at this point in the story. Shops can spend all of it. The limit grows as the story goes on.`,
                        savings: `Up to $${nf.format(x.max)}.`, cash: `Up to $${nf.format(x.max)}, the size of the wallet.`})[x.kind];
    const stacksOpt = (x, key, on) => `<div class="stacks-opt">
        <div class="row"><label class="toggle small"><input type="checkbox" data-stacks="${key}" data-max="${x.max}" data-max-stacks="${x.maxStacks}" ${on ? 'checked' : ''}> Allow more than $${nf.format(x.max)} (experimental)</label>${riskTag('stacks')}</div>
        <span class="help">Up to $${nf.format(x.maxStacks)}. Amounts above $${nf.format(x.max)} go into extra stacks the game may not let you spend: a player couldn’t make a phone payment with them. Save Garage adds at most ${nf.format(x.stackCap ?? 100)} stacks: with thousands of them, the game nearly froze whenever it paid. Use it only if you’re fine with that.</span></div>`;
    return `
      <div class="group"><div class="section-head"><h2>Money</h2>${riskTag('tested')}
        <p>Balances of 0 aren’t stored in the save, so they don’t show here. Get a little money in the game, save, and download again to edit them.</p></div>
      ${items.length ? `<div class="fields">${items.map(x => {
        const key = `${x.inv}:${x.idx}`, exp = x.kind === 'bank' && x.maxStacks > x.max, on = exp && stacksOn(s.file, key), lim = on ? x.maxStacks : x.max;
        return `
        <div class="field"><div class="name">${esc(name(x))}<span class="help${over(x) ? ' warn' : ''}">${esc(help(x))}</span></div>
          <div class="inputs">${cell({kind: 'money', key, label: 'Amount in dollars', value: x.value, display: String(x.value), unit: 'money', type: 'int', max: lim, wide: true, money: true,
            attrs: `data-inv="${x.inv}" data-idx="${x.idx}" data-label="${esc(name(x))}"`, extra: `<button class="btn small" data-act="fill" data-to="${lim}">Max</button>`
              + (x.stuck > 0 ? ` <button class="btn small primary" data-act="unstick" data-inv="${x.inv}" data-idx="${x.idx}" data-value="${x.value}" data-to="${Math.min(x.value, x.max)}">Make it spendable</button>` : '')
              + (over(x) ? ` <button class="btn small primary" data-act="unstack" data-to="${x.max}">Make it spendable</button>` : '')})}
          ${exp ? stacksOpt(x, key, on) : ''}</div></div>`;
      }).join('')}</div>`
        : '<div class="empty">This save has no money balances to edit.</div>'}</div>`;
  }

  // ticking the bank's extra stacks raises its field and Max to maxStacks, and its change asks for stacks; unticking
  // brings an amount typed above the boxes back down to them
  function onStacks(el) {
    const s = slotOf(S.slot);
    if (!s) return;
    const d = draftOf(s.file), key = el.dataset.stacks, field = el.closest('.field');
    d.stacksOn ??= {};
    if (el.checked) d.stacksOn[key] = true; else delete d.stacksOn[key];
    const input = field?.querySelector('input[data-edit="money"]'), fill = field?.querySelector('[data-act="fill"]');
    const lim = el.checked ? el.dataset.maxStacks : el.dataset.max;
    if (fill) fill.dataset.to = lim;
    if (!input) return;
    input.max = lim;
    const v = fromDisplay(input.value, 'money', 'int');
    if (!el.checked && input.value.trim() !== input.dataset.init && v != null && v > +el.dataset.max) input.value = el.dataset.max;
    onEdit(input);
  }

  // ---- ammo
  function panelAmmo(s, d) {
    const by = inv => d.ammo.filter(a => a.inv === inv);
    const block = (inv, who) => {
      const rows = by(inv);
      if (!rows.length) return '';
      const carried = (d.weapons || []).filter(w => w.inv === inv), unnamed = carried.filter(w => !w.label).length;
      const guns = carried.filter(w => w.label).map(w => `<li>${esc(w.label)}${w.kind ? ` <span class="kind">${esc(w.kind)}</span>` : ''}</li>`).join('')
        + (unnamed ? `<li class="kind">${unnamed} more not identified yet</li>` : '');
      return `<div class="group"><div class="section-head"><h3>${who}</h3><div class="head-actions"><button class="btn small" data-act="fillall" data-scope="ammo-${inv}">Refill all</button></div></div>
        ${guns ? `<p class="note">Weapons carried</p><ul class="weapons">${guns}</ul>` : ''}
        <div class="fields">${rows.map(a => {
          const help = a.full ? `A full load is ${nf.format(a.full)}.` : `Can go up to ${nf.format(a.max)}. The game’s full load for this isn’t known yet.`;
          return `<div class="field"><div class="name">${esc(a.label)}<span class="help">${help}</span></div>
            <div class="inputs" data-scope="ammo-${inv}">${cell({kind: 'ammo', key: `${a.inv}:${a.idx}`, label: a.type.startsWith('thrown') ? 'How many' : 'Rounds', value: a.value, display: String(a.value), unit: 'count', type: 'int', min: 1, max: a.max,
              attrs: `data-inv="${a.inv}" data-idx="${a.idx}" data-label="${esc(a.label + ', ' + who)}" data-full="${a.full || ''}" data-max="${a.max}"`,
              extra: a.full ? `<button class="btn small" data-act="fill" data-to="${a.full}">Full</button>` : `<button class="btn small" data-act="fill" data-to="${a.max}">Max</button>`})}</div></div>`;
        }).join('')}</div></div>`;
    };
    return `<div class="section-head"><h2>Ammo</h2>${riskTag('tested')}
        <p>Only ammo a character is carrying is listed. To add a new type, pick some up in the game first. Tested on a PS5: the game keeps up to a full load and cuts larger amounts back to it.</p></div>
      ${d.ammo.length ? block(0, 'Lucia') + block(1, 'Jason') : '<div class="empty">Neither character is carrying ammo in this save.</div>'}
      ${gunsSection(s, d)}`;
  }

  // ---- guns: add the guns a character doesn't have yet, built as the game builds a gun you buy (guns.py)
  const gunItem = (who, g, on) => `<li class="${on ? 'on' : ''}"><label><input type="checkbox" data-gun="${who}" data-id="${esc(g.id)}" ${on ? 'checked' : ''}>
    <span>${esc(g.label)}${g.kind ? ` <span class="kind">${esc(g.kind)}</span>` : ''}${g.ammo ? ` <span class="kind">×${nf.format(g.ammo)}</span>` : ''}</span></label></li>`;
  const gunSum = (c, picked) => {
    const slots = c.offered.filter(g => picked.has(g.id)).reduce((a, g) => a + g.rows, 0);
    return picked.size ? `${picked.size} picked, using ${nf.format(slots)} of the ${nf.format(c.itemsFree)} free inventory slots.` : 'None picked yet.';
  };
  function gunsSection(s, d) {
    const G = d.guns, picks = draftOf(s.file).guns || {};
    const known = (G?.characters || []).flatMap(c => [...c.offered, ...c.owned]);
    const amount = kind => known.find(g => g.name === `weaponspec_thrown_${kind}_default`)?.ammo;
    const amounts = [amount('grenade'), amount('bomb')].filter(x => x != null);
    const head = `<div class="group guns"><div class="section-head"><h2>Guns</h2>${riskTag('tested')}
        <p>Adds guns a character doesn’t have yet, each with the kit and default parts the game gives a gun you buy. Tested on a PS5: they show up in the loadout, as guns you buy do. Only guns whose parts Save Garage has seen the game write are offered, and nothing a character already has is changed. Each gun takes a few inventory slots, and ${nf.format(G?.itemReserve ?? 300)} are always left free.</p>
        <p>Guns come without ammo: buy some in the game, or pick some up, and refill it here next time.${amounts.length === 2 ? ` Grenades and sticky bombs come with ${nf.format(amounts[0])} and ${nf.format(amounts[1])}, as many as the game gave when they were bought.` : ''} A gun the compendium doesn’t list yet is added to it too, as the game does, which can raise STANDARD ISSUE WEAPONS and the 100% figure.</p></div>`;
    if (!G) return head + '<div class="callout">This part of the save can’t be read yet.</div></div>';
    const rows = G.characters.map(c => {
      const picked = new Set(picks[c.key] || []);
      let help, ctl = '';
      if (c.problem) help = esc(ERR['save_' + c.problem] || ERR.save_layout_changed);
      else if (!c.offered.length) help = c.owned.length ? `Already has all ${nf.format(c.owned.length)} guns Save Garage can add.` : 'No guns can be added to this character.';
      else {
        help = `${c.offered.length === 1 ? '1 gun can be added.' : `${nf.format(c.offered.length)} guns can be added.`} <span data-gun-sum="${c.key}">${gunSum(c, picked)}</span>`;
        ctl = `<ul class="weapons guns">${c.offered.map(g => gunItem(c.key, g, picked.has(g.id))).join('')}</ul>
          <div class="row"><button class="btn small" data-act="guns-all" data-who="${c.key}" ${picked.size === c.offered.length ? 'disabled' : ''}>Pick all</button>
            <button class="btn small" data-act="guns-none" data-who="${c.key}" ${picked.size ? '' : 'disabled'}>Clear</button></div>`;
      }
      if (c.left?.length) help += ` ${c.left.length === 1 ? '1 is' : `${nf.format(c.left.length)} are`} left alone: the character has its ammo without the weapon, which no save has shown.`;
      return `<div class="field gunfield"><div class="name">${esc(c.name)}<span class="help">${help}</span></div><div class="inputs">${ctl}</div></div>`;
    }).join('');
    const offered = new Set(known.map(g => g.id));       // a gun one character can't be given but the other can isn't listed
    const no = [...new Map(Object.values(G.notOffered || {}).flat().filter(g => !offered.has(g.id)).map(g => [g.id, g])).values()];
    const left = no.length ? `<p class="note">Can’t be added yet, because no game save shows their default parts:</p>
      <ul class="weapons">${no.map(g => `<li>${esc(g.label)}${g.kind ? ` <span class="kind">${esc(g.kind)}</span>` : ''}</li>`).join('')}</ul>` : '';
    return head + `<div class="fields">${rows}</div>${left}</div>`;
  }

  function onGun(el) {
    const s = slotOf(S.slot);
    if (!s) return;
    const d = draftOf(s.file), who = el.dataset.gun, cur = new Set(d.guns[who] || []);
    if (el.checked) cur.add(el.dataset.id); else cur.delete(el.dataset.id);
    if (cur.size) d.guns[who] = [...cur]; else delete d.guns[who];
    el.closest('li')?.classList.toggle('on', el.checked);
    const c = S.detail[s.file]?.guns?.characters?.find(x => x.key === who), sum = $(`[data-gun-sum="${who}"]`);
    if (c && sum) sum.textContent = gunSum(c, cur);
    const all = $(`[data-act="guns-all"][data-who="${who}"]`), none = $(`[data-act="guns-none"][data-who="${who}"]`);
    if (all && c) all.disabled = cur.size === c.offered.length;
    if (none) none.disabled = !cur.size;
    renderPending(); renderCounts();
  }

  // ---- featured stats
  function panelStats(s, d) {
    const unitOf = f => ({percent: ['percent', 'float', 0.01, '%'], ms: ['ms', null, 0.01, 'hours'], distance: ['distance', 'float', 0.01, 'km'],
                          money: ['count', null, 1, '$'], count: ['count', null, 1, ''], level: ['count', null, 1, ''], flag: ['flag', 'bool', 1, '']})[f.unit] || ['count', null, 1, ''];
    const rows = f => {
      const [unit, forced, step, unitLabel] = unitOf(f);
      const allSame = list => list.every(x => x.risk === f.risk);
      const own = f.risk === 'danger' && f.category !== 'trophies' ? riskTag('danger') : f.risk === 'tested' && !allSame(d.featured.filter(x => x.category === f.category)) ? riskTag('tested') : '';
      const limit = maxText(f);
      return `<div class="field"><div class="name">${esc(f.label)} ${own}<span class="help">${esc(f.help)}${limit ? ' ' + esc(limit) : ''}</span></div>
        <div class="inputs" data-spec="${esc(f.id)}">${f.entries.filter(e => !(f.autoTotal && e.owner === 0)).map(e => {
          const type = forced || e.type;
          return cell({kind: 'stat', key: `${e.group}:${e.row}`, narrow: true, label: OWNER[e.owner] + (unitLabel ? `, ${unitLabel}` : ''),
            value: e.value, display: type === 'bool' ? '' : toDisplay(e.value, unit), unit, type: type === 'bool' ? 'bool' : (e.type === 'float' ? 'float' : 'int'),
            step: e.type === 'float' || unit === 'ms' ? step : 1, max: e.type === 'bool' || f.max == null ? null : maxShown(f),
            attrs: `data-group="${esc(e.group)}" data-row="${e.row}" data-base="${e.base}" data-qual="${e.qual}" data-owner="${e.owner}" data-label="${esc(f.label + ' (' + OWNER[e.owner] + ')')}"`});
        }).join('')}${f.autoTotal ? (() => { const t = f.entries.find(e => e.owner === 0); return `<div class="cell auto narrow"><span class="lbl">Total, updates itself</span>
          <span class="with-unit"><input type="number" disabled value="${esc(toDisplay(t.value, unit))}" data-total="${esc(f.id)}" data-orig="${t.value}"></span><span class="was"></span></div>`; })() : ''}
        </div></div>`;
    };
    const cats = CATS.map(([id, name, help]) => {
      const list = d.featured.filter(f => f.category === id);
      if (!list.length) return '';
      const worst = list.every(f => f.risk === 'danger') ? 'danger' : list.every(f => f.risk === 'tested') ? 'tested' : 'caution';
      return `<div class="group"><div class="section-head"><h2>${name}</h2>${riskTag(worst)}<p>${esc(help)}</p></div><div class="fields">${list.map(rows).join('')}</div></div>`;
    }).join('');
    return `<div class="callout" style="margin-bottom:24px">Almost every stat here has been tested on a PS5: the game showed the edited values on its stats screens, kept them when it saved, and went on counting from them. Labels follow the game’s own stats screens. The times, distances, story and styles percentages and two gadget flags haven’t been tried yet: change a few, send the save, and check it loads before changing more.</div>${cats}`;
  }

  // ---- all stats browser
  function statIndex(file) {
    const t = S.stats[file];
    if (t.index) return t.index;
    const n = t.names;
    const ql = n.qual_labels || {}, ol = n.owner_labels || {};
    const bn = i => n.base[i] || `#${i}`, qn = i => (i === 0 ? '' : (n.qual[i] || (ql[i] ? (ql[i] === ql[i].toUpperCase() ? ql[i].toLowerCase() : ql[i]) : `#${i}`))), on = i => ol[i] || n.owner[i] || `#${i}`;
    // keys whose real name is unknown but whose meaning was worked out from the saves: shown as a description, marked
    const bm = n.base_meanings || {}, mq = new Set((n.meaning || {}).qual || []), mo = new Set((n.meaning || {}).owner || []);
    const labels = t.labels || {}, means = t.means || {};
    const pretty = l => l ? (l.charAt(0) + l.slice(1).toLowerCase()).replace(/\b(lucia|jason)\b/g, w => w[0].toUpperCase() + w.slice(1)) : '';
    const prot = new Set((t.protected[MONEY_GROUP] || []).map(String));
    const rows = [];
    for (const g of t.groups) {
      const vary = new Set(g.varies);
      for (let r = 0; r < g.value.length; r++) {
        const b = g.base[r], q = g.qual[r], desc = !n.base[b] && bm[b];
        const name = desc ? bm[b] + (qn(q) ? ` (${qn(q)})` : '') : bn(b) + (qn(q) ? '.' + qn(q) : '');
        const meaning = !!desc || (!n.qual[q] && mq.has(q)) || mo.has(g.owner[r]);
        const game = pretty(labels[`${g.key}:${r}`]);
        rows.push({g: g.key, type: g.type, r, b: g.base[r], q: g.qual[r], o: g.owner[r], v: g.value[r], vary: vary.has(r),
          named: !!(n.base[b] || n.qual[q] || game || desc), meaning, game, name, means: means[`${g.key}:${r}`], owner: on(g.owner[r]), qlab: n.qual[g.qual[r]] ? ql[g.qual[r]] || '' : '',
          locked: g.key === MONEY_GROUP && prot.has(String(g.base[r])), text: (game + ' ' + name + ' ' + (ql[g.qual[r]] || '') + ' ' + on(g.owner[r]) + ' ' + (n.owner[g.owner[r]] || '') + ' ' + (means[`${g.key}:${r}`]?.text || '') + ` #${g.base[r]} #${g.qual[r]}`).toLowerCase()});
      }
    }
    rows.sort((a, b) => (!!b.game - !!a.game) || (b.named - a.named) || (a.game || a.name).localeCompare(b.game || b.name) || a.b - b.b || a.q - b.q || a.o - b.o);
    return (t.index = rows);
  }

  function filteredStats(file) {
    const f = S.find;
    const words = f.q.toLowerCase().split(/\s+/).filter(Boolean);
    return statIndex(file).filter(x => (!f.varies || x.vary) && (!f.named || x.named) && (!f.game || x.game) && words.every(w => x.text.includes(w)));
  }

  function panelAll(s) {
    const f = S.find;
    return `<div class="section-head"><h2>All stats</h2>${riskTag('danger')}
        <p>Every stat in this save, ${nf.format(statIndex(s.file).length)} in all. Stats the game shows on its stats screens use the game’s own wording; other names were matched by their hash and are very likely right. Where the real name is still unknown but the saves show what a stat holds, it gets a plain description in italics. The rest are shown as numbers.
        Stats the game uses usually change between your saves, so that filter is on by default. Change one thing at a time.</p></div>
      <div class="finder"><input type="search" placeholder="Search, for example kills, time running, or #103" value="${esc(f.q)}" data-find="q" aria-label="Search stats">
        <label><input type="checkbox" data-find="varies" ${f.varies ? 'checked' : ''}> Only stats that change between my saves</label>
        <label><input type="checkbox" data-find="named" ${f.named ? 'checked' : ''}> Only named stats</label>
        <label><input type="checkbox" data-find="game" ${f.game ? 'checked' : ''}> Only stats the game shows</label></div>
      <div id="allrows">${allRows(s)}</div>`;
  }

  function allRows(s) {
    const list = filteredStats(s.file);
    const shown = list.slice(0, S.find.limit);
    if (!list.length) return '<div class="empty">No stats match. Clear the search or turn off a filter.</div>';
    return `<table class="raw"><thead><tr><th>Stat</th><th>Whose</th><th>Type</th><th>Value</th></tr></thead><tbody>${shown.map(x => {
      const dr = draftOf(s.file).stats[`${x.g}:${x.r}`];
      const attrs = `data-edit="stat" data-key="${esc(x.g)}:${x.r}" data-group="${esc(x.g)}" data-row="${x.r}" data-base="${x.b}" data-qual="${x.q}" data-owner="${x.o}" data-label="${esc(x.name + ' (' + x.owner + ')')}"`;
      let input;
      if (x.locked) input = `<span class="lock">${esc(fmtRaw(x.v, x.type))}, managed by the Money tab</span>`;
      else if (x.type === 'bool') input = `<label class="toggle"><input type="checkbox" ${attrs} data-type="bool" data-unit="flag" data-orig="${x.v ? 1 : 0}" ${(dr ? dr.newValue : x.v) ? 'checked' : ''}> ${(dr ? dr.newValue : x.v) ? 'true' : 'false'}</label>`;
      else input = `<input type="number" ${attrs} data-type="${x.type === 'float' ? 'float' : 'int'}" data-unit="${x.type === 'float' ? 'raw-float' : 'count'}" min="0" max="${capOf(x)}" step="${x.type === 'float' ? 'any' : 1}"
        data-init="${esc(String(x.v))}" data-orig="${esc(JSON.stringify(x.v))}" value="${esc(String(dr ? dr.newValue : x.v))}">`;
      return `<tr class="${dr ? 'changed' : ''}"><td class="key${x.meaning && !x.game ? ' described' : ''}">${esc(x.game || x.name)}<small>${x.game ? esc(x.name) + ', ' : x.qlab ? esc(x.qlab) + ', ' : ''}${x.meaning && !x.game ? 'real name unknown, described from how it behaves in saves, ' : ''}#${x.b}${x.q ? ' / #' + x.q : ''}</small></td><td>${esc(x.owner)}</td><td>${esc(x.type)}${x.type === 'bool' ? '' : `<small>up to ${esc(compact.format(capOf(x)))}</small>`}</td><td>${input}${x.means ? `<small class="means">${esc(x.means.kind)}: ${esc(x.means.text)}</small>` : ''}</td></tr>`;
    }).join('')}</tbody></table>${list.length > shown.length ? `<div class="more"><button class="btn small" data-act="more">Show more (${nf.format(list.length - shown.length)} left)</button></div>` : ''}`;
  }

  const fmtRaw = (v, t) => t === 'float' ? nf2.format(v) : nf.format(v);
  const compact = new Intl.NumberFormat('en', {notation: 'compact', maximumFractionDigits: 1});
  // All stats: a cap far below where a counter could overflow as the game keeps adding to it (the meaning of most of
  // these stats is unknown, so this guards against the worst breakage, not against every bad value)
  const SAFE_MAX = {int64: 999999999999, int32: 9999999, u32: 9999999, int16: 9999, u8: 99, float: 999999999};
  // a stat already holding more than the cap isn't a simple counter (often an id or a set of flags): keep the type's range
  const capOf = x => Math.abs(x.v) > (SAFE_MAX[x.type] ?? Infinity) ? TYPE_MAX[x.type] : (SAFE_MAX[x.type] ?? TYPE_MAX[x.type]);

  // featured stats: the reasonable max in the units the field shows, and in words
  const maxShown = f => f.unit === 'ms' ? Math.floor(f.max / 3600000) : f.unit === 'distance' ? Math.floor(f.max / 1000) : f.max;
  function maxText(f) {
    if (f.max == null) return '';
    const n = nf.format(maxShown(f));
    const shown = f.unit === 'percent' ? `${n}%` : f.unit === 'ms' ? `${n} hours` : f.unit === 'distance' ? `${n} km` : f.unit === 'money' ? `$${n}` : n;
    return `Max ${shown}${f.maxWhy ? ', ' + f.maxWhy : ''}.`;
  }

  // ---- trophies
  // ---- completion: the game's own 100% checklist, line by line, with what can be picked for each
  // how a checklist line is completed here: [kind, feature or key, line key]
  const LINE_PICK = {
    bankjobs: ['rob', 'robberies', 'bankjobs'], paydayloans: ['rob', 'robberies', 'paydayloans'], smashngrabs: ['rob', 'robberies', 'smashngrabs'],
    stickups: ['rob', 'robberies', 'stickups'], vaults: ['rob', 'robberies', 'vaults'], narcotics: ['rob', 'fencing', 'narcotics'],
    jewelry: ['rob', 'fencing', 'jewelry'], markedbills: ['rob', 'fencing', 'markedbills'], vehiclesfenced: ['rob', 'fencing', 'vehicles'],
    cardsets: ['coll', 'cards'], magazines: ['coll', 'magazines'], styles: ['coll', 'watches'],
    meditation: ['feat', 'activities'], hoops: ['feat', 'hoops'], vehicles: ['feat', 'vehicles'], challenges: ['feat', 'challenges'],
    animals: ['comp', 'animals'], weapons: ['comp', 'weapons'], stunts: ['stunts'],
    races: ['act', 'races'], racechallenges: ['act', 'racechallenges'], shootingranges: ['act', 'shootingranges'], videogames: ['act', 'videogames'],
    pool: ['act', 'pool'], minigolf: ['act', 'minigolf'], drones: ['act', 'drones'], bret: ['act', 'bret']};
  // why the other lines have to be played
  const LINE_WHY = {
    story: 'Play the missions.', optionaltasks: 'Play them. The game records a task only once it’s played.',
    gangs: 'Play them. A clear is written in three places and hands out its own weapons, vehicles and safes.',
    kenton: 'Not possible yet: no save has a finished set to copy.', waink: 'Not possible yet: the save doesn’t show which locations they are.',
    underwater: 'Not possible yet: the save doesn’t show which discoveries they are.',
    flamingos_or_playlists_1: 'Cocaine flamingos can be tried as an experiment below. Playlists aren’t possible yet.',
    flamingos_or_playlists_2: 'Cocaine flamingos can be tried as an experiment below. Playlists aren’t possible yet.'};
  const EXP_LINES = new Set(['bret']);                                         // lines only offered as experiments
  const TESTED_LINES = new Set(['narcotics', 'jewelry', 'markedbills', 'vehiclesfenced', 'meditation']);   // seen in the game's stats after a PS5 test
  const EXP_COLL = ['bookswaps', 'magazinestyles', 'flamingos'];               // collectibles only offered as experiments
  const FEAT_ALL = {discovery: {categories: 'all'}, gyms: {gyms: 'all'}, activities: {spots: 'all', character: 'lucia'},
    hoops: {hoops: 'all', scored: true, county_counters: 'update'}, vehicles: {count: 'min'}, challenges: {categories: 'all'}};
  // the game's checklist lines are in capitals: shown in sentence case, keeping the names that have their own spelling
  const sentence = t => {
    const x = String(t || ''), letters = x.replace(/[^A-Za-z]/g, ''), caps = letters.replace(/[^A-Z]/g, '').length;
    if (!letters || caps / letters.length < .7) return x;
    return (x.charAt(0) + x.slice(1).toLowerCase()).replace(/\bwaink\b/i, 'WAiNK').replace(/\bbret's\b/i, 'Bret’s').replace(/\bkenton\b/i, 'Kenton');
  };

  function pickRob(file, feat, key, on) {
    const d = draftOf(file).completion, cur = new Set(d[feat]?.lines || []);
    if (on) cur.add(key); else cur.delete(key);
    if (cur.size) d[feat] = feat === 'robberies' ? {lines: [...cur], vaults: 'large'} : {lines: [...cur], character: 'lucia'}; else delete d[feat];
  }
  function pickColl(file, key, on) {
    const d = draftOf(file).completion, cur = new Set(d.collectibles?.categories || []);
    if (on) cur.add(key); else cur.delete(key);
    const exp = [...cur].filter(k => EXP_COLL.includes(k));
    if (cur.size) d.collectibles = {categories: [...cur], card_items: 'skip', watch_items: 'skip', ...(exp.length ? {experimental: exp} : {})};
    else delete d.collectibles;
  }
  function pickAct(file, key, on) {
    const d = draftOf(file).completion, lines = S.comp[file].activities2?.lines || [], cur = new Set(d.activities2?.lines || []);
    if (on) cur.add(key); else cur.delete(key);
    if (cur.size) {
      const level = {};
      for (const k of cur) level[k] = (lines.find(l => l.key === k) || {}).confidence === 'verified' ? 'full' : 'counter';
      d.activities2 = {lines: [...cur], level, unverified_ok: cur.has('bret')};
    } else delete d.activities2;
  }
  function pickComp(file, group, on) {
    const d = draftOf(file).completion, g = new Set(d.compendium?.groups || []);
    if (on) g.add(group); else g.delete(group);
    if (g.size) d.compendium = {groups: [...g]}; else delete d.compendium;
  }
  function pickFeat(file, feat, on) {
    const d = draftOf(file).completion;
    if (on) d[feat] = JSON.parse(JSON.stringify(FEAT_ALL[feat])); else delete d[feat];
  }
  const openStunts = file => (S.comp[file].stunts?.groups || []).filter(g => g.done < g.count).map(g => g.id);

  function linePicked(file, key) {
    const d = draftOf(file).completion, p = LINE_PICK[key];
    if (!p) return false;
    if (p[0] === 'rob') return !!d[p[1]]?.lines?.includes(p[2]);
    if (p[0] === 'coll') return !!d.collectibles?.categories?.includes(p[1]);
    if (p[0] === 'act') return !!d.activities2?.lines?.includes(p[1]);
    if (p[0] === 'comp') return !!d.compendium?.groups?.includes(p[1]);
    if (p[0] === 'feat') return p[1] === 'challenges' ? d.challenges?.categories === 'all' : !!d[p[1]];
    return (S.stuntSel[file] || new Set()).size > 0;
  }
  // a line whose part of the save couldn't be read can't be picked
  const lineReady = (file, key) => {
    const p = LINE_PICK[key], C = S.comp[file];
    if (!p) return false;
    const need = {rob: p[1], coll: 'collectibles', act: 'activities2', comp: 'compendium', stunts: 'stunts'}[p[0]] || p[1];
    return !!C[need];
  };

  function setLine(file, key, on) {
    const p = LINE_PICK[key];
    if (!p || !lineReady(file, key)) return;
    if (p[0] === 'rob') pickRob(file, p[1], p[2], on);
    else if (p[0] === 'coll') pickColl(file, p[1], on);
    else if (p[0] === 'act') pickAct(file, p[1], on);
    else if (p[0] === 'comp') pickComp(file, p[1], on);
    else if (p[0] === 'feat') pickFeat(file, p[1], on);
  }

  // every line that can be done, plus the extras that go with them (map discoveries, gyms, convenience stores);
  // experimental parts only when asked for
  async function pickEverything(file, withExp) {
    const C = S.comp[file], lines = C.checklist?.lines || [];
    for (const l of lines) {
      const p = LINE_PICK[l.key];
      if (!p || p[0] === 'stunts' || l.done || (l.percent ?? 0) >= 100 || (EXP_LINES.has(l.key) && !withExp)) continue;
      setLine(file, l.key, true);
    }
    if (C.discovery) pickFeat(file, 'discovery', true);
    if (C.gyms) pickFeat(file, 'gyms', true);
    if (C.robberies?.lines?.some(l => l.key === 'convenience' && !l.done)) pickRob(file, 'robberies', 'convenience', true);
    if (C.collectibles) for (const k of EXP_COLL) pickColl(file, k, !!withExp && (C.collectibles.categories || []).some(c => c.key === k && c.found < c.entries));
    if (withExp && C.activities2) pickAct(file, 'bret', true);
    const st = C.stunts ? openStunts(file) : [];
    if (st.length) await setStunts(file, st);
    else { S.mainKey = ''; renderMain(); renderPending(); renderCounts(); }
  }
  async function clearPicks(file) {
    const d = draftOf(file);
    d.completion = {};
    await setStunts(file, []);
  }

  // the checklist as it would be after the picks so far, worked out by the app (nothing is written)
  function schedulePreview(file) {
    const P = S.preview[file] || (S.preview[file] = {});
    const d = draftOf(file);
    const body = {file, stats: Object.values(d.stats), completion: d.completion, guns: d.guns || {}};
    const sig = JSON.stringify(body);
    if (sig === P.want) return;
    P.want = sig;
    clearTimeout(P.t);
    if (!Object.keys(d.completion || {}).length && !Object.keys(d.stats).length && !gunCount(d.guns)) { P.data = null; P.sig = sig; P.busy = false; return; }
    P.busy = true;
    P.t = setTimeout(async () => {
      let data;
      try { data = await api('/api/preview', body); } catch (e) { data = {ok: false, failed: [], detail: e.code}; }
      if (P.want !== sig) return;                  // a newer pick is on its way
      P.data = data; P.sig = sig; P.busy = false;
      if (S.tab === 'completion' && S.slot === file) { S.mainKey = ''; renderMain(); }
    }, 500);
  }

  function compSummary(s) {
    const C = S.comp[s.file], ck = C.checklist, P = S.preview[s.file] || {}, d = draftOf(s.file);
    const now = ck?.overall ? (ck.overall.stored ?? ck.overall.computed) : null;
    const picks = compCount(d.completion) + ((S.stuntSel[s.file]?.size) ? 1 : 0);
    const ready = P.data?.ok && !P.busy;
    const after = picks && ready ? P.data.overall.computed : null;
    const pct = v => v == null ? '–' : `${nf2.format(v)}%`;
    const w = v => `${Math.max(0, Math.min(100, v || 0))}%`;
    const failed = P.data && !P.data.ok && !P.busy ? (P.data.failed || []) : [];
    const exp = !!S.compExp[s.file];
    return `<div class="comp-summary">
        <div class="nums">
          <div><span class="lbl">100% completion now</span><span class="big">${pct(now)}</span></div>
          <div class="after${picks ? '' : ' muted'}"><span class="lbl">After your picks</span><span class="big">${!picks ? '–' : P.busy ? '…' : pct(after)}</span>
            ${picks && P.busy ? '<span class="lbl">Working it out</span>' : ''}</div>
        </div>
        <div class="meter" role="img" aria-label="${now == null ? '' : `${nf2.format(now)}% now${after != null ? `, ${nf2.format(after)}% after your picks` : ''}`}">
          <span class="now" style="width:${w(now)}"></span>${after != null && after > now ? `<span class="gain" style="inset-inline-start:${w(now)};width:${w(after - now)}"></span>` : ''}</div>
        <div class="row">
          <button class="btn primary" data-act="pick-all">Pick everything that can be done</button>
          ${picks ? '<button class="btn" data-act="pick-none">Clear picks</button>' : ''}
          <label class="toggle small"><input type="checkbox" data-act="pick-exp" ${exp ? 'checked' : ''}> Include experiments (Bret’s decks, book swaps, magazine styles, cocaine flamingos)</label>
        </div>
        ${failed.length ? `<div class="callout danger">These picks don’t work on this save, so saving would fail: ${failed.map(esc).join(', ')}. Undo them, or reload the save.</div>` : ''}
        <p class="note">Each pick marks things found and completed the way the game records them, sets the counters to match, and works the 100% figure out again. Prize money, rewards and trophies aren’t given.</p>
        <p class="note">Tested on a PS5 with every pick at once: the save loads and plays, and gym memberships, map discoveries, meditation spots and fencing show in the game’s stats as written. The other lines only show on the game’s 100% screen, which hasn’t been checked yet.</p>
      </div>`;
  }

  function lineRow(s, l, a) {
    const money = l.of != null && l.of >= 1000;
    const fmt = (v, of) => of == null ? (typeof v === 'number' ? nf2.format(v) + '%' : '') : money ? `$${nf.format(v)} of $${nf.format(of)}` : `${nf.format(v)} of ${nf.format(of)}`;
    const p = LINE_PICK[l.key], picked = linePicked(s.file, l.key), exp = EXP_LINES.has(l.key);
    const full = l.done || (l.percent ?? 0) >= 100;
    let act;
    if (full) act = '<span class="done-mark">Done</span>';
    else if (!p) act = `<span class="why">${esc(LINE_WHY[l.key] || 'Not possible from the save yet.')}</span>`;
    else if (!lineReady(s.file, l.key)) act = '<span class="why">This part of the save can’t be read yet.</span>';
    else act = `<button class="btn small pick${picked ? ' on' : ''}" data-act="line-pick" data-line="${esc(l.key)}" aria-pressed="${picked}">${picked ? 'Picked' : exp ? 'Try it' : 'Complete'}</button>${exp ? '<small>Experiment</small>' : TESTED_LINES.has(l.key) ? '<small class="tested">Tested on PS5</small>' : ''}`;
    const moved = a && a.value !== l.value;
    const pctNow = Math.max(0, Math.min(100, l.percent ?? 0)), pctAfter = moved ? Math.max(0, Math.min(100, a.percent ?? 0)) : pctNow;
    return `<tr class="${picked ? 'picked' : ''}${full ? ' full' : ''}">
        <td class="key">${esc(sentence(l.label))}${l.grade === 'partial' ? '<small>Only part of this can be done here.</small>' : ''}
          <span class="mini" aria-hidden="true"><span style="width:${pctNow}%"></span>${pctAfter > pctNow ? `<span class="add" style="inset-inline-start:${pctNow}%;width:${pctAfter - pctNow}%"></span>` : ''}</span></td>
        <td class="num">${fmt(l.value, l.of)}${moved ? `<small class="after">${fmt(a.value, a.of)} after</small>` : ''}</td>
        <td class="num">${l.weight}%</td><td class="act">${act}</td></tr>`;
  }

  function checklistSections(s) {
    const C = S.comp[s.file], ck = C.checklist, P = S.preview[s.file] || {};
    if (!ck?.lines) return '<div class="callout danger">This save’s 100% checklist can’t be read, so the lines below can’t be shown. The parts further down still work.</div>';
    const after = P.data?.ok && !P.busy ? Object.fromEntries(P.data.lines.map(l => [l.key, l])) : {};
    const secs = [...new Set(ck.lines.map(l => l.section))];
    return secs.map(sec => {
      const lines = ck.lines.filter(l => l.section === sec);
      const done = lines.filter(l => l.done || (l.percent ?? 0) >= 100).length;
      return `<div class="group"><div class="section-head"><h3>${esc(sentence(sec).replace(' & ', ' and '))}</h3><span class="note">${done} of ${lines.length} lines done</span></div>
        <table class="raw ck"><thead><tr><th>Line</th><th class="num">In this save</th><th class="num">Worth</th><th></th></tr></thead>
          <tbody>${lines.map(l => lineRow(s, l, after[l.key])).join('')}</tbody></table></div>`;
    }).join('');
  }

  function stuntGroups(s) {
    const c = S.comp[s.file].stunts;
    if (!c) return '';
    const sel = S.stuntSel[s.file] || new Set();
    const row = g => {
      const marked = sel.has(g.id), all = g.done >= g.count;
      return `<div class="field"><div class="name">${esc(g.label)}<span class="help">${nf.format(g.done)} of ${nf.format(g.count)} done in this save${g.gameTotal !== g.count ? ` (the game has ${nf.format(g.gameTotal)})` : ''}.</span></div>
        <div class="inputs">${marked ? `<span class="note">Marked done. Save edits to apply it.</span> <button class="btn small" data-act="stunts-undo" data-group="${g.id}">Undo</button>`
          : `<button class="btn small" data-act="stunts" data-group="${g.id}" ${all ? 'disabled' : ''}>${all ? 'All done' : 'Mark all done'}</button>`}</div></div>`;
    };
    const left = c.groups.filter(g => g.done < g.count && !sel.has(g.id)).length;
    return `<div class="group"><div class="section-head"><h3>Stunts</h3>${left > 1 ? '<button class="btn small" data-act="stunts" data-group="all">Mark every stunt done</button>' : ''}
        <p>The 100% checklist needs any ${nf.format(c.for100)} of the game’s 397 stunts. Unique stunts done in this save: ${c.uniqueTotal == null ? 'unknown' : nf.format(c.uniqueTotal)}. Under-the-bridge flights and knife flights can’t be told apart in the save, so they’re marked together.</p></div>
        <div class="fields">${c.groups.map(row).join('')}</div></div>`;
  }

  function panelCompletion(s) {
    const C = S.comp[s.file];
    const missing = Object.keys(C.errors || {});
    schedulePreview(s.file);
    return `<div class="section-head"><h2>Completion</h2>${riskTag('caution')}
        <p>The game’s own 100% checklist for this save. Pick the lines to complete, or pick everything at once, and the figure it would reach shows before you save.</p></div>
      ${compSummary(s)}
      ${missing.length ? `<div class="callout">Some parts can’t be read in this save yet, usually because it’s early in the story: ${missing.map(esc).join(', ')}. Everything else works.</div>` : ''}
      ${checklistSections(s)}
      <details class="more-opts" data-keep="compMore" ${S.keep.compMore ? 'open' : ''}><summary>Every option, part by part</summary>
        <p class="note">The same edits in finer steps, plus extras the checklist doesn’t count: map discoveries, gym memberships, convenience-store robberies, single challenge categories, and the experiments.</p>
        ${stuntGroups(s)}${compParts(s)}</details>
      <details class="more-opts" data-keep="compCheats" ${S.keep.compCheats ? 'open' : ''}><summary>Cheats</summary>${cheatParts(s)}</details>
      <details class="more-opts" data-keep="compLeft" ${S.keep.compLeft ? 'open' : ''}><summary>What’s left to play in the game</summary>${leftToPlay(s) || '<p class="note">Not available for this save.</p>'}</details>`;
  }

  // ---- cheats: the cheat unlock trackers (challenges.py, set d6d53427), shown read-only. Tested on a PS5, completing a
  // tracker doesn't unlock its cheat: when the game unlocks one it also sets the cheat's entry in the unlock catalog
  // (block 6df5d2cf) from 0 to 2, and that entry is known for only one cheat so far (dev_scratch/cheats). A tracker
  // completed without it might also keep the game from unlocking the cheat later, so the page doesn't offer it.
  const cheatText = c => `${c.name ? `<span class="cheat-name" data-no-i18n>${esc(c.name)}</span>` : ''}<span class="${c.name ? 'effect' : 'cheat-name'}">${esc(c.effect)}</span>
    <span class="help"><b>To unlock:</b> ${esc(c.unlock)}</span>`;
  function cheatParts(s) {
    const C = S.comp[s.file].cheats;
    if (!C) return '<p class="note">This part of the save can’t be read yet.</p>';
    if (C.problem) return `<div class="callout">${esc(ERR['save_' + C.problem] || ERR.save_layout_changed)}</div>`;
    const head = `<div class="section-head"><h3>Cheat unlocks</h3>
        <p>The game unlocks a cheat when you meet its condition, and keeps a tracker for each one in the save. ${nf.format(C.done)} of ${nf.format(C.of)} are complete in this save. Tested on a PS5, completing a tracker isn’t enough: the game also marks the unlock in a list, and the entry for most cheats isn’t known yet. So cheats can’t be unlocked here for now.</p></div>`;
    const ctl = e => e.done >= e.of ? '<span class="done-mark">Unlocked</span>' : '';
    const rows = C.entries.map(e => {
      if (e.kind === 'single') return `<div class="field cheat"><div class="name">${cheatText(e.cheats[0])}</div><div class="inputs">${ctl(e)}</div></div>`;
      const note = e.kind === 'pair' ? '' : `<span class="help">Save Garage hasn’t seen these ${nf.format(e.of)} trackers hold any progress in a save, so it can’t tell which cheat each one is.</span>`;
      return `<div class="field cheat ${e.kind}"><div class="name">${note}<ul class="cheats">${e.cheats.map(c => `<li>${cheatText(c)}</li>`).join('')}</ul></div>
        <div class="inputs">${ctl(e)}</div></div>`;
    }).join('');
    return `<div class="group">${head}<div class="fields">${rows}</div></div>`;
  }

  function compParts(s) {
    const C = S.comp[s.file], d = draftOf(s.file).completion;
    const pending = (k, text) => `<span class="note">${esc(text)} Save edits to apply it.</span> <button class="btn small" data-act="comp-undo" data-feature="${k}">Undo</button>`;
    // compendium: animals and weapons (vehicles aren't offered: the game's vehicle pages don't match the save's list)
    const types = (C.compendium?.types || []).filter(t => t.group === 'animals' || t.group === 'weapons');
    const cg = new Set(d.compendium?.groups || []);
    const comp = !C.compendium ? '' : `<div class="group"><div class="section-head"><h3>Compendium</h3><p>Marks animals and weapons as discovered in the game’s compendium, with the counters and the 100% checklist rows that go with them. Vehicles aren’t offered: the game’s vehicle pages don’t match the list in the save.</p></div>
      <div class="fields">${types.map(t => `<div class="field"><div class="name">${t.group === 'animals' ? 'Animals' : 'Weapons'}<span class="help">${nf.format(t.discovered)} of ${nf.format(t.candidates)} discovered in this save.</span></div>
        <div class="inputs">${cg.has(t.group) ? pending('compendium:' + t.group, 'Will be marked discovered.') : `<button class="btn small" data-act="comp-add" data-feature="compendium" data-value="${t.group}" ${t.discovered >= t.candidates ? 'disabled' : ''}>${t.discovered >= t.candidates ? 'All discovered' : 'Mark all discovered'}</button>`}</div></div>`).join('')}</div></div>`;
    // map discoveries: shop and place categories
    const places = (C.discovery?.categories || []).filter(x => x.kind === 'place');
    const placeDone = places.filter(x => x.state === 'complete').length;
    const disc = !C.discovery ? '' : `<div class="group"><div class="section-head"><h3>Map discoveries</h3>${riskTag('tested')}<p>Shops and places on the map, by kind: ${nf.format(placeDone)} of ${nf.format(places.length)} kinds fully discovered. Completing a kind marks all its locations discovered, the way the game records a finished kind. Stunt and gang locations aren’t touched here.</p></div>
      <div class="fields"><div class="field"><div class="name">Every shop and place<span class="help">${places.some(x => x.state !== 'complete') ? `<span data-no-i18n>${places.filter(x => x.state !== 'complete').map(x => `${esc(x.label)} ${x.found}/${x.locations}`).join(', ')}</span>` : 'All done.'}</span></div>
        <div class="inputs">${d.discovery ? pending('discovery', 'Will be discovered.') : `<button class="btn small" data-act="comp-add" data-feature="discovery" data-value="all" ${placeDone >= places.length ? 'disabled' : ''}>${placeDone >= places.length ? 'All discovered' : 'Discover all'}</button>`}</div></div></div></div>`;
    // challenges by category
    const cats = C.challenges?.categories || [];
    const chosen = d.challenges ? (d.challenges.categories === 'all' ? new Set(cats.map(x => x.key)) : new Set(d.challenges.categories)) : new Set();
    const chal = !C.challenges ? '' : `<div class="group"><div class="section-head"><h3>Challenges</h3>${cats.some(x => x.done < x.of && !chosen.has(x.key)) ? '<button class="btn small" data-act="comp-add" data-feature="challenges" data-value="all">Complete every challenge</button>' : ''}
        <p>The 100% checklist needs 70 of the game’s 80 challenges. Completed in this save: ${nf.format(C.challenges?.done ?? 0)}. Completing one sets it done and moves its counters; rewards the game hands out itself, such as vehicles, may not unlock.</p></div>
      <div class="fields">${cats.map(x => `<div class="field"><div class="name">${esc(x.label)}<span class="help">${x.done} of ${x.of} completed.</span></div>
        <div class="inputs">${chosen.has(x.key) ? pending('challenges:' + x.key, 'Will be completed.') : `<button class="btn small" data-act="comp-add" data-feature="challenges" data-value="${x.key}" ${x.done >= x.of ? 'disabled' : ''}>${x.done >= x.of ? 'All done' : 'Complete'}</button>`}</div></div>`).join('')}</div></div>`;
    // gym memberships
    const gyms = C.gyms?.gyms || [];
    const owned = gyms.filter(g => g.owned).length;
    const gymBox = !C.gyms ? '' : `<div class="group"><div class="section-head"><h3>Gym memberships</h3>${riskTag('tested')}<p>The 100% checklist needs all 8. Owned in this save: ${owned}. A membership is added the way the game adds one; the gyms marked “not seen yet” have never been bought in a real save, so their item IDs come from the game’s text.</p></div>
      <div class="fields"><div class="field"><div class="name">All gym memberships<span class="help">${gyms.map(g => `<span data-no-i18n>${esc(g.label)}</span>${g.owned ? ' <span>(owned)</span>' : g.grade !== 'confirmed' ? ' <span>(not seen yet)</span>' : ''}`).join(', ')}.</span></div>
        <div class="inputs">${d.gyms ? pending('gyms', 'Will be added.') : `<button class="btn small" data-act="comp-add" data-feature="gyms" data-value="all" ${owned >= gyms.length ? 'disabled' : ''}>${owned >= gyms.length ? 'All owned' : 'Add all'}</button>`}</div></div></div></div>`;
    // meditation spots
    const m = C.activities?.meditation;
    const med = !m ? '' : `<div class="group"><div class="section-head"><h3>Meditation spots</h3><p>The 100% checklist needs 15; the save has ${m.total} spots and ${m.done} are done. Completing them records a meditation at each spot, for Lucia, with the counters and the checklist row in step. Focus training rewards aren’t given.</p></div>
      <div class="fields"><div class="field"><div class="name">Every meditation spot<span class="help">${m.done} of ${m.total} done.</span></div>
        <div class="inputs">${d.activities ? pending('activities', 'Will be completed.') : `<button class="btn small" data-act="comp-add" data-feature="activities" data-value="all" ${m.done >= m.total ? 'disabled' : ''}>${m.done >= m.total ? 'All done' : 'Complete all'}</button>`}</div></div></div></div>`;
    return comp + disc + chal + gymBox + med + robberyParts(s) + activityParts(s) + collectibleParts(s);
  }

  // collectibles: the proven kinds, the experimental ones (no save has one to copy), and the ones that can't be written yet
  const COLL = {
    cards: ['Collectible cards', c => `All ${c.entries} cards in their 18 sets (the checklist needs 15); ${c.found} found in this save. The cards don’t appear in Lucia’s pocket.`],
    magazines: ['Magazines, books and comics', c => `The ${c.entries} identified so far; ${c.found} found. They count toward MAGAZINES, BOOKS & COMICS (${c.line?.value ?? '?'} of ${c.line?.of ?? 30}).`],
    watches: ['Luxury watches', c => `All ${c.entries} watches, which count as discovered styles (${c.line?.value ?? '?'} of ${c.line?.of ?? 70}); ${c.found} found. The watches themselves aren’t added to the wardrobe.`],
    bookswaps: ['Book swaps (experimental)', c => `${c.entries} library book swaps that count toward magazines, books and comics. No save has one yet, so how the game records it is a best guess.`],
    magazinestyles: ['Magazine styles (experimental)', c => `${c.entries} tattoos, make-up looks and hairstyles from magazines that count as discovered styles. No save has one yet, and the store unlock they give may be stored elsewhere.`],
    flamingos: ['Cocaine flamingos (experimental)', c => `All ${c.entries} are identified, but no save has had one destroyed, so how the game records it is a best guess.`]};
  function collectibleParts(s) {
    const C = S.comp[s.file], d = draftOf(s.file).completion;
    if (!C.collectibles) return '';
    const cats = (C.collectibles.categories || []).filter(c => COLL[c.key] && (c.state === 'proven' || c.state === 'experimental'));
    const chosen = new Set(d.collectibles?.categories || []);
    const rows = cats.map(c => `<div class="field"><div class="name">${esc(COLL[c.key][0])}<span class="help">${COLL[c.key][1](c)}</span></div>
      <div class="inputs">${chosen.has(c.key) ? `<span class="note">Will be marked found. Save edits to apply it.</span> <button class="btn small" data-act="coll-undo" data-value="${c.key}">Undo</button>`
        : `<button class="btn small" data-act="coll-add" data-value="${c.key}" ${c.found >= c.entries ? 'disabled' : ''}>${c.found >= c.entries ? 'All found' : 'Mark found'}</button>`}</div></div>`).join('');
    const refused = (C.collectibles.categories || []).filter(c => c.state === 'refused').map(c => esc((c.label || c.key).charAt(0) + (c.label || c.key).slice(1).toLowerCase().replace('waink', 'WAiNK')));
    return `<div class="group"><div class="section-head"><h3>Collectibles</h3><p>Marked found the way the game records a pickup. Marking one found may stop it appearing in the world, so keep your backup until the PS5 shows it counted.</p></div>
      <div class="fields">${rows}</div>${refused.length ? `<p class="note">Not possible yet, because the save doesn’t show which entries they are or how the game records them: <span data-no-i18n>${refused.join(', ')}</span>.</p>` : ''}</div>`;
  }

  // activities, hoops and the vehicle compendium
  function activityParts(s) {
    const C = S.comp[s.file], d = draftOf(s.file).completion;
    if (!C.activities2 || !C.hoops || !C.vehicles) return '';
    const label = t => t.charAt(0) + t.slice(1).toLowerCase().replace(/bret's/, 'Bret’s');
    const chosen = new Set(d.activities2?.lines || []);
    const lines = C.activities2.lines;
    const open = lines.filter(l => !l.done_line && l.counter < l.of && !chosen.has(l.key) && l.key !== 'bret');
    const help = l => l.confidence === 'verified' ? 'Marks each one played.' : l.key === 'bret' ? 'Sets the count only: deck progress isn’t in the save.' : 'Sets the checklist count; the individual results aren’t written, since no save has one played to copy.';
    const acts = `<div class="group"><div class="section-head"><h3>Activities</h3>${open.length > 1 ? '<button class="btn small" data-act="act-line" data-value="all">Complete all</button>' : ''}<p>Races, ranges, video games, pool, mini golf, drone trials and Bret’s target decks. Prize money, rewards and trophies for them aren’t given.</p></div>
      <div class="fields">${lines.map(l => `<div class="field"><div class="name">${esc(label(l.label))}<span class="help">${nf.format(l.counter)} of ${nf.format(l.of)}. ${help(l)}</span></div>
        <div class="inputs">${chosen.has(l.key) ? `<span class="note">Will be completed. Save edits to apply it.</span> <button class="btn small" data-act="act-line-undo" data-value="${l.key}">Undo</button>`
          : `<button class="btn small" data-act="act-line" data-value="${l.key}" ${l.counter >= l.of ? 'disabled' : ''}>${l.counter >= l.of ? 'Done' : 'Complete'}</button>`}</div></div>`).join('')}</div></div>`;
    const h = C.hoops, ht = h.countyTotals || {};
    const hoopBox = `<div class="group"><div class="section-head"><h3>Basketball hoops</h3><p>The 100% checklist needs 90 of the game’s 100 hoops. Found ${h.found}, scored ${h.scored}. Every hoop is marked found and scored, with each county’s count (${Object.entries(ht).map(([k, v]) => `${esc(k)} ${v}`).join(', ')}, from the game’s own hoop numbers on public maps).</p></div>
      <div class="fields"><div class="field"><div class="name">Every hoop<span class="help">${h.scored} of ${h.total} scored.</span></div>
        <div class="inputs">${d.hoops ? `<span class="note">Will be scored. Save edits to apply it.</span> <button class="btn small" data-act="comp-undo" data-feature="hoops">Undo</button>` : `<button class="btn small" data-act="comp-add" data-feature="hoops" data-value="all" ${h.scored >= h.total ? 'disabled' : ''}>${h.scored >= h.total ? 'All scored' : 'Score all'}</button>`}</div></div></div></div>`;
    const v = C.vehicles;
    const veh = `<div class="group"><div class="section-head"><h3>Vehicle compendium</h3><p>BASE MODEL VEHICLES on the 100% checklist: ${v.checklist.value} of ${v.checklist.of}. Adds the vehicles still needed to the compendium, cars, bikes, boats and aircraft, each counted on its own page. Emergency, military, truck, transport, industrial and off-road vehicles aren’t added yet: the save doesn’t show for certain which page counts them.</p></div>
      <div class="fields"><div class="field"><div class="name">Discover ${v.min ? v.min.adds : v.needed} more vehicles<span class="help">Reaches ${v.min ? v.min.reaches : v.checklist.value + v.needed} of ${v.checklist.of}, from ${v.candidates} candidates.</span></div>
        <div class="inputs">${d.vehicles ? `<span class="note">Will be discovered. Save edits to apply it.</span> <button class="btn small" data-act="comp-undo" data-feature="vehicles">Undo</button>` : `<button class="btn small" data-act="comp-add" data-feature="vehicles" data-value="min" ${!v.needed || !(v.min ? v.min.adds : v.candidates) ? 'disabled' : ''}>${!v.needed ? 'Done' : !(v.min ? v.min.adds : v.candidates) ? 'No candidates left' : 'Discover'}</button>`}</div></div></div></div>`;
    return acts + hoopBox + veh;
  }

  // robberies and fencing: lines of the checklist, each marked as the game records it
  function robberyParts(s) {
    const C = S.comp[s.file], d = draftOf(s.file).completion;
    if (!C.robberies || !C.fencing) return '';
    const fmtv = l => l.of >= 1000 ? `$${nf.format(l.value)} of $${nf.format(l.of)}` : `${nf.format(l.value)} of ${nf.format(l.of)}`;
    const part = (feat, title, intro, lines) => {
      const chosen = new Set(d[feat]?.lines || []);
      const open = lines.filter(l => !l.done && !chosen.has(l.key));
      return `<div class="group"><div class="section-head"><h3>${title}</h3>${open.length > 1 ? `<button class="btn small" data-act="comp-line" data-feature="${feat}" data-value="all">Complete all</button>` : ''}<p>${intro}</p></div>
        <div class="fields">${lines.map(l => `<div class="field"><div class="name">${esc(l.label.charAt(0) + l.label.slice(1).toLowerCase())}<span class="help">${fmtv(l)}${l.missing ? `, $${nf.format(l.missing)} to go` : ''}.</span></div>
          <div class="inputs">${chosen.has(l.key) ? `<span class="note">Will be completed. Save edits to apply it.</span> <button class="btn small" data-act="comp-line-undo" data-feature="${feat}" data-value="${l.key}">Undo</button>`
            : `<button class="btn small" data-act="comp-line" data-feature="${feat}" data-value="${l.key}" ${l.done ? 'disabled' : ''}>${l.done ? 'Done' : 'Complete'}</button>`}</div></div>`).join('')}</div></div>`;
    };
    return part('robberies', 'Robberies', 'Marks robbery locations fully hit the way the game records it, with the per-type counters and the checklist rows. No cash, goods or robbery counts are added. Vaults: the save doesn’t say which 8 banks have one, so the vaults of all 12 large banks are marked.', C.robberies.lines)
      + part('fencing', 'Fencing', 'Records one sale per unfinished line, worth exactly what’s missing, to the fence the game uses most for it, as Lucia. The earnings totals that a real sale raises go up with it.', C.fencing.lines);
  }

  // optional tasks and gang operations can't be completed by editing the save: show what's left to play
  function leftToPlay(s) {
    const C = S.comp[s.file], t = C.tasks, g = C.gangs;
    if (!t || !g) return '';
    const np = (t.sideMissions || []).some(x => x.title) ? t.sideMissions.filter(x => x.state !== 'done') : (t.notPassed || []), titled = np.filter(x => x.title), untitled = np.length - titled.length;
    const taskList = titled.length ? `<span data-no-i18n>${titled.map(x => esc(x.title)).join(', ')}</span>` + (untitled ? `<span>, and ${untitled} more without a title in the game’s text</span>` : '') : '';
    const tasks = `<div class="group"><div class="section-head"><h3>Optional tasks</h3><p>${t.checklist.value} of ${t.checklist.of} done. These can’t be completed by editing the save: the game records a task only once it’s played, and recording one that wasn’t played would leave it still on offer in the world, without its rewards. ${t.left > 0 ? `Any ${t.left} more will do: there are a few hundred optional tasks, and 102 give the full 100%, because each one is worth 0.99%.` : 'This line is complete.'}</p></div>
      ${taskList ? `<p class="note">Side missions not passed in this save, a good place to look: ${taskList}.</p>` : ''}</div>`;
    const left = (g.locations || []).filter(x => !x.cleared && x.counted !== false);
    const byGang = Object.fromEntries((g.gangs || []).map(x => [x.key, x.name]));
    const gangs = `<div class="group"><div class="section-head"><h3>Gang operations</h3><p>${g.checklist.value} of ${g.checklist.of} cleared. These can’t be completed by editing the save either: a clear is written in three places, many operations have no record yet, and each one hands out its own weapons, vehicles and safes. Left to clear:</p></div>
      <table class="raw"><thead><tr><th>Operation</th><th>Gang</th><th>State</th></tr></thead><tbody>${left.map(x => `
        <tr><td class="key" data-no-i18n>${esc(x.label || x.owner || x.id)}${x.hint ? `<small>${esc(x.hint)}</small>` : ''}</td><td data-no-i18n>${esc(byGang[x.gang] || x.gang || '')}</td><td>${esc(x.state || '')}</td></tr>`).join('')}</tbody></table></div>`;
    return tasks + gangs;
  }

  // ---- world: time of day, health, armour
  const two = n => String(n).padStart(2, '0');
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  // the month in the page's language (the game's date is kept as it is)
  const monthName = m => { try { return new Intl.DateTimeFormat(document.documentElement.lang || 'en', {month: 'long', timeZone: 'UTC'}).format(new Date(Date.UTC(2000, m - 1, 1))); } catch { return MONTHS[m - 1] || ''; } };
  function panelWorld(s) {
    const w = S.world[s.file], d = draftOf(s.file).world, c = w.clock;
    const t = d.time || {hour: c.hour, minute: c.minute};
    const hp = d.health ?? w.health;
    return `<div class="section-head"><h2>World</h2>${riskTag('caution')}
        <p>The time of day, health and armour the save was made with. Not tested on a PS5 yet: send the save and check it loads before relying on it.</p></div>
      <div class="fields">
        <div class="field"><div class="name">Time of day<span class="help">Now ${two(c.hour)}:${two(c.minute)} on ${c.day} ${monthName(c.month)} ${c.year} in the game. The date stays the same.</span></div>
          <div class="inputs"><div class="cell narrow ${d.time ? 'changed' : ''}"><label for="w-hour">Hour</label><span class="with-unit"><input id="w-hour" type="number" min="0" max="23" step="1" value="${t.hour}" data-world="hour"></span></div>
            <div class="cell narrow ${d.time ? 'changed' : ''}"><label for="w-min">Minute</label><span class="with-unit"><input id="w-min" type="number" min="0" max="59" step="1" value="${two(t.minute)}" data-world="minute"></span></div></div></div>
        <div class="field"><div class="name">Health<span class="help">Now ${nf2.format(w.health)}. Up to ${nf.format(w.healthMax)}; above 100 is overpowered health.</span></div>
          <div class="inputs"><div class="cell ${d.health != null ? 'changed' : ''}"><label for="w-hp">Health</label><span class="with-unit"><input id="w-hp" type="number" min="1" max="${w.healthMax}" step="any" value="${hp}" data-world="health">
            <button class="btn small" data-act="world-fill" data-what="health">Max</button></span></div></div></div>
        <div class="field"><div class="name">Armour<span class="help">Now ${nf2.format(w.armour)} of ${nf2.format(w.armourMax)}, for both characters’ armour together.</span></div>
          <div class="inputs">${d.armour === 'full' ? '<span class="note">Will be filled. Save edits to apply it.</span> <button class="btn small" data-act="world-undo" data-what="armour">Undo</button>'
            : `<button class="btn small" data-act="world-fill" data-what="armour" ${w.armour >= w.armourMax ? 'disabled' : ''}>${w.armour >= w.armourMax ? 'Already full' : 'Fill armour'}</button>`}</div></div>
      </div>
      ${mapGroup(s)}${characterGroups(s)}`;
  }

  // a World field with its own risk label; help is plain text
  const worldField = (name, risk, help, ctl) => `<div class="field"><div class="name">${name} ${riskTag(risk)}<span class="help">${esc(help)}</span></div>
    <div class="inputs">${ctl}</div></div>`;
  // a number cell of the World tab: what = skills | profile | relationship, who = lucia | jason (none for the relationship)
  function worldCell(o) {
    const {what, who, label, min, max, step, value, init, was, changed, extra = ''} = o, id = `w-${what}-${who || 'both'}`;
    return `<div class="cell narrow ${changed ? 'changed' : ''}"><label for="${id}">${esc(label)}</label><span class="with-unit"><input id="${id}" type="number" min="${min}" max="${max}" step="${step}"
      value="${esc(value)}" data-world="${what}" ${who ? `data-who="${who}"` : ''} data-init="${esc(init)}" data-was="${esc(was)}">${extra}</span>
      <span class="was">${changed ? 'was ' + esc(was) : ''}</span></div>`;
  }

  // the map's fog of war: every region Save Garage knows (fog.py)
  function mapGroup(s) {
    const F = S.world[s.file].fog, d = draftOf(s.file).world;
    let help = 'This part of the save can’t be read yet.', ctl = '';
    if (F?.problem) help = ERR['save_' + F.problem] || ERR.save_layout_changed;
    else if (F) {
      help = `Clears the fog of war from the regions Save Garage knows so far, about ${nf.format(F.known)} of the map’s ${nf.format(F.mapTotal)}; the others stay covered until you explore them. This save has ${nf.format(F.regions)} uncovered, and ${nf.format(F.missing)} of the known ones are still covered.`;
      ctl = d.fog ? '<span class="note">Will be revealed. Save edits to apply it.</span> <button class="btn small" data-act="world-undo" data-what="fog">Undo</button>'
        : `<button class="btn small" data-act="world-fill" data-what="fog" ${F.missing ? '' : 'disabled'}>${F.missing ? 'Reveal the map' : 'All known regions revealed'}</button>`;
    }
    return `<div class="group"><div class="section-head"><h3>Map</h3></div><div class="fields">${worldField('Reveal the map', 'untested', help, ctl)}</div></div>`;
  }

  // Lucia and Jason: special meter, skills, levels, capacity bars, criminal profile and a vest each, then their
  // relationship (player.py, levels.py, growth.py)
  function characterGroups(s) {
    const P = S.world[s.file].player, L = S.world[s.file].levels, G = S.world[s.file].growth, d = draftOf(s.file).world;
    if (!P) return '<div class="group"><div class="section-head"><h3>Jason and Lucia</h3></div><div class="callout">This part of the save can’t be read yet.</div></div>';
    return P.characters.map(c => characterGroup(P, c, d[c.key] || {}, L, d.levels?.[c.key] || {}, G, d.growth?.[c.key] || {})).join('') + relationshipGroup(P, d);
  }

  // strength, cardio and focus: the save counts levels from 0, the page from 1 as the game shows them
  const LEVELS = ['muscle', 'cardio', 'focus'];
  const LEVEL_LABEL = {muscle: 'Strength', cardio: 'Cardio', focus: 'Focus'};
  const LEVEL_REVIEW = {muscle: n => `Strength level (${n})`, cardio: n => `Cardio level (${n})`, focus: n => `Focus level (${n})`};
  const CAPACITIES = ['healthmax', 'staminamax', 'meleestaminamax', 'specialabilitymax'];
  const CAPACITY_LABEL = {healthmax: 'Health bar', staminamax: 'Stamina bar', meleestaminamax: 'Melee bar', specialabilitymax: 'Focus bar'};
  const CAPACITY_REVIEW = {healthmax: 'Health capacity', staminamax: 'Stamina capacity', meleestaminamax: 'Melee stamina capacity', specialabilitymax: 'Focus capacity'};
  function levelsField(L, key, dl) {
    const name = 'Strength, cardio and focus';
    if (!L || L.problem) return worldField(name, 'experimental', L ? ERR['save_' + L.problem] || ERR.save_layout_changed : 'This part of the save can’t be read yet.', '');
    const c = L.characters.find(x => x.key === key);
    if (!c || !c.levels.muscle) return '';
    // the level the game shows is the one outside the stats (levels.py); the stats copy follows it when a level is set
    const atMax = LEVELS.every(a => c.levels[a].value === c.levels[a].max && dl[a] == null);
    const cells = LEVELS.map(a => {
      const x = c.levels[a], now = x.value + 1;
      return worldCell({what: a, who: key, label: LEVEL_LABEL[a], min: 1, max: x.max + 1, step: 1, value: dl[a] != null ? dl[a] + 1 : now, init: now, was: String(now), changed: dl[a] != null});
    }).join('');
    return worldField(name, 'experimental', `Strength goes up to level ${L.max.muscle + 1}, cardio and focus up to level ${L.max.cardio + 1}. The game keeps each level in two places, and both are changed together.`,
      cells + `<button class="btn small" data-act="world-fill" data-what="levels" data-who="${key}" ${atMax ? 'disabled' : ''}>Max all</button>`);
  }

  // the length of the four bars: two copies in the attribute set and the points and rank in the stats, all written
  // together (growth.py). A save where those copies disagree is still offered, and all four are set alike.
  function capacityField(G, key, dg) {
    const name = 'Health, stamina, melee and focus bars';
    if (!G || G.problem) return worldField(name, 'experimental', G ? ERR['save_' + G.problem] || ERR.save_layout_changed : 'This part of the save can’t be read yet.', '');
    const c = G.characters.find(x => x.key === key);
    if (!c) return '';
    const atMax = CAPACITIES.every(q => c.capacities[q]?.value === G.max && dg[q] == null);
    const cells = CAPACITIES.map(q => {
      const x = c.capacities[q], now = x?.value;
      return worldCell({what: q, who: key, label: CAPACITY_LABEL[q], min: 0, max: G.max, step: 1, value: dg[q] ?? now,
        init: now, was: String(now), changed: dg[q] != null});
    }).join('');
    return worldField(name, 'tested', `The game keeps a capacity in four places, and all four are set together. ${G.max} is the highest value the game writes; the bars are separate from the levels above and from the special meter.`,
      cells + `<button class="btn small" data-act="world-fill" data-what="capacities" data-who="${key}" ${atMax ? 'disabled' : ''}>Max all</button> `
        + `<button class="btn small" data-act="world-fill" data-what="everything" data-who="${key}">Max everything</button>`);
  }

  function characterGroup(P, c, dc, L, dl, G, dg) {
    const pending = (what, text) => `<span class="note">${text} Save edits to apply it.</span> <button class="btn small" data-act="world-undo" data-what="${what}" data-who="${c.key}">Undo</button>`;
    let rows = '';
    if (c.attributesProblem || !c.skills) rows += worldField('Special meter and skills', 'experimental', ERR['save_' + c.attributesProblem] || ERR.save_layout_changed, '');
    else {
      const full = c.meter >= P.meterFull, lo = Math.min(...c.skills), hi = Math.max(...c.skills), now = lo === hi ? String(lo) : `${lo} to ${hi}`;
      rows += worldField('Special meter', 'untested', `Now ${c.meter}. Attribute slot ${P.meterSlot}, which other editors call the special ability meter; the game’s own name for it isn’t known. Filling it sets ${P.meterFull}, a value the game writes there itself.`,
        dc.meter ? pending('meter', 'Will be filled.') : `<button class="btn small" data-act="world-fill" data-what="meter" data-who="${c.key}" ${full ? 'disabled' : ''}>${full ? 'Already full' : `Fill to ${P.meterFull}`}</button>`);
      rows += worldField('Skills', 'experimental', `Now ${now}. Attribute slots ${P.skillSlots.slice(0, -1).join(', ')} and ${P.skillSlots.at(-1)}, which other editors call skills. Each is raised to the value you pick and never lowered. In the game’s own saves none is above ${P.skillChoices[0]}; GarlicSaves writes ${P.skillChoices[1]} and says it was tested in the game.`,
        worldCell({what: 'skills', who: c.key, label: 'Raise to', min: P.skillMin, max: P.skillMax, step: 1, value: dc.skills ?? lo, init: lo, was: now, changed: dc.skills != null,
          extra: P.skillChoices.map(v => `<button class="btn small" data-act="world-fill" data-what="skills" data-who="${c.key}" data-to="${v}">${v}</button>`).join('')}));
    }
    rows += levelsField(L, c.key, dl);
    rows += capacityField(G, c.key, dg);
    if (c.profile != null) {
      const was = nf2.format(c.profile);
      rows += worldField('Criminal profile', 'experimental', `Now ${was}. The game calls it the criminal profile: a temperament score behind the Professional, Hardened, Violent, Psycho and Irredeemable profiles in the Jason & Lucia menu. Which score gives which profile isn’t known yet. Lucia starts a new game at ${nf.format(P.profileNewGame)}; saves written by the game hold ${nf.format(P.profileMin)} to ${nf2.format(P.profileMax)}.`,
        worldCell({what: 'profile', who: c.key, label: 'Score', min: P.profileMin, max: P.profileMax, step: 'any', value: dc.profile ?? Number(c.profile.toFixed(2)), init: Number(c.profile.toFixed(2)), was, changed: dc.profile != null}));
    }
    const V = c.vest || {};
    const vhelp = {can_add: `Wears no armour, and a vest is in the wardrobe. Adding it puts it on the way the game records a worn vest: armour ${nf.format(P.vestArmour)} of ${nf.format(P.vestArmour)}.`,
      worn: `Wears armour now, ${nf2.format(V.armour)} of ${nf2.format(V.max)}.` + (V.armour < V.max ? ' Fill armour above tops it up.' : ''), no_vest: ERR.save_no_vest}[V.state]
      || 'The armour in this save doesn’t look the way Save Garage expects, so it is left alone.';
    rows += worldField('Vest', 'experimental', vhelp, V.state !== 'can_add' ? '' : dc.vest ? pending('vest', 'Will be added.')
      : `<button class="btn small" data-act="world-fill" data-what="vest" data-who="${c.key}">Add a vest</button>`);
    return `<div class="group"><div class="section-head"><h3>${esc(c.name)}</h3></div><div class="fields">${rows}</div></div>`;
  }

  function relationshipGroup(P, d) {
    const R = P.relationship || {};
    let help, ctl = '';
    if (R.problem) help = (R.value != null ? `Now ${R.value}. ` : '') + (ERR['save_' + R.problem] || ERR.save_layout_changed);
    else {
      help = `Now ${R.value}. At this point in the story the game keeps it from ${R.lowerCap} to ${R.cap}, so that is the range here. The relationship level the game shows is stored on its own and isn’t changed.`;
      ctl = worldCell({what: 'relationship', label: 'Score', min: R.lowerCap, max: R.cap, step: 1, value: d.relationship ?? R.value, init: R.value, was: String(R.value), changed: d.relationship != null});
    }
    return `<div class="group"><div class="section-head"><h3>Jason and Lucia</h3></div><div class="fields">${worldField('Relationship', 'experimental', help, ctl)}</div></div>`;
  }

  function onWorld(el) {
    const s = slotOf(S.slot);
    if (!s || !S.world[s.file]) return;
    const w = S.world[s.file], d = draftOf(s.file).world, c = w.clock;
    const what = el.dataset.world, v = Number(el.value);
    if (what === 'hour' || what === 'minute') {
      const t = {hour: d.time?.hour ?? c.hour, minute: d.time?.minute ?? c.minute};
      t[what] = v;
      const ok = el.value !== '' && Number.isInteger(v) && v >= 0 && v <= (what === 'hour' ? 23 : 59);
      el.setAttribute('aria-invalid', ok ? 'false' : 'true');
      if (!ok) { delete d.time; }
      else if (t.hour === c.hour && t.minute === c.minute) delete d.time;
      else d.time = t;
    } else if (what === 'health') {
      const ok = el.value !== '' && v >= 1 && v <= w.healthMax;
      el.setAttribute('aria-invalid', ok ? 'false' : 'true');
      if (!ok || v === w.health) delete d.health; else d.health = v;
    } else if ((what === 'skills' || what === 'profile' || what === 'relationship') && w.player) {
      const who = el.dataset.who, c = w.player.characters.find(x => x.key === who);
      const ok = el.value.trim() !== '' && Number.isFinite(v) && (what === 'profile' || Number.isInteger(v)) && v >= Number(el.min) && v <= Number(el.max);
      el.setAttribute('aria-invalid', ok ? 'false' : 'true');
      // skills are only ever raised, so a value at or below the lowest one changes nothing; the profile is a float32 in the save
      const same = what === 'skills' ? v <= Math.min(...c.skills) : what === 'profile' ? Math.fround(v) === Math.fround(c.profile) : v === w.player.relationship.value;
      if (what === 'relationship') { if (!ok || same) delete d.relationship; else d.relationship = v; }
      else {
        const ch = d[who] || {};
        if (!ok || same) delete ch[what]; else ch[what] = v;
        if (Object.keys(ch).length) d[who] = ch; else delete d[who];
      }
      mark(el.closest('.cell'), ok && !same, el);
    } else if (LEVELS.includes(what) && w.levels?.characters) {
      // the page shows levels from 1, the save and the drafts hold them from 0
      const who = el.dataset.who, x = w.levels.characters.find(c => c.key === who)?.levels?.[what];
      if (!x) return;
      const ok = el.value.trim() !== '' && Number.isInteger(v) && v >= 1 && v <= x.max + 1;
      el.setAttribute('aria-invalid', ok ? 'false' : 'true');
      const same = v - 1 === x.value;
      const all = d.levels || {}, ch = all[who] || {};
      if (!ok || same) delete ch[what]; else ch[what] = v - 1;
      if (Object.keys(ch).length) all[who] = ch; else delete all[who];
      if (Object.keys(all).length) d.levels = all; else delete d.levels;
      mark(el.closest('.cell'), ok && !same, el);
    } else if (CAPACITIES.includes(what) && w.growth?.characters) {
      const who = el.dataset.who, x = w.growth.characters.find(c => c.key === who)?.capacities?.[what];
      if (!x) return;
      const ok = el.value.trim() !== '' && Number.isInteger(v) && v >= Number(el.min) && v <= Number(el.max);
      el.setAttribute('aria-invalid', ok ? 'false' : 'true');
      const same = v === x.value;
      const all = d.growth || {}, ch = all[who] || {};
      if (!ok || same) delete ch[what]; else ch[what] = v;
      if (Object.keys(ch).length) all[who] = ch; else delete all[who];
      if (Object.keys(all).length) d.growth = all; else delete d.growth;
      mark(el.closest('.cell'), ok && !same, el);
    }
    renderPending(); renderCounts();
  }

  // ---- save data: every section, one number or true/false at a time
  function panelData(s) {
    const sd = S.sd[s.file], d = draftOf(s.file).raw;
    const head = `<div class="section-head"><h2>Save data</h2>${riskTag('danger')}
        <p>Every section of the save, with names where they’re known. A number that is the ID of an item, stat, place or vehicle the app knows shows that name under it. Numbers and true/false values can be changed one at a time; text, the story flow, heists, vehicle records and anything another tab handles stay read-only. Most of these values have unknown meanings, so change one thing, send the save and check it loads.</p></div>`;
    if (!sd.cur) {
      return head + `<table class="raw"><thead><tr><th>Section</th><th>Size</th><th></th></tr></thead><tbody>${sd.sections.map(x => `
        <tr><td class="key"><span data-no-i18n>${esc(x.name || '0x' + x.hash)}</span><small>0x${x.hash}${x.readOnly ? ', read-only: ' + esc(x.readOnly) : x.risky ? ', not recommended' : ''}</small></td>
          <td>${nf.format(x.bytes)} bytes</td><td><button class="btn small" data-act="sd-open" data-section="${x.hash}" data-path="[]">Open</button></td></tr>`).join('')}</tbody></table>`;
    }
    const n = sd.node, sec = sd.sections.find(x => x.hash === sd.cur.section);
    const crumbs = [`<button class="btn small" data-act="sd-home">Sections</button>`, `<button class="btn small" data-act="sd-open" data-section="${sd.cur.section}" data-path="[]">${esc(sec?.name || '0x' + sd.cur.section)}</button>`]
      .concat(sd.cur.path.map((p, i) => `<button class="btn small" data-act="sd-open" data-section="${sd.cur.section}" data-path='${esc(JSON.stringify(sd.cur.path.slice(0, i + 1)))}'>${esc(String(sd.cur.labels[i] ?? p))}</button>`));
    if (!n) return head + `<div class="crumbs">${crumbs.join(' ')}</div><div class="empty">Reading…</div>`;
    const ro = n.readOnly;
    const rows = n.items.map(x => {
      const path = [...n.path, x.key], k = rawKey(n.section, path), dr = d[k];
      let cell;
      if (x.kind === 'object' || x.kind === 'array') cell = `<button class="btn small" data-act="sd-open" data-section="${n.section}" data-path='${esc(JSON.stringify(path))}' data-label="${esc(String(x.label))}">${x.kind === 'array' ? `Open, ${nf.format(x.count)} items` : `Open, ${nf.format(x.count)} fields`}</button>`;
      else if (ro || x.readOnly || !['int', 'float', 'bool'].includes(x.kind)) cell = `<span class="lock">${esc(x.raw)}${x.readOnly ? `, read-only: ${esc(x.readOnly)}` : ''}</span>`;
      else if (x.kind === 'bool') { const on = dr ? dr.newValue : x.raw === 'true';
        cell = `<label class="toggle"><input type="checkbox" data-raw="1" data-section="${n.section}" data-path='${esc(JSON.stringify(path))}' data-orig="${esc(x.raw)}" data-label="${esc(String(x.label))}" ${on ? 'checked' : ''}> ${on ? 'true' : 'false'}</label>`; }
      else cell = `<input type="number" step="any" ${x.min != null ? `min="${x.min}" max="${x.max}"` : ''} data-raw="1" data-kind="${x.kind}" data-section="${n.section}" data-path='${esc(JSON.stringify(path))}' data-orig="${esc(x.raw)}" data-label="${esc(String(x.label))}" value="${esc(dr ? String(dr.newValue) : x.raw)}">`;
      return `<tr class="${dr ? 'changed' : ''}"><td class="key" data-no-i18n>${esc(String(x.label))}${typeof x.key === 'string' && x.label !== x.key ? `<small>${esc(x.key)}</small>` : ''}</td><td>${esc(x.kind)}</td><td>${cell}${x.means ? `<small class="means">${esc(x.means.kind)}: ${esc(x.means.text)}</small>` : ''}</td></tr>`;
    }).join('');
    const more = n.total > n.offset + n.items.length ? `<div class="more"><button class="btn small" data-act="sd-more">Show more (${nf.format(n.total - n.offset - n.items.length)} left)</button></div>` : '';
    return head + `<div class="crumbs">${crumbs.join(' ')}</div>${ro ? `<div class="callout">Read-only: ${esc(ro)}.</div>` : n.risky ? '<div class="callout">Not recommended: this section is tied to the story or its meaning isn’t known.</div>' : ''}
      <table class="raw"><thead><tr><th>Field</th><th>Type</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>${more}`;
  }

  async function sdOpen(file, section, path, labelText, append) {
    const sd = S.sd[file];
    if (!append) {
      const same = sd.cur && sd.cur.section === section;
      const labels = same ? sd.cur.labels.slice(0, path.length) : [];
      if (labelText && path.length) labels[path.length - 1] = labelText;
      sd.cur = {section, path, labels};
      sd.node = null; S.mainKey = ''; renderMain();
    }
    const offset = append ? sd.node.offset + sd.node.items.length : 0;
    try {
      const n = await api('/api/savedata?file=' + encodeURIComponent(file) + '&section=' + section + '&path=' + encodeURIComponent(JSON.stringify(path)) + '&offset=' + offset);
      if (append) { n.items = sd.node.items.concat(n.items); n.offset = sd.node.offset; }
      sd.node = n;
    } catch (e) { toast(ERR[e.code] || ERR.internal); }
    S.mainKey = ''; renderMain();
  }

  function onRaw(el) {
    const s = slotOf(S.slot);
    if (!s) return;
    const d = draftOf(s.file).raw, path = JSON.parse(el.dataset.path), k = rawKey(el.dataset.section, path);
    let nv;
    if (el.type === 'checkbox') { nv = el.checked; const lab = el.closest('label'); if (lab && lab.lastChild?.nodeType === 3) lab.lastChild.textContent = ' ' + String(nv); }
    else {
      nv = Number(el.value);
      const ok = el.value.trim() !== '' && Number.isFinite(nv) && (el.dataset.kind !== 'int' || Number.isInteger(nv))
        && (el.min === '' || nv >= Number(el.min)) && (el.max === '' || nv <= Number(el.max));
      el.setAttribute('aria-invalid', ok ? 'false' : 'true');
      if (!ok) { delete d[k]; renderPending(); renderCounts(); if (el.max !== '') toast(`This value can be ${el.min} to ${el.max}.`); return; }
    }
    const orig = el.dataset.orig;
    const same = el.type === 'checkbox' ? String(nv) === orig : Number(orig) === nv;
    if (same) delete d[k];
    else d[k] = {section: el.dataset.section, path, value: orig, newValue: nv, label: el.dataset.label};
    el.closest('tr')?.classList.toggle('changed', !same);
    renderPending(); renderCounts();
  }

  async function setStunts(file, ids) {
    const d = draftOf(file);
    for (const k of S.stuntKeys[file] || []) delete d.stats[k];
    S.stuntKeys[file] = new Set();
    S.stuntSel[file] = new Set(ids);
    if (ids.length) d.completion.stuntDiscovery = [...ids]; else delete d.completion.stuntDiscovery;
    if (ids.length) {
      try {
        const r = await api('/api/stunt-edits', {file, groups: ids});
        for (const e of r.edits) { const k = `${e.group}:${e.row}`; d.stats[k] = e; S.stuntKeys[file].add(k); }
      } catch (e) { S.stuntSel[file] = new Set(); toast(ERR[e.code] || ERR.internal); }
    }
    S.mainKey = ''; renderMain(); renderPending(); renderCounts();
  }

  function panelTrophies() {
    return `<div class="section-head"><h2>Trophies</h2><p>What a save edit can and can’t do for trophies on a PS5 without a jailbreak.</p></div>
      <div class="facts">
        <div class="fact no"><span class="mark" aria-hidden="true"></span><div><h3>Trophies can’t be edited directly</h3><p>The PS5 keeps trophies outside the game save and syncs them to PSN. No public tool can write them on system software 14.23, and any “no jailbreak trophy unlocker” is a scam or malware.</p></div></div>
        <div class="fact yes"><span class="mark" aria-hidden="true"></span><div><h3>Money can help with two trophies the normal way</h3><p>Treat Yo Self needs $100,000 spent, and Little Boxes needs all eight garages, about $160,000. Add money in the Money tab, send the save back, then spend it in the game. The game awards these itself.</p></div></div>
        <div class="fact maybe"><span class="mark" aria-hidden="true"></span><div><h3>Counter trophies might pop after an edit</h3><p>About 16 trophies count things like collectibles, stunts, challenges and vehicles, and the Completion tab can now set many of those counters. If GTA VI re-checks its counters, one pushed past its target could unlock the next time it goes up in play. Nobody has tested this on GTA VI yet, and the game may only award a trophy at the moment the real thing happens.</p></div></div>
        <div class="fact maybe"><span class="mark" aria-hidden="true"></span><div><h3>Story trophies need missions, and the Platinum needs play</h3><p>Mission progress is spread across many unnamed values, and getting them wrong can lock a mission later. About 18 trophies are one-off moments you have to play, so editing can’t finish the Platinum.</p></div></div>
        <div class="fact no"><span class="mark" aria-hidden="true"></span><div><h3>Trophy sites can flag save edits</h3><p>PSNProfiles’ rules list save editors as a reason to flag a trophy list, even when the game itself awarded the trophy. Sony’s terms forbid modifying game data, though no ban for single-player save edits has been reported. Never give your PSN login to a trophy service.</p></div></div>
      </div>`;
  }

  // ---- after the edit view renders: load what it needs
  async function afterEdit() {
    const s = slotOf(S.slot);
    if (!s) return;
    const file = s.file;
    if (S.tab !== 'money' && S.tab !== 'trophies' && !S.detail[file]) {
      try { S.detail[file] = await api('/api/slot?file=' + encodeURIComponent(file)); } catch (e) { S.detail[file] = {failed: e.code || 'request_failed', featured: [], ammo: []}; }
      S.mainKey = ''; renderMain(); return;
    }
    if (S.tab === 'all' && !S.stats[file]) {
      try { S.stats[file] = await api('/api/stats?file=' + encodeURIComponent(file)); } catch (e) { S.stats[file] = {failed: e.code || 'request_failed'}; }
      S.mainKey = ''; renderMain(); return;
    }
    if (S.tab === 'data' && !S.sd[file]) {
      try { S.sd[file] = {sections: (await api('/api/savedata?file=' + encodeURIComponent(file))).sections, cur: null, node: null}; }
      catch (e) { S.sd[file] = {failed: e.code || 'request_failed'}; }
      S.mainKey = ''; renderMain(); return;
    }
    if (S.tab === 'world' && !S.world[file]) {
      try { S.world[file] = await api('/api/world?file=' + encodeURIComponent(file)); } catch (e) { S.world[file] = {failed: e.code || 'request_failed'}; }
      S.mainKey = ''; renderMain(); return;
    }
    if (S.tab === 'completion' && !S.comp[file]) {
      try { S.comp[file] = await api('/api/completion?file=' + encodeURIComponent(file)); } catch (e) { S.comp[file] = {failed: e.code || 'request_failed'}; }
      S.mainKey = ''; renderMain(); return;
    }
    renderCounts();
  }

  function renderCounts() {
    const d = draftOf(S.slot);
    const n = {money: Object.keys(d.money).length, ammo: Object.keys(d.ammo).length + gunCount(d.guns), stats: 0, all: 0};
    const feat = new Set((S.detail[S.slot]?.featured || []).flatMap(f => f.entries.map(e => `${e.group}:${e.row}`)));
    const stunt = S.stuntKeys[S.slot] || new Set();
    n.completion = compCount(d.completion); n.world = worldCount(d.world); n.data = Object.keys(d.raw || {}).length;
    for (const k of Object.keys(d.stats)) n[stunt.has(k) ? 'completion' : feat.has(k) ? 'stats' : 'all']++;
    for (const el of $$('[data-count]')) el.textContent = n[el.dataset.count] || '';
  }

  // ------------------------------------------------------------ send back
  // another user of the PS5 the saves are going to (state.users), or null for the account they came from
  const sendTarget = st => (st.users || []).find(u => u.id === S.sendTo && u.id !== String(st.user?.id || '').toLowerCase()) || null;
  function accountChoice(st) {
    const others = (st.users || []).filter(u => u.id !== String(st.user?.id || '').toLowerCase());
    if (!others.length) return '';
    const target = sendTarget(st);
    return `<div class="panel"><h3>Send to another account on this PS5</h3>
      <p class="detail" style="margin:6px 0 10px">The saves are signed for the account you pick, through GarlicSaves, before they go to the PS5. The account you downloaded from keeps its own saves.</p>
      <div class="saves" role="group" aria-label="Send to"><button class="save" data-act="sendto" data-user="" aria-pressed="${!target}"><span class="t" data-no-i18n>${esc(st.user?.name || '')}</span></button>${others.map(u => `
        <button class="save" data-act="sendto" data-user="${esc(u.id)}" aria-pressed="${target?.id === u.id}"><span class="t" data-no-i18n>${esc(u.name)}</span></button>`).join('')}</div></div>`;
  }

  function viewSend() {
    const st = S.state;
    const job = st.job || {};
    const target = sendTarget(st);
    const done = job.kind === 'upload' && job.stage === 'uploaded';
    const edited = (st.slots || []).filter(x => x.modified);
    const summary = edited.length ? `<div class="panel"><h3>What’s being sent</h3><ul class="review" style="max-height:none;margin-top:8px">${edited.map(x =>
      (x.changes || []).slice(0, 60).map(c => `<li><span>${esc(missionName(x))}: ${esc(changeLabel(c))}</span><span>${c.count > 1 ? `${nf.format(c.count)} changes` : c.from === '' || c.from == null ? esc(fmtChange(c.to)) : `${esc(fmtChange(c.from))} to ${esc(fmtChange(c.to))}`}</span></li>`).join('')
      + ((x.changes || []).length > 60 ? `<li><span>${esc(missionName(x))}: and ${nf.format(x.changes.length - 60)} more changes</span><span></span></li>` : '') ||
      `<li><span>${esc(missionName(x))}</span><span>edited</span></li>`).join('')}</ul></div>` : '';
    const all = sortedSlots(st);
    const total = Math.max(st.fileCount || 0, all.length);
    const allList = all.length ? `<div class="panel"><h3>All ${total} saves are sent back</h3>
      <p class="detail" style="margin:6px 0 10px">Everything the PS5 had for ${esc(st.user?.name || 'this account')} in GTA VI goes back, not only the save you edited. Edited saves carry your changes. The others are sent exactly as downloaded.</p>
      <ul class="review" style="max-height:none;margin-top:8px">${all.map(x => `<li><span>${esc(label(x))}: ${esc(missionName(x))}</span><span>${x.modified ? 'edited' : 'unchanged'}</span></li>`).join('')}${total > all.length ? `<li><span>${total - all.length} other file${total - all.length > 1 ? 's' : ''}</span><span>unchanged</span></li>` : ''}</ul></div>` : '';
    if (done) {
      return `<section class="title-card"><span class="chip">Done</span><h1>Your save is back on the PS5</h1>
          <p>Start GTA VI and load the save you edited. Check the values in the game before you play on.</p></section>
        <div class="stack">
          <div class="panel stack"><h3>If the save won’t load</h3>
            <ol class="how"><li><strong>Delete the GTA VI save on the PS5 again.</strong><span class="path">${PS5_DELETE}.</span></li>
              <li><strong>Click Put the originals back.</strong><span class="path">This swaps your untouched saves back in.</span></li>
              <li><strong>Send the save to the PS5 again from this page.</strong></li></ol>
            <div class="row"><button class="btn danger" data-act="restore" ${running() ? 'disabled' : ''}>Put the originals back</button>
              <button class="btn" data-act="go" data-view="edit">Edit more</button></div></div>
          ${jobBox('restore')}
        </div>`;
    }
    if (!st.readyToUpload && !target) {
      return `<section class="title-card"><span class="chip">Step ${stepNo('send', st)}</span><h1>Nothing to send yet</h1><p>Save some edits first. They’ll wait here until you send them.</p></section>
        <div class="row"><button class="btn primary" data-act="go" data-view="edit">Edit a save</button></div>${accountChoice(st)}${jobBox('restore upload')}`;
    }
    return `
      <section class="title-card"><span class="chip">Step ${stepNo('send', st)}</span><h1>Send your save back</h1>
        <p>Your edits are encrypted and waiting. The PS5 won’t overwrite a save, so the old ones have to be deleted first. Every save of this account comes back, and the originals stay backed up on this computer.</p></section>
      <div class="stack">
        ${accountChoice(st)}
        ${summary}
        ${allList}
        <ol class="how">
          <li><strong>Optional: upload your GTA VI save to PS Plus cloud storage.</strong><span class="path">That gives you a second backup. Turn off auto-sync for GTA VI until you know the edited save works.</span></li>
          <li><strong>${target ? 'Switch the PS5 to that account and delete its GTA VI save.' : 'Delete the GTA VI save on the PS5.'}</strong><span class="path">${PS5_DELETE}, then pick Grand Theft Auto VI.</span>
            <label class="check" style="margin-top:10px"><input type="checkbox" data-act="deleted" ${S.deleted ? 'checked' : ''}><span>I deleted the GTA VI save on my PS5</span></label></li>
          <li><strong>Click Send save to PS5, then start the transfer on the PS5.</strong><span class="path">${PS5_TRANSFER}, then pick “Save Garage” and choose Start Transfer.</span></li>
        </ol>
        <div class="row"><button class="btn primary" data-act="upload" ${S.deleted && !running() ? '' : 'disabled'}>Send save to PS5</button>
          <button class="btn danger" data-act="restore" ${running() ? 'disabled' : ''}>Undo all edits</button></div>
        ${jobBox('upload restore')}
      </div>`;
  }

  const changeLabel = c => c.label || ({bank: 'Bank account', savings: 'Family Savings', cash: 'Cash'})[c.kind] || c.kind;
  const fmtChange = v => typeof v === 'boolean' ? (v ? 'yes' : 'no') : typeof v === 'number' ? (Number.isInteger(v) ? nf.format(v) : nf2.format(v)) : String(v);

  // ------------------------------------------------------------ job box
  // a PS5 asked for IPv6 data (issue #7) and the adapter carrying its connection has no link-local IPv6 address
  // (job.hint from upload_network_hint, PR #14): how to turn it on, for the computer's system. The upload keeps
  // waiting, so the player can turn IPv6 on and pick Save Garage on the PS5 again.
  function uploadNetworkHelp(hint) {
    if (hint?.code === 'ipv6_data_unreached') {
      return `<div class="callout ipv6" role="status"><strong>The PS5 connected, but the IPv6 data connection has not reached TCP port 1005.</strong>
        <div>Use the same home network on both devices. Check for guest Wi-Fi or client isolation.</div>
        ${hint.platform === 'win32' ? '<div>On Windows, see app/docs/transfer-network.md for the private-network firewall repair.</div>' : ''}
        <div>Keep this page open. Search again on the PS5 and select Save Garage.</div></div>`;
    }
    if (hint?.code !== 'local_ipv6') return '';
    const steps = hint.platform === 'win32'
      ? 'Press Win + R, open ncpa.cpl, open the adapter properties and check Internet Protocol Version 6 (TCP/IPv6).'
      : hint.platform === 'darwin'
        ? 'Open System Settings → Network → your connection → Details → TCP/IP. Set Configure IPv6 to Automatically or Link-local only.'
        : 'Open the settings for this network connection and enable automatic or link-local IPv6.';
    return `<div class="callout ipv6" role="status"><div><strong>This transfer needs IPv6 on the local network.</strong>
      ${hint.adapter ? `<div><span>Network adapter</span>: <b data-no-i18n>${esc(hint.adapter)}</b></div>` : ''}
      <div>${esc(steps)}</div><div>Keep this page open. Search again on the PS5 and select Save Garage.</div></div></div>`;
  }

  function renderJob() {
    const st = S.state;
    if (!st) return;
    const job = st.job || {};
    for (const box of $$('[data-job]')) {
      const kinds = box.dataset.job.split(' ');
      const err = S.localError;
      let html = '';
      if (err) {
        html = `<div class="job err"><div class="stage">${esc(ERR[err.code] || ERR.internal)}</div>${err.detail ? `<div class="detail">${esc(err.detail)}</div>` : ''}${signinFix(err.code, kinds[0])}</div>`;
      } else if (kinds.includes(job.kind) && job.status !== 'idle') {
        const stage = STAGE[job.stage] || job.stage || '';
        if (job.status === 'running') {
          const p = job.progress;
          const pct = p && p.total ? Math.round(100 * p.files / p.total) : null;
          html = `<div class="job"><div class="stage">${esc(stage)}</div>
            ${p ? `<div class="detail">${p.total ? `File ${p.files} of ${p.total}` : `${p.files} files so far`}</div>` : ''}
            ${job.stage === 'key_rate_wait' && job.wait != null ? `<div class="detail">Trying again in ${esc(job.wait)} s</div>` : ''}
            <div class="bar ${pct != null ? 'fixed' : ''}"><span ${pct != null ? `style="width:${pct}%"` : ''}></span></div>
            ${job.needPower ? `<div class="power"><svg viewBox="0 0 48 48" aria-hidden="true"><path d="M15 12a16 16 0 1 0 18 0"/><line x1="24" y1="5" x2="24" y2="22"/></svg>
              <div><strong>Hold the PS5 power button for about one second</strong>Then let go. The PS5 beeps and restarts into transfer mode. Holding it longer turns the PS5 off. You have about 5 minutes.</div></div>` : ''}
            ${job.stage === 'choose_account' && job.accounts ? `<div class="accounts"><strong>Which account’s save do you want to edit?</strong>
              <div class="row">${job.accounts.map(a => `<button class="btn primary" data-act="choose-account" data-owner="${esc(a.id)}">${esc(a.name)}</button>`).join('')}</div>
              <div class="detail">These accounts each have a GTA VI save on this PS5.</div></div>` : ''}
            ${uploadNetworkHelp(job.hint)}
            ${job.hint === 'console_has_save' ? '<div class="callout" style="margin-top:12px">The PS5 still has a GTA VI save, so it has nothing to receive. Delete the save on the PS5, then open Data Transfer again.</div>' : ''}
            ${['waiting_console', 'pair_waiting_console', 'connecting', 'key_retry', 'key_rate_wait', 'need_power', 'choose_account'].includes(job.stage) ? '<div class="row" style="margin-top:10px"><button class="link" data-act="cancel">Cancel</button></div>' : ''}
            ${logBlock(job)}</div>`;
        } else if (job.status === 'error') {
          const code = job.error?.code || 'internal';
          const detail = job.error?.detail || '';
          const perm = /PermissionError/.test(detail);
          html = `<div class="job err"><div class="stage">${esc(ERR[code] || ERR.internal)}</div>
            ${perm ? '<div class="detail">This computer isn’t allowed to use ports 1004 to 1006. On Linux, run sudo sysctl -w net.ipv4.ip_unprivileged_port_start=1004 in a terminal, then try again.</div>' : ''}
            ${detail && !perm ? `<div class="detail">${esc(detail)}</div>` : ''}${signinFix(code, job.kind)}${logBlock(job)}</div>`;
        } else if (job.status === 'done') {
          html = `<div class="job ok"><div class="stage">${esc(stage)}</div></div>`;
        }
      }
      if (box.dataset.html !== html) {           // only real changes: the page translates what it shows, and keeps focus
        const open = box.querySelector('details')?.open;
        box.innerHTML = html; box.dataset.html = html;
        if (open && box.querySelector('details')) box.querySelector('details').open = true;
      }
    }
  }

  // for an error a sign-in fixes: GarlicSaves refused the sign-in (Sign in again), or there is none yet; kind: the job's
  // kind or the step's job box, to come back to that step once signed in
  function signinFix(code, kind) {
    if (!S.state?.garlic) return '';
    const back = SIGNIN_BACK[kind] || '';
    if (['key_disabled', 'garlic_key_disabled'].includes(code)) return `<div class="row" style="margin-top:10px"><button class="btn small primary" data-act="signin" data-back="${back}">Sign in again</button></div>`;
    if (code === 'not_signed_in') return `<div class="row" style="margin-top:10px"><button class="btn small primary" data-act="signin" data-back="${back}">Sign in to GarlicSaves</button></div>`;
    return '';
  }

  const logBlock = job => (job.log || []).length ? `<details class="log"><summary>Show details</summary><pre>${esc(job.log.map(l => l.m).join('\n'))}</pre></details>` : '';

  // ------------------------------------------------------------ pending bar
  function renderPending() {
    const st = S.state;
    const s = slotOf(S.slot);
    if (!st || viewFor(st) !== 'edit' || !s) { pendingEl.hidden = true; return; }
    const d = draftOf(s.file);
    const n = editCount(d);
    const isDirty = dirty(s);
    const busy = running();
    if (!n && !s.modified) { pendingEl.hidden = true; return; }
    const w = d.world || {}, now = S.world[s.file], P = now?.player, F = now?.fog;
    const who = k => P?.characters?.find(x => x.key === k);
    const worldList = [w.time && {label: 'Time of day', value: now ? `${two(now.clock.hour)}:${two(now.clock.minute)}` : '', newValue: `${two(w.time.hour)}:${two(w.time.minute)}`},
      w.health != null && {label: 'Health', value: now ? now.health : '', newValue: w.health},
      w.armour && {label: 'Armour', value: now ? now.armour : '', newValue: 'full'},
      w.fog && {label: 'Map regions uncovered', value: F ? F.regions : '', newValue: F ? F.regions + F.missing : 'all known'},
      ...['lucia', 'jason'].flatMap(k => {
        const e = w[k], c = who(k), name = c?.name || (k === 'lucia' ? 'Lucia' : 'Jason');
        return !e ? [] : [e.meter && {label: `Special meter (${name})`, value: c?.meter ?? '', newValue: P?.meterFull ?? 100},
          e.skills != null && {label: `Skills (${name})`, value: c?.skills ? Math.min(...c.skills) : '', newValue: e.skills},
          e.profile != null && {label: `Criminal profile (${name})`, value: c?.profile ?? '', newValue: e.profile},
          e.vest && {label: `Vest (${name})`, value: c?.vest?.armour ?? '', newValue: P?.vestArmour ?? 150}];
      }),
      ...Object.entries(w.levels || {}).flatMap(([k, ch]) => {
        const c = now?.levels?.characters?.find(x => x.key === k), name = c?.name || (k === 'lucia' ? 'Lucia' : 'Jason');
        return Object.entries(ch || {}).map(([a, v]) => ({label: LEVEL_REVIEW[a] ? LEVEL_REVIEW[a](name) : a, value: c?.levels?.[a] ? c.levels[a].value + 1 : '', newValue: v + 1}));
      }),
      ...Object.entries(w.growth || {}).flatMap(([k, ch]) => {
        const c = now?.growth?.characters?.find(x => x.key === k), name = c?.name || (k === 'lucia' ? 'Lucia' : 'Jason');
        return Object.entries(ch || {}).map(([q, v]) => ({label: `${CAPACITY_REVIEW[q] || q} (${name})`, value: c?.capacities?.[q]?.value ?? '', newValue: v}));
      }),
      w.relationship != null && {label: 'Relationship', value: P?.relationship?.value ?? '', newValue: w.relationship}].filter(Boolean);
    const cp = d.completion || {};
    const compList = [cp.compendium && {label: 'Compendium: ' + cp.compendium.groups.join(' and '), value: '', newValue: 'discovered'},
      cp.discovery && {label: 'Map: every shop and place', value: '', newValue: 'discovered'},
      cp.challenges && {label: 'Challenges: ' + (cp.challenges.categories === 'all' ? 'every category' : cp.challenges.categories.join(', ')), value: '', newValue: 'completed'},
      cp.gyms && {label: 'Gym memberships: ' + (cp.gyms.gyms === 'all' ? 'all' : cp.gyms.gyms.length), value: '', newValue: 'owned'},
      cp.activities && {label: 'Meditation spots: all, as ' + (cp.activities.character === 'jason' ? 'Jason' : 'Lucia'), value: '', newValue: 'completed'},
      cp.robberies && {label: 'Robberies: ' + cp.robberies.lines.join(', '), value: '', newValue: 'fully hit'},
      cp.fencing && {label: 'Fencing: ' + cp.fencing.lines.join(', '), value: '', newValue: 'completed'},
      cp.activities2 && {label: 'Activities: ' + cp.activities2.lines.join(', '), value: '', newValue: 'completed'},
      cp.hoops && {label: 'Basketball hoops: all', value: '', newValue: 'scored'},
      cp.vehicles && {label: 'Vehicle compendium: up to 200 base models', value: '', newValue: 'discovered'},
      cp.collectibles && {label: 'Collectibles: ' + cp.collectibles.categories.join(', '), value: '', newValue: 'found'},
      cp.cheats && {label: 'Cheat trackers', value: '', newValue: `${cp.cheats.trackers.length} completed`}].filter(Boolean);
    const gunList = Object.entries(d.guns || {}).filter(([, v]) => (v || []).length)
      .map(([k, v]) => ({label: `Guns added (${k === 'lucia' ? 'Lucia' : 'Jason'})`, value: '', newValue: v.length}));
    const list = [...Object.values(d.money), ...Object.values(d.ammo), ...gunList, ...Object.values(d.stats), ...worldList, ...Object.values(d.raw || {}), ...compList];
    const html = !n && s.modified && !isDirty
      ? `<div class="sum">Edits waiting to be sent<small><span data-no-i18n>${esc(missionName(s))}.</span> They were saved earlier. Send them to the PS5, or undo them on the Send back step.</small></div>
         <div class="row"><button class="btn primary" data-act="go" data-view="send">Go to send back</button></div>`
      : isDirty
      ? `<div class="sum">${n === 1 ? '1 change not saved yet' : `${n} changes not saved yet`}<small><span data-no-i18n>${esc(missionName(s))}.</span> Saving encrypts the save through GarlicSaves and gets it ready to send.</small></div>
         <div class="row"><button class="btn small" data-act="review">${S.reviewOpen ? 'Hide list' : 'Review'}</button>
           <button class="btn small" data-act="discard">Discard</button>
           <button class="btn primary" data-act="save" ${busy ? 'disabled' : ''}>${busy && st.job.kind === 'patch' ? 'Saving…' : 'Save edits to this save'}</button></div>`
      : `<div class="sum">Edits saved<small><span data-no-i18n>${esc(missionName(s))}.</span> ${n === 1 ? '1 change.' : `${n} changes.`} Edit another save, or send them back to the PS5.</small></div>
         <div class="row"><button class="btn small" data-act="review">${S.reviewOpen ? 'Hide list' : 'Review'}</button>
           <button class="btn primary" data-act="go" data-view="send">Go to send back</button></div>`;
    const review = S.reviewOpen ? `<ul class="review">${list.map(c => `<li><span>${esc(c.label || 'Change')}</span><span>${esc(fmtChange(c.value))} to ${esc(fmtChange(c.newValue))}</span></li>`).join('')}</ul>` : '';
    const job = st.job || {};
    const jobLine = job.kind === 'patch' && job.status !== 'idle' && !(job.status === 'done' && !isDirty)
      ? `<div style="flex-basis:100%">${job.status === 'error' ? `<span class="risk danger">${esc(ERR[job.error?.code] || ERR.internal)}</span>${signinFix(job.error?.code, 'patch')}` : `<span class="risk caution">${esc(STAGE[job.stage] || job.stage)}</span>`}</div>` : '';
    const full = html + jobLine + review;
    if (pendingEl.dataset.html !== full) { pendingEl.innerHTML = full; pendingEl.dataset.html = full; }
    pendingEl.hidden = false;
  }

  // ------------------------------------------------------------ input handling
  function onEdit(el) {
    const s = slotOf(S.slot);
    if (!s) return;
    const kind = el.dataset.edit;
    const bucket = kind === 'stat' ? 'stats' : kind;
    const key = el.dataset.key;
    const d = draftOf(s.file);
    const cellEl = el.closest('.cell') || el.closest('tr');
    let newValue, orig = JSON.parse(el.dataset.orig ?? 'null'), same;
    if (el.type === 'checkbox') {
      newValue = el.checked;
      orig = el.dataset.orig === '1';
      same = newValue === orig;
      const lab = el.closest('label');
      if (lab && lab.lastChild && lab.lastChild.nodeType === 3) lab.lastChild.textContent = ' ' + (el.closest('table') ? String(newValue) : (newValue ? 'Yes' : 'No'));
    } else {
      newValue = fromDisplay(el.value, el.dataset.unit, el.dataset.type);
      same = el.value.trim() === el.dataset.init;
      const max = Number(el.max), min = Number(el.min);
      const bad = !same && (newValue === null || (el.max !== '' && newValue > max * (el.dataset.unit === 'ms' ? 3600000 : el.dataset.unit === 'distance' ? 1000 : 1)) || newValue < (Number.isFinite(min) ? min : 0));
      el.setAttribute('aria-invalid', bad ? 'true' : 'false');
      if (bad) { delete d[bucket][key]; mark(cellEl, false, el); renderPending(); renderCounts(); return; }
    }
    if (same) delete d[bucket][key];
    else {
      const base = {value: orig, newValue, label: el.dataset.label || ''};
      d[bucket][key] = kind === 'stat'
        ? {group: el.dataset.group, row: +el.dataset.row, base: +el.dataset.base, qual: +el.dataset.qual, owner: +el.dataset.owner, ...base}
        : {inv: +el.dataset.inv, idx: +el.dataset.idx, ...base, ...(kind === 'money' && stacksOn(s.file, key) ? {stacks: true} : {})};
    }
    mark(cellEl, !same, el);
    if (kind === 'stat') updateTotal(el);
    renderPending();
    renderCounts();
  }

  function mark(cellEl, changed, el) {
    if (!cellEl) return;
    cellEl.classList.toggle('changed', changed);
    const was = cellEl.querySelector('.was');
    if (was) was.textContent = changed ? (el.type === 'checkbox' ? 'was ' + (el.dataset.orig === '1' ? 'yes' : 'no') : 'was ' + (el.dataset.was || el.dataset.init)) : '';
  }

  function updateTotal(el) {
    const wrap = el.closest('[data-spec]');
    const total = wrap && wrap.querySelector('[data-total]');
    if (!total) return;
    const ins = $$('input[data-edit]', wrap);
    const unit = ins[0]?.dataset.unit;
    const sum = ins.reduce((a, x) => a + (fromDisplay(x.value, x.dataset.unit, x.dataset.type) ?? JSON.parse(x.dataset.orig)), 0);
    total.value = toDisplay(sum, unit);
  }

  // ------------------------------------------------------------ events
  document.addEventListener('toggle', e => { const k = e.target?.dataset?.keep; if (k) S.keep[k] = e.target.open; }, true);
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-act]');
    if (!b || b.disabled) return;
    const a = b.dataset.act;
    if (a === 'deleted') { S.deleted = b.checked; const up = $('[data-act="upload"]'); if (up) up.disabled = !(S.deleted && !running()); return; }
    if (a === 'pick-exp') { S.compExp[S.slot] = b.checked; return; }
    if (a === 'update-auto') {                  // saved in data/config.json as autoUpdate
      const on = b.checked;
      S.updAuto = on;
      api('/api/update/settings', {auto: on}).then(u => { if (S.state) S.state.update = u; })
        .catch(e => toast(ERR[e.code] || ERR.internal)).finally(() => { S.updAuto = null; renderUpdate(); });
      return;
    }
    if (b.tagName === 'A') return;
    e.preventDefault();
    if (a === 'go') { S.localError = null; S.manualView = b.dataset.view; if (b.dataset.view !== 'signin') S.signinFor = null; S.mainKey = ''; renderRoute(); renderMain(); renderSigninLeft(); renderJob(); renderPending(); main.focus(); return; }
    if (a === 'discover') {
      S.searching = true; S.consoles = null; renderMain();
      act('/api/discover', {}, out => { S.consoles = out.consoles || []; }).finally(() => { S.searching = false; S.mainKey = ''; renderMain(); renderJob(); });
      return;
    }
    if (a === 'pick') { act('/api/console', {host: b.dataset.host}, st => { S.manualView = null; onState(st); }); return; }
    if (a === 'signin') { goSignIn(b.dataset.back, true); return; }
    if (a === 'signin-cancel') {
      act('/api/signin/cancel', {}, g => { if (S.state) S.state.garlic = g; S.mainKey = ''; renderMain(); renderSigninLeft(); });
      return;
    }
    if (a === 'signin-done') { S.manualView = null; S.signinFor = null; S.mainKey = ''; renderRoute(); renderMain(); renderJob(); renderPending(); main.focus(); return; }
    if (a === 'signout') {                      // forgets the key on this computer (config.json); refused while a task runs
      if (!confirm(T('Sign out of GarlicSaves? Save Garage forgets its key on this computer, and you’ll need to sign in again to pair, download, save edits or send saves back.'))) return;
      act('/api/signout', {}, g => { if (S.state) S.state.garlic = g; S.signinFor = null; S.mainKey = ''; renderStatus(); renderRoute(); renderMain(); });
      return;
    }
    // pairing, downloading, saving edits and sending need the GarlicSaves sign-in: without it, the sign-in step comes first
    if (['pair', 'download', 'upload'].includes(a) && mustSignIn(S.state)) { goSignIn(SIGNIN_BACK[a]); return; }
    if (a === 'pair') { act('/api/pair'); return; }
    if (a === 'download') { act('/api/download'); return; }
    if (a === 'choose-account') { act('/api/choose-account', {owner: b.dataset.owner}); return; }
    if (a === 'cancel') { act('/api/cancel'); return; }
    if (a === 'update-check') {
      api('/api/update/check', {}).then(u => { if (S.state) { S.state.update = u; renderUpdate(); } }).catch(e => toast(ERR[e.code] || ERR.internal));
      return;
    }
    if (a === 'update-restart') {               // Save Garage starts again and installs the update; refused while a task runs
      if (running()) return;
      const unsaved = (S.state?.slots || []).some(x => editCount(draftOf(x.file)) && dirty(x));
      if (unsaved && !confirm(T('Restart Save Garage now? Edits you haven’t saved here are lost.'))) return;
      const from = S.state?.version, host = S.state?.console?.host || null;
      api('/api/update/restart', {}).then(() => { S.restarting = {from, host, down: false, at: Date.now()}; renderUpdate(); renderStatus(); })
        .catch(e => toast(ERR[e.code] || ERR.internal));
      return;
    }
    if (a === 'upload') { const to = sendTarget(S.state); act('/api/upload', to ? {to: to.id} : {}); return; }
    if (a === 'restore') {
      if (confirm(T('Put the original saves back? Every edit you saved here is undone. You still need to send the save to the PS5 afterwards.'))) act('/api/restore', {}, () => { S.drafts = {}; });
      return;
    }
    if (a === 'slot') { S.slot = b.dataset.file; S.reviewOpen = false; S.mainKey = ''; renderMain(); renderPending(); return; }
    if (a === 'sendto') { S.sendTo = b.dataset.user || null; S.mainKey = ''; renderMain(); return; }
    if (a === 'tab') { S.tab = b.dataset.tab; S.mainKey = ''; renderMain(); return; }
    if (a === 'unstick') {      // move bank money out of the Savings boxes an older version used: same or lower total, saved explicitly
      const s = slotOf(S.slot), d = draftOf(s.file);
      d.money[`${b.dataset.inv}:${b.dataset.idx}`] = {inv: +b.dataset.inv, idx: +b.dataset.idx, value: +b.dataset.value, newValue: +b.dataset.to, label: 'Bank account (made spendable)'};
      toast('The bank money will be moved into the bank’s own boxes when you save edits.');
      renderPending(); renderCounts();
      return;
    }
    if (a === 'unstack') {      // a bank past its own boxes, the rest in extra stacks: set it to what the boxes hold, stacks emptied
      const field = b.closest('.field'), input = field?.querySelector('input[data-edit="money"]'), box = field?.querySelector('[data-stacks]');
      if (!input) return;
      if (box?.checked) { box.checked = false; onStacks(box); }
      input.value = b.dataset.to; onEdit(input);
      const c = draftOf(S.slot).money[input.dataset.key];
      if (c) c.label = 'Bank account (made spendable)';
      toast(`The bank will be set to $${nf.format(+b.dataset.to)}, all in its own money boxes, when you save edits.`);
      return;
    }
    if (a === 'fill') {
      const input = b.parentElement.querySelector('input[type="number"]');
      if (input) { input.value = b.dataset.to; onEdit(input); }
      return;
    }
    if (a === 'line-pick') {
      const file = S.slot, key = b.dataset.line, on = !linePicked(file, key);
      if (LINE_PICK[key]?.[0] === 'stunts') { setStunts(file, on ? openStunts(file) : []); return; }
      setLine(file, key, on);
      S.mainKey = ''; renderMain(); renderPending(); renderCounts();
      return;
    }
    if (a === 'pick-all') { pickEverything(S.slot, !!S.compExp[S.slot]); return; }
    if (a === 'pick-none') { clearPicks(S.slot); return; }
    if (a === 'coll-add' || a === 'coll-undo') {
      const s = slotOf(S.slot), d = draftOf(s.file).completion, v = b.dataset.value;
      const cur = new Set(d.collectibles?.categories || []);
      if (a === 'coll-add') cur.add(v); else cur.delete(v);
      const exp = [...cur].filter(k => ['bookswaps', 'magazinestyles', 'flamingos'].includes(k));
      if (cur.size) d.collectibles = {categories: [...cur], card_items: 'skip', watch_items: 'skip', ...(exp.length ? {experimental: exp} : {})};
      else delete d.collectibles;
      S.mainKey = ''; renderMain(); renderPending(); renderCounts();
      return;
    }
    if (a === 'act-line' || a === 'act-line-undo') {
      const s = slotOf(S.slot), d = draftOf(s.file).completion, C = S.comp[s.file];
      const lines = C.activities2.lines, v = b.dataset.value;
      const cur = new Set(d.activities2?.lines || []);
      if (a === 'act-line') { if (v === 'all') lines.filter(l => l.counter < l.of && l.key !== 'bret').forEach(l => cur.add(l.key)); else cur.add(v); } else cur.delete(v);
      if (cur.size) {
        const level = {};
        for (const k of cur) level[k] = (lines.find(l => l.key === k) || {}).confidence === 'verified' ? 'full' : 'counter';
        d.activities2 = {lines: [...cur], level, unverified_ok: cur.has('bret')};
      } else delete d.activities2;
      S.mainKey = ''; renderMain(); renderPending(); renderCounts();
      return;
    }
    if (a === 'comp-line' || a === 'comp-line-undo') {
      const s = slotOf(S.slot), d = draftOf(s.file).completion, C = S.comp[s.file];
      const feat = b.dataset.feature, v = b.dataset.value, all = C[feat].lines.filter(l => !l.done).map(l => l.key);
      const cur = new Set(d[feat]?.lines || []);
      if (a === 'comp-line') { if (v === 'all') all.forEach(k => cur.add(k)); else cur.add(v); } else cur.delete(v);
      if (cur.size) d[feat] = feat === 'robberies' ? {lines: [...cur], vaults: 'large'} : {lines: [...cur], character: 'lucia'}; else delete d[feat];
      S.mainKey = ''; renderMain(); renderPending(); renderCounts();
      return;
    }
    if (a === 'comp-add' || a === 'comp-undo') {
      const s = slotOf(S.slot), d = draftOf(s.file).completion, C = S.comp[s.file];
      const [feat, sub] = (a === 'comp-add' ? b.dataset.feature : b.dataset.feature).split(':');
      const v = b.dataset.value;
      if (a === 'comp-add') {
        if (feat === 'compendium') { const g = new Set(d.compendium?.groups || []); g.add(v); d.compendium = {groups: [...g]}; }
        if (feat === 'discovery') d.discovery = {categories: 'all'};
        if (feat === 'gyms') d.gyms = {gyms: 'all'};
        if (feat === 'activities') d.activities = {spots: 'all', character: 'lucia'};
        if (feat === 'hoops') d.hoops = {hoops: 'all', scored: true, county_counters: 'update'};
        if (feat === 'vehicles') d.vehicles = {count: 'min'};
        if (feat === 'challenges') {
          if (v === 'all') d.challenges = {categories: 'all'};
          else { const cur = d.challenges ? (d.challenges.categories === 'all' ? C.challenges.categories.map(x => x.key) : d.challenges.categories) : [];
                 d.challenges = {categories: [...new Set([...cur, v])]}; }
        }
      } else {
        if (feat === 'compendium') { const g = (d.compendium?.groups || []).filter(x => x !== sub); if (g.length) d.compendium = {groups: g}; else delete d.compendium; }
        else if (feat === 'challenges') {
          const cur = d.challenges ? (d.challenges.categories === 'all' ? C.challenges.categories.map(x => x.key) : d.challenges.categories) : [];
          const left = cur.filter(x => x !== sub);
          if (left.length) d.challenges = {categories: left}; else delete d.challenges;
        } else delete d[feat];
      }
      S.mainKey = ''; renderMain(); renderPending(); renderCounts();
      return;
    }
    if (a === 'guns-all' || a === 'guns-none') {
      const s = slotOf(S.slot), d = draftOf(s.file), who = b.dataset.who;
      const c = S.detail[s.file]?.guns?.characters?.find(x => x.key === who);
      if (a === 'guns-all' && c?.offered?.length) d.guns[who] = c.offered.map(g => g.id); else delete d.guns[who];
      S.mainKey = ''; renderMain(); renderPending(); renderCounts();
      return;
    }
    if (a === 'sd-home') { S.sd[S.slot].cur = null; S.sd[S.slot].node = null; S.mainKey = ''; renderMain(); return; }
    if (a === 'sd-open') { sdOpen(S.slot, b.dataset.section, JSON.parse(b.dataset.path), b.dataset.label, false); return; }
    if (a === 'sd-more') { const c = S.sd[S.slot].cur; sdOpen(S.slot, c.section, c.path, null, true); return; }
    if (a === 'world-fill' || a === 'world-undo') {
      const s = slotOf(S.slot), w = S.world[s.file], d = draftOf(s.file).world, what = b.dataset.what, who = b.dataset.who;
      if (what === 'levels' || what === 'everything') {   // one character's strength, cardio and focus, to the highest
        const c = w.levels?.characters?.find(x => x.key === who), all = d.levels || {}, ch = {};
        for (const a of LEVELS) { const x = c?.levels?.[a]; if (x && x.value !== x.max) ch[a] = x.max; }
        if (Object.keys(ch).length) all[who] = ch; else delete all[who];
        if (Object.keys(all).length) d.levels = all; else delete d.levels;
      } else if (what === 'capacities') {         // one character's four bars, each to the maximum the game writes
        const c = w.growth?.characters?.find(x => x.key === who), all = d.growth || {}, ch = {};
        if (a === 'world-fill') for (const q of CAPACITIES) { const x = c?.capacities?.[q]; if (x && x.value !== x.max) ch[q] = x.max; }
        if (Object.keys(ch).length) all[who] = ch; else delete all[who];
        if (Object.keys(all).length) d.growth = all; else delete d.growth;
      } else if (who) {                           // one character's special meter, skills or vest
        const ch = d[who] || {}, c = w.player.characters.find(x => x.key === who);
        if (a === 'world-undo') delete ch[what];
        else if (what === 'skills') { const to = Number(b.dataset.to); if (to > Math.min(...c.skills)) ch.skills = to; else delete ch.skills; }
        else ch[what] = what === 'meter' ? 'full' : true;
        if (Object.keys(ch).length) d[who] = ch; else delete d[who];
      } else if (what === 'fog') { if (a === 'world-fill') d.fog = 'known'; else delete d.fog; }
      else if (what === 'health') d.health = w.healthMax;
      else if (a === 'world-fill') d.armour = 'full';
      else delete d.armour;
      if (what === 'everything') {                // also fill the four bars and the special meter for that character
        const c = w.growth?.characters?.find(x => x.key === who), all = d.growth || {}, ch = {};
        for (const q of CAPACITIES) { const x = c?.capacities?.[q]; if (x && x.value !== x.max) ch[q] = x.max; }
        if (Object.keys(ch).length) all[who] = ch; else delete all[who];
        if (Object.keys(all).length) d.growth = all; else delete d.growth;
        const cur = w.player?.characters?.find(x => x.key === who);
        if (cur && cur.meter < (w.player.meterFull ?? 100)) {
          const pc = d[who] || {}; pc.meter = 'full'; d[who] = pc;
        }
      }
      S.mainKey = ''; renderMain(); renderPending(); renderCounts();
      return;
    }
    if (a === 'stunts' || a === 'stunts-undo') {
      const file = S.slot, sel = new Set(S.stuntSel[file] || []);
      const g = b.dataset.group;
      if (a === 'stunts-undo') sel.delete(g);
      else if (g === 'all') for (const x of S.comp[file].stunts.groups) { if (x.done < x.count) sel.add(x.id); }
      else sel.add(g);
      setStunts(file, [...sel]);
      return;
    }
    if (a === 'fillall') {                       // each ammo type with a known full load, to that load
      for (const w of $$(`.inputs[data-scope="${b.dataset.scope}"]`)) {
        const input = w.querySelector('input[type="number"]');
        const to = input && input.dataset.full;
        if (to) { input.value = to; onEdit(input); }
      }
      return;
    }
    if (a === 'reload') { const f = S.slot; delete S.detail[f]; delete S.stats[f]; delete S.comp[f]; delete S.world[f]; delete S.sd[f]; delete S.preview[f]; S.mainKey = ''; renderMain(); return; }
    if (a === 'more') { S.find.limit += 300; $('#allrows').innerHTML = allRows(slotOf(S.slot)); return; }
    if (a === 'review') { S.reviewOpen = !S.reviewOpen; renderPending(); return; }
    if (a === 'discard') {
      const s = slotOf(S.slot);
      delete S.drafts[s.file]; delete S.stuntSel[s.file]; delete S.stuntKeys[s.file]; seedDraft(s); S.mainKey = ''; renderMain(); renderPending(); return;
    }
    if (a === 'save') {
      const s = slotOf(S.slot);
      const d = draftList(draftOf(s.file));
      const none = !d.money.length && !d.ammo.length && !d.stats.length && !Object.keys(d.world).length && !d.raw.length && !compCount(d.completion) && !gunCount(d.guns);
      if (none && !s.modified) return;
      if (none) {
        if (confirm(T('You removed every edit for this save. Put its original back instead?'))) act('/api/restore', {}, () => { S.drafts = {}; });
        return;
      }
      if (mustSignIn(S.state)) { goSignIn('edit'); return; }   // the drafts stay here while signing in
      const stuntKeys = S.stuntKeys[s.file] || new Set();
      const risky = d.stats.some(c => !stuntKeys.has(`${c.group}:${c.row}`) && !(S.detail[s.file]?.featured || []).some(f => f.entries.some(e => e.group === c.group && e.row === c.row)));
      if (risky && !confirm(T('Some of these edits come from All stats, where most values have unknown meanings and can break the save. Keep the originals backed up and check the save loads. Continue?'))) return;
      act('/api/patch', {slot: s.file, ...d});
    }
  });

  $('#passed').addEventListener('click', () => { $('#passed').hidden = true; });
  $('#quit').addEventListener('click', () => {
    if (!confirm(T('Quit Save Garage? Edits you haven\u2019t saved here are lost.'))) return;
    api('/api/quit', {}).then(() => { document.body.innerHTML = '<main id="main"><section class="title-card"><h1>Save Garage has closed</h1><p>You can close this tab.</p></section></main>'; })
      .catch(e => toast(ERR[e.code] || ERR.internal));
  });

  document.addEventListener('input', e => {
    const el = e.target;
    if (el.dataset.edit && el.type !== 'checkbox') onEdit(el);
    if (el.dataset.world) onWorld(el);
    if (el.dataset.raw && el.type !== 'checkbox') onRaw(el);
    if (el.dataset.find === 'q') {
      S.find.q = el.value; S.find.limit = 150;
      clearTimeout(S.findT);
      S.findT = setTimeout(() => { const box = $('#allrows'); if (box) box.innerHTML = allRows(slotOf(S.slot)); }, 160);
    }
  });

  document.addEventListener('change', e => {
    const el = e.target;
    if (el.dataset.gun && el.type === 'checkbox') onGun(el);
    if (el.dataset.stacks && el.type === 'checkbox') onStacks(el);
    if (el.dataset.edit && el.type === 'checkbox') onEdit(el);
    if (el.dataset.raw && el.type === 'checkbox') onRaw(el);
    if (el.dataset.find === 'varies' || el.dataset.find === 'named' || el.dataset.find === 'game') {
      S.find[el.dataset.find] = el.checked; S.find.limit = 150;
      const box = $('#allrows'); if (box) box.innerHTML = allRows(slotOf(S.slot));
    }
  });

  document.addEventListener('submit', e => {
    const f = e.target;
    if (f.dataset.form !== 'ip') return;
    e.preventDefault();
    const host = $('#ip').value.trim();
    if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) { S.localError = {code: 'console_not_found', detail: ''}; renderJob(); return; }
    act('/api/console', {host}, st => { S.manualView = null; onState(st); });
  });

  window.addEventListener('beforeunload', e => {
    const s = S.state?.slots?.find(x => editCount(draftOf(x.file)) && dirty(x));
    if (s) { e.preventDefault(); e.returnValue = ''; }
  });

  // ------------------------------------------------------------ start
  api('/api/network', {}).catch(() => {});
  poll();
})();
