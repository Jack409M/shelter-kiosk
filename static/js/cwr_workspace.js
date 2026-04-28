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

function convertQuestionsToReportLines() {
  document.querySelectorAll('button.cwr-question').forEach((button) => {
    const line = document.createElement('div');
    line.className = button.className;
    line.dataset.panel = button.dataset.panel;
    line.setAttribute('role', 'button');
    line.setAttribute('tabindex', '0');
    line.innerHTML = button.innerHTML;
    button.replaceWith(line);
  });
}

function closeAllQuestionPanels(panels) {
  panels.forEach((item) => {
    item.hidden = true;
    item.classList.remove('is-open');
  });
}

convertQuestionsToReportLines();

const cwrPanels = document.querySelectorAll('.cwr-panel');
const cwrPlaceholder = document.querySelector('.cwr-panel-placeholder');

closeAllQuestionPanels(cwrPanels);

document.querySelectorAll('.cwr-question').forEach((question) => {
  const openPanel = () => {
    const panelName = question.dataset.panel;
    const panel = document.getElementById('cwr-panel-' + panelName);

    document.querySelectorAll('.cwr-question').forEach((item) => {
      item.classList.remove('is-active');
    });
    question.classList.add('is-active');

    closeAllQuestionPanels(cwrPanels);

    if (cwrPlaceholder) {
      cwrPlaceholder.hidden = true;
      cwrPlaceholder.classList.add('is-hidden');
    }

    if (panel) {
      panel.hidden = false;
      panel.classList.add('is-open');
    }
  };

  question.addEventListener('click', openPanel);
  question.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openPanel();
    }
  });
});
