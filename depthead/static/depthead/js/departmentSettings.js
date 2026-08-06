(function(){
    const STORAGE_KEY = 'dept_announcements';

    function $(sel, ctx=document){ return ctx.querySelector(sel); }
    function $all(sel, ctx=document){ return Array.from(ctx.querySelectorAll(sel)); }

    function loadAnnouncements(){
        try{
            const raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : [];
        }catch(e){ console.error('Failed to parse announcements', e); return []; }
    }
    function saveAnnouncements(list){
        localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    }

    function renderAnnouncements(){
        const list = loadAnnouncements();
        const container = $('#announcements-list');
        container.innerHTML = '';
        if(list.length === 0){
            container.innerHTML = '<p>No announcements yet.</p>';
            return;
        }
        list.sort((a,b)=> b.createdAt - a.createdAt);
        list.forEach(item=>{
            const el = document.createElement('div');
            el.className = 'announcement-item';
            const date = new Date(item.createdAt);
            el.innerHTML = `
                <div class="meta">
                    <div>
                        <div class="title">${escapeHtml(item.title || '(No title)')}</div>
                        <div class="small muted">${date.toLocaleString()}</div>
                    </div>
                    <div class="status">${item.published ? 'Published' : 'Draft'}</div>
                </div>
                <div class="message">${escapeHtml(item.message || '')}</div>
                <div class="announcement-controls">
                    <button data-action="toggle" data-id="${item.id}">${item.published ? 'Unpublish' : 'Publish'}</button>
                    <button data-action="delete" data-id="${item.id}" class="btn-danger">Delete</button>
                </div>
            `;
            container.appendChild(el);
        });
    }

    function escapeHtml(str){
        if(!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function addAnnouncement(title, message, published){
        const list = loadAnnouncements();
        const item = {
            id: 'a_' + Date.now() + '_' + Math.floor(Math.random()*1000),
            title: title || '',
            message: message || '',
            published: !!published,
            createdAt: Date.now()
        };
        list.push(item);
        saveAnnouncements(list);
        renderAnnouncements();
    }

    function togglePublish(id){
        const list = loadAnnouncements();
        const idx = list.findIndex(i=> i.id===id);
        if(idx === -1) return;
        list[idx].published = !list[idx].published;
        saveAnnouncements(list);
        renderAnnouncements();
    }

    function deleteAnnouncement(id){
        let list = loadAnnouncements();
        list = list.filter(i=> i.id !== id);
        saveAnnouncements(list);
        renderAnnouncements();
    }

    document.addEventListener('DOMContentLoaded', ()=>{
        const form = $('#announcement-form');
        renderAnnouncements();

        if(form){
            form.addEventListener('submit', (e)=>{
                e.preventDefault();
                const title = $('#ann-title').value.trim();
                const message = $('#ann-message').value.trim();
                const published = $('#ann-publish').checked;
                if(!title && !message){
                    alert('Please provide a title or message for the announcement.');
                    return;
                }
                addAnnouncement(title, message, published);
                form.reset();
            });
        }

        const container = $('#announcements-list');
        container && container.addEventListener('click', (e)=>{
            const btn = e.target.closest('button[data-action]');
            if(!btn) return;
            const id = btn.getAttribute('data-id');
            const action = btn.getAttribute('data-action');
            if(action === 'toggle') togglePublish(id);
            if(action === 'delete'){
                if(confirm('Delete this announcement?')) deleteAnnouncement(id);
            }
        });
    });

})();
