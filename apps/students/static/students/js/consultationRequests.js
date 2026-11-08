document.addEventListener('DOMContentLoaded', () => {
    const statusFilter = document.getElementById('statusFilter');
    const requestList = document.querySelector('.consultation-request-list');
    const requestResultCount = document.getElementById('requestResultCount');
    const requestPagination = document.getElementById('requestPagination');
    const REQUESTS_PER_PAGE = 12;
    let currentPage = 1;
    const actionModal = document.getElementById('consultationActionModal');
    const actionTitle = document.getElementById('consultationActionTitle');
    const actionMessage = document.getElementById('consultationActionMessage');
    const cancelActionButton = document.getElementById('cancelConsultationAction');
    const confirmActionButton = document.getElementById('confirmConsultationAction');
    let resolveActionConfirmation;

    function closeActionModal(confirmed) {
        actionModal?.classList.add('hidden');
        if (resolveActionConfirmation) {
            const resolve = resolveActionConfirmation;
            resolveActionConfirmation = null;
            resolve(confirmed);
        }
    }

    function showActionModal(title, message, confirmLabel) {
        return new Promise(resolve => {
            resolveActionConfirmation = resolve;
            if (actionTitle) actionTitle.textContent = title;
            if (actionMessage) actionMessage.textContent = message;
            if (confirmActionButton) confirmActionButton.textContent = confirmLabel;
            actionModal?.classList.remove('hidden');
            cancelActionButton?.focus();
        });
    }

    cancelActionButton?.addEventListener('click', () => closeActionModal(false));
    confirmActionButton?.addEventListener('click', () => closeActionModal(true));
    actionModal?.addEventListener('click', event => {
        if (event.target === actionModal) closeActionModal(false);
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && actionModal && !actionModal.classList.contains('hidden')) {
            closeActionModal(false);
        }
    });

    requestList?.addEventListener('click', async (event) => {
        const button = event.target.closest('.delete-request-btn');
        if (!button || button.disabled) return;
        if (!(await showActionModal(
            'Delete consultation request?',
            'This consultation request will be permanently deleted. Any linked calendar appointment will also be removed.',
            'Delete Request',
        ))) return;
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

    function renderPagination(pageCount) {
        if (!requestPagination) return;
        requestPagination.replaceChildren();
        const totalPages = Math.max(1, pageCount);

        const addNavigationButton = (label, page, ariaLabel) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'request-page-button request-page-navigation';
            button.textContent = label;
            button.setAttribute('aria-label', ariaLabel);
            button.disabled = page < 1 || page > totalPages || totalPages === 1;
            button.addEventListener('click', () => {
                currentPage = page;
                applyFilter();
                requestList?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
            requestPagination.appendChild(button);
        };

        addNavigationButton('<', currentPage - 1, 'Go to previous consultation request page');
        for (let page = 1; page <= totalPages; page += 1) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `request-page-button${page === currentPage ? ' active' : ''}`;
            button.textContent = String(page);
            button.setAttribute('aria-label', `Go to consultation request page ${page}`);
            button.setAttribute('aria-current', page === currentPage ? 'page' : 'false');
            button.disabled = totalPages === 1;
            button.addEventListener('click', () => {
                currentPage = page;
                applyFilter();
                requestList?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
            requestPagination.appendChild(button);
        }
        addNavigationButton('>', currentPage + 1, 'Go to next consultation request page');
    }

    function applyFilter(resetPage = false) {
        if (resetPage) currentPage = 1;
        const filter = statusFilter?.value || 'all';
        const requestItems = requestList?.querySelectorAll('.request-item') || [];
        const matchingItems = [];
        requestItems.forEach(item => {
            const visible = filter === 'all' || item.dataset.status === filter;
            if (visible) matchingItems.push(item);
        });
        const pageCount = Math.ceil(matchingItems.length / REQUESTS_PER_PAGE);
        currentPage = pageCount ? Math.min(currentPage, pageCount) : 1;
        const pageStart = (currentPage - 1) * REQUESTS_PER_PAGE;
        const pageItems = new Set(matchingItems.slice(pageStart, pageStart + REQUESTS_PER_PAGE));
        requestItems.forEach(item => {
            item.style.display = pageItems.has(item) ? 'flex' : 'none';
        });
        renderPagination(pageCount);
        requestList?.querySelector('.filtered-empty-state')?.remove();
        if (requestItems.length && matchingItems.length === 0 && requestList) {
            const emptyState = document.createElement('li');
            emptyState.className = 'filtered-empty-state';
            emptyState.textContent = `No ${filter} consultation requests.`;
            requestList.appendChild(emptyState);
        }
        if (requestResultCount) {
            requestResultCount.textContent = `${matchingItems.length} request${matchingItems.length === 1 ? '' : 's'}`;
        }
    }

    if (statusFilter) {
        statusFilter.addEventListener('change', () => applyFilter(true));
    }

    async function removeFinishedRequests() {
        if (!requestList) return;
        try {
            const response = await fetch('/student/api/consultation-requests/', { cache: 'no-store' });
            const data = await response.json();
            if (!response.ok) return;

            // A faculty decision changes the badge and available actions, not just list membership.
            const updated = new Map((data.consultations || []).map(item => [item.request_id, item]));
            if ([...requestList.querySelectorAll('.request-item')].some(item =>
                updated.has(item.dataset.requestId)
                && (updated.get(item.dataset.requestId).status !== item.dataset.status
                    || (updated.get(item.dataset.requestId).google_meet_link || '') !== (item.dataset.meetLink || '')))) {
                window.location.reload();
                return;
            }

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

    applyFilter(true);
    window.setInterval(removeFinishedRequests, 10000);
});
