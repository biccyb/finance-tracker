# FinTrack — Supabase Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate FinTrack from localStorage to Supabase so data persists across devices, with email magic-link authentication.

**Architecture:** Add a `supabase-layer` script block that initialises the Supabase JS v2 client, maintains an in-memory cache (`_db`), and exposes an async `loadAll()`. The existing synchronous render functions continue to read from `_db` unchanged. Only write operations (addIncomeEntry, addExpenseEntry, setBalanceOverride) become async. App initialisation becomes async: check session → show auth overlay if no session, or call loadAll() + seed + render if session exists.

**Tech Stack:** Supabase JS v2 (CDN UMD build), Supabase Auth (email magic link), Row Level Security, no build tools, single HTML file.

---

## File Map

| File | Change |
|------|--------|
| `index.html` | All changes: new CDN script tag, new `supabase-layer` script, updated `data-layer` script, updated `render-layer` script (async saves), updated `app` script (async init), new auth overlay HTML, new auth overlay CSS, updated topbar avatar id, updated sidebar logout onclick |
| `tests/data-tests.html` | Update mock to use _db instead of localStorage; keep all 12 tests passing |

---

## Task 1: Supabase SQL Schema

**Files:**
- No file edits — run SQL in Supabase dashboard SQL editor

- [ ] **Step 1: Open Supabase SQL editor**

Navigate to your Supabase project → SQL Editor → New query.

- [ ] **Step 2: Run the schema SQL**

```sql
-- Income log
create table income_log (
  id          uuid      primary key default gen_random_uuid(),
  user_id     uuid      references auth.users not null,
  source      text      not null,
  amount      integer   not null,
  date        date      not null,
  note        text      not null default '',
  created_at  timestamptz not null default now()
);

-- Expense log
create table expense_log (
  id          uuid      primary key default gen_random_uuid(),
  user_id     uuid      references auth.users not null,
  type        text      not null,
  amount      integer   not null,
  date        date      not null,
  note        text      not null default '',
  created_at  timestamptz not null default now()
);

-- Installment plans (seeded per-user on first login)
create table installments (
  id          text      not null,
  user_id     uuid      references auth.users not null,
  name        text      not null,
  card        text      not null,
  monthly     integer   not null,
  paid        integer   not null,
  total       integer   not null,
  primary key (user_id, id)
);

-- Fixed expenses (seeded per-user on first login)
create table fixed_expenses (
  id          text      not null,
  user_id     uuid      references auth.users not null,
  name        text      not null,
  amount      integer   not null,
  category    text      not null,
  primary key (user_id, id)
);

-- User settings (one row per user)
create table settings (
  user_id          uuid    primary key references auth.users,
  currency         text    not null default 'THB',
  month_start      integer not null default 1,
  username         text    not null default 'B',
  balance_override integer
);

-- Row Level Security
alter table income_log     enable row level security;
alter table expense_log    enable row level security;
alter table installments   enable row level security;
alter table fixed_expenses enable row level security;
alter table settings       enable row level security;

create policy "own_data" on income_log     for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own_data" on expense_log    for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own_data" on installments   for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own_data" on fixed_expenses for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own_data" on settings       for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
```

- [ ] **Step 3: Verify in Table Editor**

In Supabase → Table Editor, confirm all 5 tables appear: `income_log`, `expense_log`, `installments`, `fixed_expenses`, `settings`.

- [ ] **Step 4: Enable email magic links**

Supabase → Authentication → Providers → Email — confirm "Enable Email provider" is ON and "Confirm email" is set to your preference (recommended: OFF for personal use so login is instant).

- [ ] **Step 5: Note credentials**

From Supabase → Project Settings → API, copy:
- `Project URL` (e.g. `https://abcdefgh.supabase.co`)
- `anon public` key

These go into `SUPABASE_URL` and `SUPABASE_ANON_KEY` in Task 2.

---

## Task 2: Add Supabase CDN + supabase-layer Script

**Files:**
- Modify: `index.html` (add CDN tag + new script block between CDN and `data-layer`)

