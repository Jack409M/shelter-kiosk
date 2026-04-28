document.querySelectorAll('.cwr-mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.cwr-mode-btn').forEach(b => b.classList.remove('is-active'));
    btn.classList.add('is-active');

    const mode = btn.dataset.mode;
    document.querySelectorAll('.cwr-mode').forEach(m => m.classList.remove('is-active'));
    document.getElementById('cwr-' + mode).classList.add('is-active');
  });
});

function openModal(type) {
  const modal = document.getElementById('cwr-modal');
  const content = document.getElementById('cwr-modal-content');
  const template = document.querySelector(`[data-modal="${type}"]`);

  content.innerHTML = template.innerHTML;
  modal.classList.remove('hidden');
}

window.addEventListener('click', function(e) {
  const modal = document.getElementById('cwr-modal');
  if (e.target === modal) {
    modal.classList.add('hidden');
  }
});
