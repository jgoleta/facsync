document.addEventListener('DOMContentLoaded', () => {
    const dialog = document.getElementById('consultationRatingDialog');
    const form = document.getElementById('consultationRatingForm');
    if (!dialog || !form) return;
    const error = document.getElementById('ratingError');
    const save = document.getElementById('saveRating');
    const cancel = document.getElementById('closeRatingDialog');
    const closeIcon = document.getElementById('closeRatingDialogIcon');
    const selectionHint = document.getElementById('ratingSelectionHint');
    const studentFeedback = window.studentFeedback;
    let trigger;
    let saving = false;
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-rating-url]');
        if (!button) return;
        trigger = button;
        form.reset();
        form.action = button.dataset.ratingUrl;
        error.hidden = true;
        document.getElementById('ratingFaculty').textContent = `Consultation with ${button.dataset.faculty}`;
        const selected = [...form.elements.rating].find(input => input.value === button.dataset.rating);
        if (selected) selected.checked = true;
        selectionHint.textContent = selected ? `Selected score: ${selected.value}/5` : 'Select a score from 1 to 5.';
        save.textContent = button.dataset.rating ? 'Save rating' : 'Submit rating';
        dialog.showModal();
        (selected || form.elements.rating[0])?.focus();
    });
    cancel.addEventListener('click', () => dialog.close());
    closeIcon.addEventListener('click', () => dialog.close());
    form.addEventListener('change', event => {
        if (event.target.name === 'rating') selectionHint.textContent = `Selected score: ${event.target.value}/5`;
    });
    dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
    dialog.addEventListener('close', () => trigger?.focus());
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (saving) return;
        saving = true;
        save.disabled = cancel.disabled = true;
        save.textContent = 'Saving...';
        dialog.close();
        studentFeedback?.showLoading('Saving your rating...');
        error.hidden = true;
        try {
            const response = await fetch(form.action, {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.elements.csrfmiddlewaretoken.value},
                body: JSON.stringify({rating: Number(new FormData(form).get('rating'))}),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Unable to save your rating. Please try again.');
            window.location.reload();
        } catch (failure) {
            error.textContent = failure.message;
            error.hidden = false;
            dialog.showModal();
            save.focus();
        } finally {
            saving = false;
            save.disabled = cancel.disabled = false;
            save.textContent = trigger?.dataset.rating ? 'Save rating' : 'Submit rating';
            studentFeedback?.hideLoading();
        }
    });
});