- [ ] **Step 1: Add Supabase CDN script tag**

Find this line in index.html (just before `<script id="logos">`):

```html
  <script id="logos">
```

Insert BEFORE it:

```html
  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
```

- [ ] **Step 2: Add supabase-layer script block**

Insert a new script block between `</script>` (end of logos block, around line 611) and `<script id="data-layer">`:

```html
  <script id="supabase-layer">
  // ── Credentials ──────────────────────────────────────────────────
  const SUPABASE_URL      = 'https://YOURPROJECT.supabase.co';  // ← replace
  const SUPABASE_ANON_KEY = 'YOURANONKEY';                       // ← replace

  const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

  // ── In-memory cache (synchronous reads, async writes) ────────────
  const _db = {
    incomeLog:     [],
    expenseLog:    [],
    installments:  [],
    fixedExpenses: [],
    settings:      null,
  };

  async function loadAll() {
    const { data: { user } } = await sb.auth.getUser();
    const uid = user.id;
    const [il, el_, inst, fe, sett] = await Promise.all([
      sb.from('income_log').select('*').eq('user_id', uid),
      sb.from('expense_log').select('*').eq('user_id', uid),
      sb.from('installments').select('*').eq('user_id', uid),
      sb.from('fixed_expenses').select('*').eq('user_id', uid),
      sb.from('settings').select('*').eq('user_id', uid).maybeSingle(),
    ]);
    _db.incomeLog     = il.data   || [];
    _db.expenseLog    = el_.data  || [];
    _db.installments  = inst.data || [];
    _db.fixedExpenses = fe.data   || [];
    _db.settings      = sett.data || null;
  }
  </script>
```

- [ ] **Step 3: Replace credentials**

In the new block, replace `'https://YOURPROJECT.supabase.co'` and `'YOURANONKEY'` with the values from Task 1 Step 5.

- [ ] **Step 4: Verify script order in index.html**

Confirm the script order is now:
1. Supabase CDN `<script src="...">` 
2. `<script id="logos">`
3. `<script id="supabase-layer">`
4. `<script id="data-layer">`
5. `<script id="render-layer">`
6. `<script id="app">`

- [ ] **Step 5: Commit**

```bash
cd "/Users/biccywang/Claude Code/Projects/Finance Tracker"
git add index.html
git commit -m "feat: add Supabase CDN and supabase-layer script block with _db cache and loadAll()"
```

---

## Task 3: Add Auth Overlay HTML + CSS

**Files:**
- Modify: `index.html` (add auth overlay CSS + HTML element)

- [ ] **Step 1: Add auth overlay CSS**

Find this CSS block (last responsive breakpoint, near the end of the `<style>` tag):

```css
  @media (max-width:480px) {
```

Insert BEFORE it (still inside `<style>`):

```css
  /* ── Auth Overlay ──────────────────────────────────────────── */
  .auth-overlay { position:fixed; inset:0; background:rgba(245,246,250,0.97); backdrop-filter:blur(4px); display:none; align-items:center; justify-content:center; z-index:1000; }
  .auth-card { background:#fff; border:1px solid #ebebf0; border-radius:18px; padding:40px 36px; width:100%; max-width:380px; text-align:center; box-shadow:0 8px 32px rgba(0,0,0,.08); }
  .auth-logo-wrap { width:52px; height:52px; border-radius:14px; background:linear-gradient(135deg,#16a34a,#22c55e); display:flex; align-items:center; justify-content:center; margin:0 auto 18px; }
  .auth-title { font-size:22px; font-weight:700; color:#1a1a2e; margin:0 0 6px; }
  .auth-subtitle { font-size:13.5px; color:#64748b; margin:0 0 28px; line-height:1.5; }
  .auth-field { text-align:left; margin-bottom:14px; }
  .auth-field label { display:block; font-size:12px; font-weight:600; color:#64748b; margin-bottom:6px; }
  .auth-field input { width:100%; box-sizing:border-box; border:1.5px solid #e2e8f0; border-radius:9px; padding:11px 13px; font-size:14px; color:#1a1a2e; outline:none; transition:border-color .15s; }
  .auth-field input:focus { border-color:#16a34a; }
  .auth-btn { width:100%; padding:12px; background:linear-gradient(135deg,#16a34a,#22c55e); color:#fff; border:none; border-radius:9px; font-size:14px; font-weight:600; cursor:pointer; transition:opacity .15s; margin-top:4px; }
  .auth-btn:hover { opacity:.9; }
  .auth-btn:disabled { opacity:.6; cursor:default; }
  .auth-btn-secondary { background:none; border:1.5px solid #e2e8f0; border-radius:9px; padding:10px 20px; font-size:13px; color:#64748b; cursor:pointer; margin-top:12px; }
  .auth-sent-icon { font-size:36px; margin-bottom:10px; }
  .auth-sent-text { font-size:14px; color:#1a1a2e; font-weight:600; margin:0 0 4px; }
  .auth-sent-sub { font-size:13px; color:#64748b; margin:0 0 16px; }
  .auth-error { font-size:12.5px; color:#ef4444; min-height:18px; margin-top:10px; }
```

