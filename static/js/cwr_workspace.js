document.querySelectorAll('.cwr-mode-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const mode = btn.dataset.mode;

    document.querySelectorAll('.cwr-mode-btn').forEach((item) => {
      item.classList.remove('is-active');
    });
    btn.classList.add('is-active');

    document.querySelectorAll('.cwr-mode').forEach((section) => {
      section.classList.remove('is-active');
    });

    const activeSection = document.getElementById('cwr-' + mode);
    if (activeSection) {
      activeSection.classList.add('is-active');
    }
  });
});

document.querySelectorAll('.cwr-question').forEach((question) => {
  question.addEventListener('click', () => {
    const panelName = question.dataset.panel;
    const panel = document.getElementById('cwr-panel-' + panelName);

    document.querySelectorAll('.cwr-question').forEach((item) => {
      item.classList.remove('is-active');
    });
    question.classList.add('is-active');

    document.querySelectorAll('.cwr-panel').forEach((item) => {
      item.classList.remove('is-open');
    });

    const placeholder = document.querySelector('.cwr-panel-placeholder');
    if (placeholder) {
      placeholder.classList.add('is-hidden');
    }

    if (panel) {
      panel.classList.add('is-open');
    }
  });
});
