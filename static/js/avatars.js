/* Images sit over the existing placeholder; a failed image reveals it again. */
(() => {
  function hideFailedImage(event) {
    const image = event.target;
    if (image && image.matches && image.matches('[data-avatar-image]')) image.hidden = true;
  }
  document.addEventListener('error', hideFailedImage, true);
  document.querySelectorAll('[data-avatar-image]').forEach(image => {
    if (image.complete && image.naturalWidth === 0) image.hidden = true;
  });
})();