- [ ] **Step 2: Add auth overlay HTML**

Find this line (just before `<aside class="sidebar">`):

```html
<aside class="sidebar">
```

Insert BEFORE it:

```html
<div class="auth-overlay" id="auth-overlay">
  <div class="auth-card">
    <div class="auth-logo-wrap">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
    </div>
    <h1 class="auth-title">FinTrack</h1>
    <p class="auth-subtitle">Sign in to access your personal finance dashboard. We'll email you a magic link.</p>
    <div id="auth-form">
      <div class="auth-field">
        <label for="auth-email-input">Email address</label>
        <input type="email" id="auth-email-input" placeholder="you@email.com" />
      </div>
      <button class="auth-btn" onclick="sendMagicLink()">Send Magic Link</button>
    </div>
    <div id="auth-sent" style="display:none">
      <div class="auth-sent-icon">✉️</div>
      <p class="auth-sent-text">Check your inbox</p>
      <p class="auth-sent-sub">We sent a login link to your email address.</p>
      <button class="auth-btn-secondary" onclick="showAuthForm()">Use a different email</button>
    </div>
    <p id="auth-error" class="auth-error"></p>
  </div>
</div>
```

- [ ] **Step 3: Add id to topbar avatar**

Find:

```html
      <div class="avatar">B</div>
```

Replace with:

```html
      <div class="avatar" id="user-avatar">B</div>
```

- [ ] **Step 4: Wire sidebar logout button**

Find:

```html
      Log out
    </div>
  </div>
</aside>
```

Replace with:

```html
      Log out
    </div>
  </div>
  <div style="padding:0 12px 8px;font-size:11px;color:#94a3b8;word-break:break-all;" id="sidebar-user-email"></div>
</aside>
```

- [ ] **Step 5: Add onclick to Log out nav item**

Find:

```html
    <div class="nav-item">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
      Log out
    </div>
```

Replace with:

```html
    <div class="nav-item" onclick="signOut()" style="cursor:pointer;">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
      Log out
    </div>
```

- [ ] **Step 6: Commit**

```bash
cd "/Users/biccywang/Claude Code/Projects/Finance Tracker"
git add index.html
git commit -m "feat: add auth overlay HTML/CSS and wire topbar avatar + logout"
```

---

## Task 4: Update Data Layer — Read from _db, Async Writes

**Files:**
- Modify: `index.html` — replace entire `<script id="data-layer">` block content

The full replacement for the data-layer script body (between `<script id="data-layer">` and its `</script>`):

- [ ] **Step 1: Replace data-layer script content**

Find the entire content between `<script id="data-layer">` and its closing `</script>` and replace with:

