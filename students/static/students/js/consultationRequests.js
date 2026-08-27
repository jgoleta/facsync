document.addEventListener('DOMContentLoaded', () => {
    const statusFilter = document.getElementById('statusFilter');
    const requestList = document.querySelector('.consultation-request-list');

    function applyFilter() {
        const filter = statusFilter?.value || 'all';
        requestList?.querySelectorAll('.request-item').forEach(item => {
            item.style.display = filter === 'all' || item.dataset.status === filter ? 'flex' : 'none';
        });
    }

    if (statusFilter) {
        statusFilter.addEventListener('change', applyFilter);
    }

    async function removeFinishedRequests() {
        if (!requestList) return;
        try {
            const response = await fetch('/student/api/consultation-requests/', { cache: 'no-store' });
            const data = await response.json();
            if (!response.ok) return;

            const activeRequestIds = new Set(
                (data.consultations || []).map(consultation => consultation.request_id),
            );
            requestList.querySelectorAll('.request-item').forEach(item => {
                if (!activeRequestIds.has(item.dataset.requestId)) {
                    item.remove();
                }
            });

            if (!requestList.querySelector('.request-item')) {
                let emptyState = requestList.querySelector('.empty-state');
                if (!emptyState) {
                    emptyState = document.createElement('li');
                    emptyState.className = 'empty-state';
                    emptyState.textContent = 'You have no active consultation requests.';
                    requestList.appendChild(emptyState);
                }
            }
            applyFilter();
        } catch (error) {
            // Keep the current list visible if the refresh is temporarily unavailable.
        }
    }

    applyFilter();
    window.setInterval(removeFinishedRequests, 10000);
});
