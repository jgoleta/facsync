document.addEventListener('DOMContentLoaded', () => {
    const statusFilter = document.getElementById('statusFilter');
    const requestList = document.querySelector('.consultation-request-list');
    const requestResultCount = document.getElementById('requestResultCount');

    function applyFilter() {
        const filter = statusFilter?.value || 'all';
        let visibleCount = 0;
        const requestItems = requestList?.querySelectorAll('.request-item') || [];
        requestItems.forEach(item => {
            const visible = filter === 'all' || item.dataset.status === filter;
            item.style.display = visible ? 'flex' : 'none';
            if (visible) visibleCount += 1;
        });
        requestList?.querySelector('.filtered-empty-state')?.remove();
        if (requestItems.length && visibleCount === 0 && requestList) {
            const emptyState = document.createElement('li');
            emptyState.className = 'filtered-empty-state';
            emptyState.textContent = `No ${filter} consultation requests.`;
            requestList.appendChild(emptyState);
        }
        if (requestResultCount) {
            requestResultCount.textContent = `${visibleCount} request${visibleCount === 1 ? '' : 's'}`;
        }
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