```javascript
  const KEYS = {
    INCOME_LOG:     'fintrack_income_log',
    EXPENSE_LOG:    'fintrack_expense_log',
    INSTALLMENTS:   'fintrack_installments',
    FIXED_EXPENSES: 'fintrack_fixed_expenses',
    SETTINGS:       'fintrack_settings',
  };

  const SEED_INSTALLMENTS = [
    { id:'i1', name:'Cash Loan 1',  card:'UOB',   monthly:1968, paid:6,  total:11 },
    { id:'i2', name:'Cash Loan 2',  card:'UOB',   monthly:2236, paid:1,  total:11 },
    { id:'i3', name:'Cash Loan 3',  card:'UOB',   monthly:2236, paid:1,  total:11 },
    { id:'i4', name:'Deepcharts',   card:'KTC',   monthly:1072, paid:5,  total:10 },
    { id:'i5', name:'Fabervaale',   card:'KTC',   monthly:3419, paid:4,  total:10 },
    { id:'i6', name:'ATAS',         card:'KBANK', monthly:757,  paid:1,  total:10 },
    { id:'i7', name:'Tradezella',   card:'KBANK', monthly:790,  paid:3,  total:10 },
    { id:'i8', name:'Tradingview',  card:'KBANK', monthly:825,  paid:6,  total:10 },
    { id:'i9', name:'Petheal',      card:'KBANK', monthly:970,  paid:9,  total:10 },
  ];

  const SEED_FIXED_EXPENSES = [
    { id:'f1', name:'Maid Salary',      amount:7000, category:'household'    },
    { id:'f2', name:'Electricity',      amount:4000, category:'household'    },
    { id:'f3', name:'Water Bill',       amount:500,  category:'household'    },
    { id:'f4', name:'Phone Bill',       amount:749,  category:'household'    },
    { id:'f5', name:'Wifi Bill',        amount:749,  category:'household'    },
    { id:'f6', name:'YouTube Premium',  amount:519,  category:'subscription' },
    { id:'f7', name:'iCloud Storage',   amount:99,   category:'subscription' },
  ];

  // Synchronous reads — serve from in-memory _db cache populated by loadAll()
  function getData(key) {
    switch (key) {
      case KEYS.INCOME_LOG:     return _db.incomeLog;
      case KEYS.EXPENSE_LOG:    return _db.expenseLog;
      case KEYS.INSTALLMENTS:   return _db.installments;
      case KEYS.FIXED_EXPENSES: return _db.fixedExpenses;
      default: return null;
    }
  }

  function getMonthKey(date = new Date()) {
    return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0');
  }
  function todayISO() {
    return new Date().toISOString().split('T')[0];
  }
  function getIncomeLog(month = getMonthKey()) {
    return _db.incomeLog.filter(e => e.date.startsWith(month));
  }
  function getExpenseLog(month = getMonthKey()) {
    return _db.expenseLog.filter(e => e.date.startsWith(month));
  }

  // getSettings normalises snake_case Supabase columns to camelCase used by render layer
  function getSettings() {
    const s = _db.settings;
    if (!s) return { currency:'THB', monthStart:1, userName:'B' };
    return {
      currency:        s.currency   || 'THB',
      monthStart:      s.month_start || 1,
      userName:        s.username   || 'B',
      balanceOverride: s.balance_override != null ? s.balance_override : undefined,
    };
  }

  // Async writes — update Supabase then mirror into _db
  async function addIncomeEntry(source, amount, date, note = '') {
    const { data: { user } } = await sb.auth.getUser();
    const { data, error } = await sb.from('income_log')
      .insert({ user_id: user.id, source, amount, date, note })
      .select().single();
    if (error) throw error;
    _db.incomeLog.push(data);
    await clearBalanceOverride();
  }

  async function addExpenseEntry(type, amount, date, note = '') {
    const { data: { user } } = await sb.auth.getUser();
    const { data, error } = await sb.from('expense_log')
      .insert({ user_id: user.id, type, amount, date, note })
      .select().single();
    if (error) throw error;
    _db.expenseLog.push(data);
    await clearBalanceOverride();
  }

  async function setBalanceOverride(amount) {
    const { data: { user } } = await sb.auth.getUser();
    const { error } = await sb.from('settings').upsert(
      { user_id: user.id, balance_override: amount, currency:'THB', month_start:1, username:'B' },
      { onConflict: 'user_id' }
    );
    if (error) throw error;
    if (!_db.settings) {
      _db.settings = { user_id: user.id, currency:'THB', month_start:1, username:'B', balance_override: null };
    }
    _db.settings.balance_override = amount;
  }

  async function clearBalanceOverride() {
    if (!_db.settings) return;
    const { data: { user } } = await sb.auth.getUser();
    const { error } = await sb.from('settings')
      .update({ balance_override: null })
      .eq('user_id', user.id);
    if (error) throw error;
    _db.settings.balance_override = null;
  }

  const SALARY = 30000;
  function computeCashBalance(month = getMonthKey()) {
    const settings = getSettings();
    if (settings.balanceOverride != null) return settings.balanceOverride;
    const incomeTotal  = getIncomeLog(month).reduce((s, e) => s + e.amount, 0);
    const expenseTotal = getExpenseLog(month).reduce((s, e) => s + e.amount, 0);
    const fixedTotal   = _db.fixedExpenses.reduce((s, e) => s + e.amount, 0);
    const ccTotal      = _db.installments.reduce((s, p) => s + p.monthly, 0);
    return SALARY + incomeTotal - fixedTotal - ccTotal - expenseTotal;
  }

  // Seed static data into Supabase for a new user (called after loadAll)
  async function seedIfNew(userId) {
    if (_db.installments.length === 0) {
      const rows = SEED_INSTALLMENTS.map(r => ({ ...r, user_id: userId }));
      const { error } = await sb.from('installments').insert(rows);
      if (error) throw error;
      _db.installments = rows;
    }
    if (_db.fixedExpenses.length === 0) {
      const rows = SEED_FIXED_EXPENSES.map(r => ({ ...r, user_id: userId }));
      const { error } = await sb.from('fixed_expenses').insert(rows);
      if (error) throw error;
      _db.fixedExpenses = rows;
    }
  }

  // Offer to migrate any existing localStorage data on first login
  async function migrateFromLocalStorage(user) {
    const lsIncome  = localStorage.getItem('fintrack_income_log');
    const lsExpense = localStorage.getItem('fintrack_expense_log');
    const lsSetts   = localStorage.getItem('fintrack_settings');
    if (!lsIncome && !lsExpense && !lsSetts) return;
    // Only migrate if Supabase account is empty
    if (_db.incomeLog.length > 0 || _db.expenseLog.length > 0) {
      localStorage.removeItem('fintrack_income_log');
      localStorage.removeItem('fintrack_expense_log');
      localStorage.removeItem('fintrack_settings');
      return;
    }
    if (!confirm('Found locally stored data. Import it to your account?')) {
      localStorage.removeItem('fintrack_income_log');
      localStorage.removeItem('fintrack_expense_log');
      localStorage.removeItem('fintrack_settings');
      return;
    }
    const uid = user.id;
    if (lsIncome) {
      const entries = JSON.parse(lsIncome).map(e => ({
        user_id: uid, source: e.source, amount: e.amount, date: e.date, note: e.note || ''
      }));
      if (entries.length) {
        const { data, error } = await sb.from('income_log').insert(entries).select();
        if (!error) _db.incomeLog = data;
      }
    }
    if (lsExpense) {
      const entries = JSON.parse(lsExpense).map(e => ({
        user_id: uid, type: e.type, amount: e.amount, date: e.date, note: e.note || ''
      }));
      if (entries.length) {
        const { data, error } = await sb.from('expense_log').insert(entries).select();
        if (!error) _db.expenseLog = data;
      }
    }
    if (lsSetts) {
      const s = JSON.parse(lsSetts);
      if (s.balanceOverride != null) await setBalanceOverride(s.balanceOverride);
    }
    localStorage.removeItem('fintrack_income_log');
    localStorage.removeItem('fintrack_expense_log');
    localStorage.removeItem('fintrack_settings');
  }
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/biccywang/Claude Code/Projects/Finance Tracker"
git add index.html
git commit -m "feat: replace data layer — synchronous reads from _db, async Supabase writes"
```

