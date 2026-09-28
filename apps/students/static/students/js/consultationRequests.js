document.addEventListener('DOMContentLoaded', () => {
    const statusFilter = document.getElementById('statusFilter');
    const requestList = document.querySelector('.consultation-request-list');
    const requestResultCount = document.getElementById('requestResultCount');

    requestList?.addEventListener('click', async (event) => {
        const button = event.target.closest('.delete-request-btn');
        if (!button || button.disabled) return;
        if (!window.confirm('Delete this consultation request permanently? Any linked calendar appointment will also be removed.')) return;
        button.disabled = true;
        const feedback = window.studentFeedback;
        feedback?.showLoading('Deleting consultation request...');
        try {
            const cookie = document.cookie.split('; ').find(value => value.startsWith('csrftoken='));
            const response = await fetch(button.dataset.deleteUrl, {
                method: 'DELETE',
                headers: { 'X-CSRFToken': cookie ? decodeURIComponent(cookie.slice('csrftoken='.length)) : '' },
            });
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.error || 'Unable to delete this request. Please try again.');
            }
            button.closest('.request-item').remove();
            if (!requestList.querySelector('.request-item') && !requestList.querySelector('.empty-state')) {
                const empty = document.createElement('li');
                empty.className = 'empty-state';
                empty.textContent = 'You have no active consultation requests.';
                requestList.appendChild(empty);
            }
            applyFilter();
            feedback?.showToast('Consultation request deleted.');
        } catch (error) {
            feedback?.showToast(error.message, true);
        } finally {
            button.disabled = false;
            feedback?.hideLoading();
        }
    });

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
