(() => {
  const form = document.querySelector('[data-photo-editor]');
  if (!form) return;
  const input = form.querySelector('input[type=file]');
  const feedback = form.querySelector('[data-photo-feedback]');
  const remove = form.querySelector('[data-remove-photo]');
  let busy = false;
  async function save(action) {
    if (busy) return;
    if (action === 'upload') {
      const file = input.files[0];
      if (!file || !/\.(jpe?g|png|webp)$/i.test(file.name) ||
          !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        feedback.textContent = 'Choose a JPG, PNG or WebP image.';
        return;
      }
      if (file.size > 2 * 1024 * 1024) {
        feedback.textContent = 'Choose an image no larger than 2 MB.';
        return;
      }
    }
    const data = new FormData(form);
    data.set('action', action);
    if (action === 'remove') data.delete('photo');
    busy = true;
    form.querySelectorAll('button, input[type=file]').forEach(el => el.disabled = true);
    feedback.textContent = action === 'upload' ? 'Uploading picture…' : 'Removing uploaded picture…';
    try {
      const response = await fetch(form.action, { method: 'POST', body: data, credentials: 'same-origin' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to update your picture. Please try again.');
      // Refresh only this user's pictures, leaving the rest of the page intact.
      document.querySelectorAll('[data-own-avatar] .fs-avatar').forEach(avatar => {
        avatar.querySelector('img')?.remove();
        if (result.avatar_url) {
          const image = document.createElement('img');
          image.alt = '';
          image.referrerPolicy = 'no-referrer';
          image.dataset.avatarImage = '';
          image.addEventListener('error', () => { image.hidden = true; });
          const url = new URL(result.avatar_url, window.location.origin);
          if (url.origin === window.location.origin) url.searchParams.set('v', Date.now());
          image.src = url.href;
          avatar.append(image);
        }
      });
      remove.hidden = !result.has_upload;
      input.value = '';
      feedback.textContent = result.has_upload ? 'Profile picture updated.' : 'Uploaded picture removed. Using your Google photo or initials.';
    } catch (error) {
      feedback.textContent = error.message || 'Unable to update your picture. Please try again.';
    } finally {
      busy = false;
      form.querySelectorAll('button, input[type=file]').forEach(el => el.disabled = false);
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); save('upload'); });
  remove.addEventListener('click', () => save('remove'));
})();