---

## Task 5: Update App Init — Async with Auth State Management

**Files:**
- Modify: `index.html` — replace entire `<script id="app">` block content

- [ ] **Step 1: Replace app script content**

Find the entire content between `<script id="app">` and its closing `</script>` and replace with:

```javascript
  function renderDate() {
    el('page-date').textContent = new Date().toLocaleDateString('en-GB', {
      weekday:'short', day:'numeric', month:'long', year:'numeric'
    });
  }

  function showAuthOverlay() {
    const ov = el('auth-overlay');
    ov.style.display = 'flex';
  }

  function hideAuthOverlay() {
    el('auth-overlay').style.display = 'none';
  }

  function updateUserDisplay(user) {
    const initial = (user.email || 'U')[0].toUpperCase();
    el('user-avatar').textContent = initial;
    const emailEl = el('sidebar-user-email');
    if (emailEl) emailEl.textContent = user.email || '';
  }

  async function initApp(user) {
    hideAuthOverlay();
    await loadAll();
    await migrateFromLocalStorage(user);
    await seedIfNew(user.id);
    updateUserDisplay(user);
    renderDate();
    renderKPIs();
    renderInstallments();
    renderIncomeSources();
    renderChart();
    renderFixedExpenses();
    initChipGroups();
    initModalBackdrops();
    el('balance-adjust-input').addEventListener('keydown', e => {
      if (e.key === 'Enter')  applyAdjust();
      if (e.key === 'Escape') el('adjust-row').classList.remove('open');
    });
  }

  async function sendMagicLink() {
    const email = el('auth-email-input').value.trim();
    if (!email) { el('auth-error').textContent = 'Please enter your email.'; return; }
    el('auth-error').textContent = '';
    const btn = document.querySelector('#auth-overlay .auth-btn');
    btn.textContent = 'Sending…';
    btn.disabled = true;
    const { error } = await sb.auth.signInWithOtp({ email });
    btn.textContent = 'Send Magic Link';
    btn.disabled = false;
    if (error) { el('auth-error').textContent = error.message; return; }
    el('auth-form').style.display = 'none';
    el('auth-sent').style.display = 'block';
  }

  function showAuthForm() {
    el('auth-form').style.display = 'block';
    el('auth-sent').style.display = 'none';
    el('auth-error').textContent = '';
  }

  async function signOut() {
    await sb.auth.signOut();
    location.reload();
  }

  document.addEventListener('DOMContentLoaded', async () => {
    showAuthOverlay();
    const { data: { session } } = await sb.auth.getSession();
    if (session) {
      await initApp(session.user);
    }

    sb.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session) {
        await initApp(session.user);
      } else if (event === 'SIGNED_OUT') {
        location.reload();
      }
    });
  });
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/biccywang/Claude Code/Projects/Finance Tracker"
git add index.html
git commit -m "feat: async app init with Supabase auth state management and auth overlay"
```

