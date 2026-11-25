(() => {
  const form = document.querySelector('#facultyInviteModal form');
  if (!form) return;
  form.addEventListener('management:open', event => {
    const checkbox = form.elements.namedItem('prepare_test_requests');
    if (checkbox) checkbox.checked = event.detail.trigger.dataset.prepareTestRequests === 'true';
  });
})();
