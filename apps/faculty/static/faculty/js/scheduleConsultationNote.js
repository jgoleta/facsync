document.addEventListener('DOMContentLoaded', () => {
    const note = document.getElementById('schedule-consultation-note');
    if (!note) return;

    const text = document.getElementById('schedule-consultation-note-text');
    const input = document.getElementById('schedule-consultation-note-input');
    const editButton = document.getElementById('edit-schedule-consultation-note');
    const saveButton = document.getElementById('save-schedule-consultation-note');
    const cancelButton = document.getElementById('cancel-schedule-consultation-note');
    const count = document.getElementById('schedule-consultation-note-count');
    const profileUrl = note.dataset.profileUrl;

    const csrfToken = document.cookie.split('; ')
        .find((row) => row.startsWith('csrftoken='))?.split('=')[1] || '';

    const updateCount = () => {
        count.textContent = `${input.value.length}/255`;
    };

    const closeEditor = () => {
        text.classList.remove('hidden');
        editButton.classList.remove('hidden');
        input.classList.add('hidden');
        saveButton.classList.add('hidden');
        cancelButton.classList.add('hidden');
        updateCount();
    };

    editButton.addEventListener('click', () => {
        text.classList.add('hidden');
        editButton.classList.add('hidden');
        input.classList.remove('hidden');
        saveButton.classList.remove('hidden');
        cancelButton.classList.remove('hidden');
        input.value = text.textContent === 'Not provided' ? '' : text.textContent;
        updateCount();
        input.focus();
    });

    input.addEventListener('input', updateCount);
    cancelButton.addEventListener('click', closeEditor);
    input.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') closeEditor();
    });

    saveButton.addEventListener('click', async () => {
        saveButton.disabled = true;
        try {
            const value = input.value.trim();
            const response = await fetch(profileUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': decodeURIComponent(csrfToken),
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({ field: 'consultation_note', value }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.error || 'Unable to save consultation note.');

            text.textContent = data.value || 'Not provided';
            closeEditor();
            window.facultyFeedback?.showToast('Consultation note saved successfully.');
        } catch (error) {
            window.facultyFeedback?.showToast(error.message, true);
        } finally {
            saveButton.disabled = false;
        }
    });
});