---

## Task 6: Update Render Layer — Async Save Functions

**Files:**
- Modify: `index.html` — update `saveIncome`, `saveExpense`, `applyAdjust` in the render-layer script

- [ ] **Step 1: Make saveIncome async**

Find in `<script id="render-layer">`:

```javascript
  function saveIncome() {
    const source = el('income-source-chips').querySelector('.modal-chip.active')?.dataset.value;
    const amount = parseInt(el('income-amount-input').value, 10);
    const date   = el('income-date-input').value;
    const note   = el('income-note-input').value.trim();
    if (!source)               { alert('Please select a source.');        return; }
    if (!amount || amount < 1) { alert('Please enter a valid amount.');   return; }
    if (!date)                 { alert('Please select a date.');          return; }
    addIncomeEntry(source, amount, date, note);
    closeModal('income');
    refreshAll();
  }
```

Replace with:

```javascript
  async function saveIncome() {
    const source = el('income-source-chips').querySelector('.modal-chip.active')?.dataset.value;
    const amount = parseInt(el('income-amount-input').value, 10);
    const date   = el('income-date-input').value;
    const note   = el('income-note-input').value.trim();
    if (!source)               { alert('Please select a source.');        return; }
    if (!amount || amount < 1) { alert('Please enter a valid amount.');   return; }
    if (!date)                 { alert('Please select a date.');          return; }
    await addIncomeEntry(source, amount, date, note);
    closeModal('income');
    refreshAll();
  }
```

