document.addEventListener('DOMContentLoaded', () => {
    const statusFilter = document.getElementById('statusFilter');
    const requestItems = document.querySelectorAll('.request-item');

    if (statusFilter && requestItems.length > 0) {
        statusFilter.addEventListener('change', () => {
            const filter = statusFilter.value;

            requestItems.forEach(item => {
                if (filter === 'all' || item.dataset.status === filter) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        });
    }
});