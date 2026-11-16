import { TERMINAL_COMMANDS } from './data.js';

export function initTerminal() {
  const screenEl = document.getElementById('term-screen');
  const inputEl = document.getElementById('term-input');
  const formEl = document.getElementById('term-form');
  const modeToggleBtn = document.getElementById('term-mode-btn');
  const presetBtns = document.querySelectorAll('[data-term-cmd]');

  if (!screenEl || !inputEl || !formEl) return;

  let jsonMode = false;
  let activeKey = 'ping';

  function renderOutput(key) {
    const entry = TERMINAL_COMMANDS[key] || TERMINAL_COMMANDS.ping;
    activeKey = key;
    inputEl.value = entry.cmd;

    if (jsonMode) {
      screenEl.textContent = JSON.stringify(entry.jsonOutput, null, 2);
      screenEl.classList.add('is-json');
    } else {
      screenEl.textContent = entry.tuiOutput.join('\n');
      screenEl.classList.remove('is-json');
    }

    presetBtns.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.termCmd === key);
    });
  }

  presetBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      renderOutput(btn.dataset.termCmd);
    });
  });

  if (modeToggleBtn) {
    modeToggleBtn.addEventListener('click', () => {
      jsonMode = !jsonMode;
      modeToggleBtn.textContent = jsonMode
        ? 'Режим: AI Operator (--json)'
        : 'Режим: Human Mini HUD (TUI)';
      modeToggleBtn.classList.toggle('is-json', jsonMode);
      renderOutput(activeKey);
    });
  }

  formEl.addEventListener('submit', (e) => {
    e.preventDefault();
    const raw = inputEl.value.trim().toLowerCase();
    if (!raw) return;

    if (raw.includes('wh') || raw.includes('clean') || raw.includes('miner')) {
      renderOutput('wh');
    } else if (raw.includes('pocket') || raw.includes('send') || raw.includes('sync')) {
      renderOutput('pocket');
    } else if (raw.includes('doctor') || raw.includes('check')) {
      renderOutput('doctor');
    } else if (raw.startsWith('e ') || raw.includes('exec') || raw.includes('service')) {
      renderOutput('exec');
    } else {
      renderOutput('ping');
    }
  });

  renderOutput('ping');
}