- [ ] **Step 2: Make saveExpense async**

Find:

```javascript
  function saveExpense() {
    const type   = el('expense-type-chips').querySelector('.modal-chip.active')?.dataset.value;
    const amount = parseInt(el('expense-amount-input').value, 10);
    const date   = el('expense-date-input').value;
    const note   = el('expense-note-input').value.trim();
    if (!type)               { alert('Please select an expense type.'); return; }
    if (!amount || amount < 1) { alert('Please enter a valid amount.');  return; }
    if (!date)               { alert('Please select a date.');          return; }
    addExpenseEntry(type, amount, date, note);
    closeModal('expense');
    refreshAll();
  }
```

Replace with:

```javascript
  async function saveExpense() {
    const type   = el('expense-type-chips').querySelector('.modal-chip.active')?.dataset.value;
    const amount = parseInt(el('expense-amount-input').value, 10);
    const date   = el('expense-date-input').value;
    const note   = el('expense-note-input').value.trim();
    if (!type)                 { alert('Please select an expense type.'); return; }
    if (!amount || amount < 1) { alert('Please enter a valid amount.');   return; }
    if (!date)                 { alert('Please select a date.');          return; }
    await addExpenseEntry(type, amount, date, note);
    closeModal('expense');
    refreshAll();
  }
```

- [ ] **Step 3: Make applyAdjust async**

Find:

```javascript
  function applyAdjust() {
    const val = parseInt(el('balance-adjust-input').value, 10);
    if (isNaN(val) || val < 0) { alert('Enter a valid positive amount.'); return; }
    setBalanceOverride(val);
    el('adjust-row').classList.remove('open');
    renderKPIs();
  }
```

Replace with:

```javascript
  async function applyAdjust() {
    const val = parseInt(el('balance-adjust-input').value, 10);
    if (isNaN(val) || val < 0) { alert('Enter a valid positive amount.'); return; }
    await setBalanceOverride(val);
    el('adjust-row').classList.remove('open');
    renderKPIs();
  }
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/biccywang/Claude Code/Projects/Finance Tracker"
git add index.html
git commit -m "feat: make saveIncome, saveExpense, applyAdjust async to await Supabase writes"
```

---

## Task 7: Update Test File

**Files:**
- Modify: `tests/data-tests.html` — update mock to use _db instead of localStorage

- [ ] **Step 1: Read current test file structure**

```bash
grep -n "getData\|setData\|seedIfEmpty\|localStorage\|_db" tests/data-tests.html | head -40
```

- [ ] **Step 2: Replace the mock setup in tests**

In `tests/data-tests.html`, find where SEED data and getData/setData/seedIfEmpty are defined or mocked for testing (usually a `<script>` block near the top of the test file).

Replace the data layer mock with the new _db-based one. The key is to initialise `_db` with test data before each test runs.

Find any code block that sets up localStorage-based data (typically something like):

```javascript
// setup localStorage with test data
localStorage.setItem(KEYS.INSTALLMENTS, JSON.stringify([...]));
```

Replace with:

```javascript
// setup _db with test data (mirrors how loadAll() populates it)
const _db = {
  incomeLog:     [],
  expenseLog:    [],
  installments:  [],
  fixedExpenses: [],
  settings:      null,
};
```

And seed it per test using:

