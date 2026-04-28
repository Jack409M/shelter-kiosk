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

const cwrPanels = document.querySelectorAll('.cwr-panel');
const cwrPlaceholder = document.querySelector('.cwr-panel-placeholder');

cwrPanels.forEach((panel) => {
  panel.hidden = true;
  panel.classList.remove('is-open');
});

document.querySelectorAll('.cwr-question').forEach((question) => {
  question.addEventListener('click', () => {
    const panelName = question.dataset.panel;
    const panel = document.getElementById('cwr-panel-' + panelName);

    document.querySelectorAll('.cwr-question').forEach((item) => {
      item.classList.remove('is-active');
    });
    question.classList.add('is-active');

    cwrPanels.forEach((item) => {
      item.hidden = true;
      item.classList.remove('is-open');
    });

    if (cwrPlaceholder) {
      cwrPlaceholder.hidden = true;
      cwrPlaceholder.classList.add('is-hidden');
    }

    if (panel) {
      panel.hidden = false;
      panel.classList.add('is-open');
    }
  });
});
