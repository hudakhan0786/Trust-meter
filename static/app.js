(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const themeToggle = document.querySelector('.theme-toggle');
  const savedTheme = localStorage.getItem('trustmeter-theme');
  const initialTheme = savedTheme || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.dataset.theme = initialTheme;
  const updateThemeLabel = () => themeToggle?.setAttribute('aria-label', document.documentElement.dataset.theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
  updateThemeLabel();
  themeToggle?.addEventListener('click', () => {
    document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('trustmeter-theme', document.documentElement.dataset.theme);
    updateThemeLabel();
  });
  const nav = document.querySelector('.nav');
  const setNav = () => nav && nav.classList.toggle('scrolled', window.scrollY > 8);
  setNav();
  window.addEventListener('scroll', setNav, { passive: true });

  const ambientShapes = [...document.querySelectorAll('.ambient-shape')];
  if (ambientShapes.length && !reduceMotion) {
    const parallaxRates = [0.075, -0.052, 0.038];
    let ambientFrame = false;
    const updateAmbient = () => {
      ambientShapes.forEach((shape, index) => shape.style.setProperty('--scroll-shift', `${Math.round(window.scrollY * parallaxRates[index % parallaxRates.length])}px`));
      ambientFrame = false;
    };
    window.addEventListener('scroll', () => {
      if (!ambientFrame) { ambientFrame = true; requestAnimationFrame(updateAmbient); }
    }, { passive: true });
    updateAmbient();
  }

  const menuToggle = document.querySelector('.menu-toggle');
  const setMenu = (open) => {
    if (!nav || !menuToggle) return;
    nav.classList.toggle('menu-open', open);
    document.body.classList.toggle('menu-open', open);
    menuToggle.setAttribute('aria-expanded', String(open));
    menuToggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  };
  menuToggle?.addEventListener('click', () => setMenu(menuToggle.getAttribute('aria-expanded') !== 'true'));
  nav?.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setMenu(false)));
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') setMenu(false); });

  const revealItems = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window && !reduceMotion) {
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); }
    }), { threshold: 0.12, rootMargin: '0px 0px -25px 0px' });
    revealItems.forEach((item, index) => { item.style.transitionDelay = `${Math.min(index % 5, 4) * 65}ms`; observer.observe(item); });
  } else revealItems.forEach((item) => item.classList.add('visible'));

  const tabs = [...document.querySelectorAll('.tab[data-mode]')];
  const modeInput = document.querySelector('#input-mode');
  const panels = [...document.querySelectorAll('.form-panel[data-panel]')];
  const setMode = (mode) => {
    if (!modeInput) return;
    modeInput.value = mode;
    tabs.forEach((tab) => { const active = tab.dataset.mode === mode; tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active)); });
    panels.forEach((panel) => {
      const active = panel.dataset.panel === mode;
      panel.hidden = !active;
      panel.querySelectorAll('input,textarea').forEach((field) => { field.disabled = !active; field.required = active && (field.name === 'url' || field.name === 'headline' || field.name === 'body'); });
    });
  };
  tabs.forEach((tab) => tab.addEventListener('click', () => setMode(tab.dataset.mode)));
  if (tabs.length) setMode(modeInput?.value || 'url');

  const text = document.querySelector('#body');
  const counter = document.querySelector('#word-count');
  const updateCount = () => { if (text && counter) { const value = text.value.trim(); const words = value ? value.split(/\s+/).length : 0; counter.textContent = `${words.toLocaleString()} words · ${text.value.length.toLocaleString()} characters`; } };
  text?.addEventListener('input', updateCount);
  updateCount();

  const form = document.querySelector('#analysis-form');
  form?.addEventListener('submit', () => {
    const button = form.querySelector('.submit');
    const pipeline = document.querySelector('#pipeline');
    const label = document.querySelector('#pipeline-label');
    if (button) { button.disabled = true; button.classList.add('loading'); }
    if (pipeline) pipeline.hidden = false;
    const stages = ['Submitting article', 'Fetching page and metadata', 'Analyzing source and language', 'Preparing your report'];
    let index = 0;
    window.setInterval(() => { index = Math.min(index + 1, stages.length - 1); if (label) label.textContent = stages[index]; pipeline?.querySelectorAll('li').forEach((step, i) => { step.classList.toggle('active', i === Math.min(index, 3)); step.classList.toggle('done', i < index); }); }, 1200);
  });

  document.querySelectorAll('.count-score').forEach((element) => {
    const target = Number(element.dataset.score) || 0;
    if (reduceMotion) { element.textContent = String(Math.round(target)); return; }
    const ring = element.closest('.score-ring');
    if (ring) ring.style.setProperty('--score', '0');
    const start = performance.now();
    const duration = 1000;
    const tick = (now) => { const ratio = Math.min((now - start) / duration, 1); const eased = 1 - Math.pow(1 - ratio, 3); const value = target * eased; element.textContent = String(Math.round(value)); if (ring) ring.style.setProperty('--score', String(value)); if (ratio < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  });

  const search = document.querySelector('#history-search');
  const historyRows = [...document.querySelectorAll('.history-row')];
  const emptySearch = document.querySelector('.empty-search');
  search?.addEventListener('input', () => {
    const query = search.value.trim().toLowerCase(); let visible = 0;
    historyRows.forEach((row) => { const match = row.textContent.toLowerCase().includes(query); row.hidden = !match; if (match) visible += 1; });
    if (emptySearch) emptySearch.hidden = visible > 0;
  });
})();
