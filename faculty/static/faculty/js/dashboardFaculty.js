document.addEventListener('DOMContentLoaded', () => {
    const statusButtons = document.querySelectorAll('.status-btn');
    const updateStatusButton = document.getElementById('updateStatusBtn');
    const statusMessage = document.getElementById('statusMessage');
    const liveStatusIndicator = document.getElementById('liveStatusIndicator');
    const liveStatusIcon = document.getElementById('liveStatusIcon');
    const liveStatusLabel = document.getElementById('liveStatusLabel');
    const liveStatusNote = document.getElementById('liveStatusNote');
    const statusFeedback = document.getElementById('statusFeedback');
    const updateStatusLabel = document.getElementById('updateStatusLabel');
    const statusIcons = {
        available: '✓',
        busy: '◷',
        virtual: '⌁',
        'on-leave': '☕',
        unavailable: '×',
    };
    let selectedStatus = document.querySelector('.status-btn.active')?.dataset.status || 'available';

    statusButtons.forEach((button) => {
        button.addEventListener('click', () => {
            statusButtons.forEach((item) => item.classList.remove('active'));
            button.classList.add('active');
            statusButtons.forEach((item) => item.setAttribute('aria-pressed', item === button ? 'true' : 'false'));
            selectedStatus = button.dataset.status;
        });
    });

    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
        return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
    }

    if (updateStatusButton) {
        updateStatusButton.addEventListener('click', async () => {
            updateStatusButton.disabled = true;
            if (updateStatusLabel) updateStatusLabel.textContent = 'Saving...';
            statusFeedback.className = 'status-feedback';
            statusFeedback.textContent = '';
            try {
                const response = await fetch('/faculty/api/status/', {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        status: selectedStatus,
                        note: statusMessage?.value || '',
                    }),
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Unable to update status.');

                liveStatusIndicator.className = `status-indicator ${data.status_css_class}`;
                if (liveStatusIcon) liveStatusIcon.textContent = statusIcons[selectedStatus];
                liveStatusLabel.textContent = data.label;
                liveStatusNote.textContent = data.note || 'No status note set.';
                statusFeedback.className = 'status-feedback success';
                statusFeedback.textContent = 'Status updated successfully.';
                if (updateStatusLabel) updateStatusLabel.textContent = 'Updated';
                window.setTimeout(() => { if (updateStatusLabel) updateStatusLabel.textContent = 'Update'; }, 1500);
            } catch (error) {
                statusFeedback.className = 'status-feedback error';
                statusFeedback.textContent = error.message;
                if (updateStatusLabel) updateStatusLabel.textContent = 'Update';
            } finally {
                updateStatusButton.disabled = false;
            }
        });
    }

    if (liveStatusIcon) liveStatusIcon.textContent = statusIcons[selectedStatus];

    // --- Consultation Request Filtering ---
    const filterButtons = document.querySelectorAll('.filter-btn');
    const requestItems = document.querySelectorAll('.request-item');

    if (filterButtons.length > 0 && requestItems.length > 0) {
        filterButtons.forEach(button => {
            button.addEventListener('click', () => {
                // Update active button
                filterButtons.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');

                const filter = button.dataset.filter;

                // Filter request items
                requestItems.forEach(item => {
                    if (filter === 'all' || item.dataset.status === filter) {
                        item.style.display = 'flex';
                    } else {
                        item.style.display = 'none';
                    }
                });
            });
        });
    }
    console.log('Faculty dashboard script loaded.');
});
