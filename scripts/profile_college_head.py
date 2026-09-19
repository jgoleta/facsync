"""Read-only authenticated page profiling using Debug Toolbar's SQL panel.
Run with development settings; no login/session database writes or AI requests.
"""
import os, sys, json, time
from pathlib import Path
from collections import Counter
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()
from django.conf import settings
from django.test import Client
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.urls import reverse
from apps.core.models import User
from apps.faculty.models import FacultyProfile
from debug_toolbar.panels.sql.panel import SQLPanel, _similar_query_key, _duplicate_query_key

account = sys.argv[1] if len(sys.argv)>1 else 'testdepthead'
user = User.objects.get(username=account, role='depthead')
# Exercise normal database-session middleware without persisting a login.
# SessionStore.load returns the authenticated test identity in memory only.
session_data = {SESSION_KEY: str(user.pk), BACKEND_SESSION_KEY: 'django.contrib.auth.backends.ModelBackend', HASH_SESSION_KEY: user.get_session_auth_hash()}
client = Client(HTTP_HOST='localhost', REMOTE_ADDR='127.0.0.1')
client.cookies[settings.SESSION_COOKIE_NAME] = 'a'*32
original = SQLPanel.generate_stats
captured = []
def collect(self, request, response):
    original(self, request, response)
    queries = self._queries
    similar = Counter(_similar_query_key(q) for q in queries)
    duplicate = Counter(_duplicate_query_key(q) for q in queries)
    captured.append(dict(query_count=len(queries),sql_ms=round(self._sql_time,3),
        similar_groups=sum(n>1 for n in similar.values()), similar_queries=sum(n for n in similar.values() if n>1),
        duplicate_groups=sum(n>1 for n in duplicate.values()),duplicate_queries=sum(n for n in duplicate.values() if n>1),
        duplicate_repeats=sum(n-1 for n in duplicate.values() if n>1),
        slowest=[{'ms':round(q['duration'],3),'sql':q['raw_sql']} for q in sorted(queries,key=lambda q:q['duration'],reverse=True)[:5]],
        similar_patterns=[{'count':n,'sql':sql} for sql,n in similar.most_common() if n>1]))
report={'account':account,'college':user.college,'active_faculty':FacultyProfile.objects.filter(college_id__iexact=user.college,user__role='faculty',user__account_status='active').count(),'session_note':'In-memory authenticated session; normal middleware and live DB. Session lookup itself excluded.','pages':[]}
with patch.object(SessionStore,'load',return_value=session_data), patch.object(SQLPanel,'generate_stats',collect):
    for page in ('admin_dashboard','peak_analytics','faculty_trends','student_behavior'):
        for run in range(1,3):
            start=time.perf_counter()
            response=client.get(reverse('depthead:'+page))
            assert response.status_code==200,(page,response.status_code)
            assert b'djDebug' in response.content, 'Toolbar not injected'
            result=captured[-1]
            result.update(page=page,run=run,wall_ms=round((time.perf_counter()-start)*1000,3))
            report['pages'].append(result)
            print(page,run,result['query_count'],result['sql_ms'],flush=True)
output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('docs/college-head-query-profile-'+account+'.json')
output.write_text(json.dumps(report,indent=2),encoding='utf-8')
