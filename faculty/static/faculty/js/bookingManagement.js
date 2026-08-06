document.addEventListener('DOMContentLoaded', () => {
    const queueList = document.getElementById('queueList');
    const queueCount = document.getElementById('queueCount');
    const refreshQueueBtn = document.getElementById('refreshQueueBtn');

    let queueData = [
        {
            id: 1,
            name: 'Emily Carter',
            major: 'Computer Science',
            note: 'Needs help finalizing project timeline.',
            queuedAt: '10:05 AM',
            status: 'pending'
        },
        {
            id: 2,
            name: 'Mateo Alvarez',
            major: 'Data Science',
            note: 'Follow-up on last week’s grading rubric.',
            queuedAt: '10:12 AM',
            status: 'pending'
        },
        {
            id: 3,
            name: 'Priya Shah',
            major: 'Information Systems',
            note: 'Discuss conference presentation draft.',
            queuedAt: '10:20 AM',
            status: 'pending'
        },
        {
            id: 4,
            name: 'Noah Patel',
            major: 'Software Engineering',
            note: 'Ask about application deployment.',
            queuedAt: '10:28 AM',
            status: 'completed'
        }
    ];

    function renderQueueList() {
        queueList.innerHTML = '';
        const pendingStudents = queueData.filter(student => student.status === 'pending');

        queueCount.textContent = pendingStudents.length;

        if (pendingStudents.length === 0) {
            queueList.innerHTML = '<li class="queue-item empty-state"><p>There are no students in the queue.</p></li>';
            return;
        }

        pendingStudents.forEach((student) => {
            const item = document.createElement('li');
            item.className = 'queue-item';
            item.dataset.id = student.id;
            item.innerHTML = `
                <div class="queue-summary">
                    <p class="student-name">${student.name}</p>
                    <p class="student-meta">${student.major}</p>
                    <p class="student-note">${student.note}</p>
                    <p class="student-meta">Queued at ${student.queuedAt}</p>
                </div>
                <div class="queue-item-actions">
                    <button class="btn-mark-complete" data-id="${student.id}">Mark Complete</button>
                </div>
            `;
            queueList.appendChild(item);
        });
    }

    function markStudentAsComplete(studentId) {
        const student = queueData.find(s => s.id === studentId);
        if (student) {
            student.status = 'completed';
            console.log(`Student ${student.name} marked as complete.`);
        }
        renderQueueList();
    }

    queueList.addEventListener('click', (event) => {
        const completeBtn = event.target.closest('.btn-mark-complete');
        if (completeBtn) {
            const studentId = Number(completeBtn.dataset.id);
            markStudentAsComplete(studentId);
        }
    });

    refreshQueueBtn.addEventListener('click', () => {
        renderQueueList();
    });

    renderQueueList();
});