```javascript
function resetDb(overrides = {}) {
  _db.incomeLog     = overrides.incomeLog     || [];
  _db.expenseLog    = overrides.expenseLog    || [];
  _db.installments  = overrides.installments  || JSON.parse(JSON.stringify(SEED_INSTALLMENTS));
  _db.fixedExpenses = overrides.fixedExpenses || JSON.parse(JSON.stringify(SEED_FIXED_EXPENSES));
  _db.settings      = overrides.settings      || null;
}
```

Call `resetDb()` in each test's setup.

- [ ] **Step 3: Remove any calls to seedIfEmpty() from tests**

`seedIfEmpty()` no longer exists. Replace with `resetDb()`.

- [ ] **Step 4: Open tests in browser and verify all pass**

```bash
open "tests/data-tests.html"
```

Expected: all tests show ✅ PASS (or green).

- [ ] **Step 5: Commit**

```bash
cd "/Users/biccywang/Claude Code/Projects/Finance Tracker"
git add tests/data-tests.html
git commit -m "test: update data-tests to use _db mock instead of localStorage"
```

---

## Task 8: End-to-End Test + Deploy

**Files:**
- No code changes — test, push, verify

- [ ] **Step 1: Open the app locally**

```bash
cd "/Users/biccywang/Claude Code/Projects/Finance Tracker"
python3 -m http.server 8080
```

Navigate to `http://localhost:8080`.

- [ ] **Step 2: Verify auth overlay appears**

Expected: Auth overlay with "FinTrack" heading and email input appears on load (not the dashboard).

- [ ] **Step 3: Sign in with magic link**

Enter your email (bic.bov@gmail.com), click "Send Magic Link", check inbox, click link.

Expected: Dashboard loads with all data seeded (installments, fixed expenses). Cash Balance KPI shows correct computed value.

- [ ] **Step 4: Log an income entry**

Click "+ Add Income", select BIOPOX, enter ฿7,500, click Save Income.

Expected: Income Sources card shows ฿7,500 in amber for BIOPOX. Cash Balance updates.

- [ ] **Step 5: Verify data persists**

Refresh the page. After auto-sign-in (Supabase session persists in localStorage):

Expected: BIOPOX still shows ฿7,500 (loaded from Supabase).

- [ ] **Step 6: Test sign out**

Click "Log out" in the sidebar.

Expected: Page reloads, auth overlay appears. Dashboard hidden.

- [ ] **Step 7: Push to GitHub and trigger Vercel deploy**

```bash
cd "/Users/biccywang/Claude Code/Projects/Finance Tracker"
git push origin main
```

Expected: Vercel auto-deploys within ~30 seconds. Check https://vercel.com/dashboard.

- [ ] **Step 8: Verify production URL**

Open the Vercel production URL and repeat Steps 2–6.

Expected: All behaviours identical in production.

---

## Spec Self-Review

**Spec coverage check:**
- ✅ Supabase SQL schema (5 tables + RLS): Task 1
- ✅ CDN + client init + _db cache + loadAll: Task 2
- ✅ Auth overlay HTML + CSS: Task 3
- ✅ Data layer reads from _db: Task 4
- ✅ Async write functions (addIncomeEntry, addExpenseEntry, setBalanceOverride, clearBalanceOverride): Task 4
- ✅ seedIfNew (installments + fixed expenses on first login): Task 4
- ✅ localStorage migration on first login: Task 4
- ✅ Async app init + auth state change handler: Task 5
- ✅ sendMagicLink, showAuthForm, signOut functions: Task 5
- ✅ updateUserDisplay (email in topbar avatar + sidebar): Task 5
- ✅ Async saveIncome, saveExpense, applyAdjust: Task 6
- ✅ Test file updated: Task 7
- ✅ E2E test + deploy: Task 8

**No placeholders found.**

**Type consistency:**
- `getData(key)` → returns array or null from `_db` (Tasks 4, render-layer consumers)
- `getSettings()` → returns camelCase object with `balanceOverride` (used in renderKPIs, computeCashBalance)
- `_db.settings.balance_override` snake_case in DB, converted in `getSettings()` — consistent
- `seedIfNew(userId)` called with `user.id` string — consistent with `_db.installments.map(r => ({...r, user_id: userId}))`

