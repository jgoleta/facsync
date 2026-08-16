# FacSync
An automated real-time faculty availability and consultation scheduling system with Google Calendar integration, built for Ateneo de Naga University (ADNU).

FacSync replaces fragmented, informal communication (Messenger, Google Chat, email) with a centralized platform where students can check faculty availability, book consultations, join a digital walk-in queue, and receive real-time notifications — all without needing to log in just to view faculty status.

# Features
+ Real-time availability status — 5 categories (Available, Busy, Virtual Only, On Leave, Unavailable), color-coded on a public, login-free dashboard
+ Automatic status updates — via Google Calendar sync and/or an uploaded weekly class schedule
Manual status updates — two-click toggle for faculty who don't use Google Calendar
+ Consultation scheduling — in-person or virtual (with auto-generated Google Meet links), with approve/decline workflow
+ Digital walk-in queue — join, track position, get notified when it's your turn
+ Weekly schedule management — faculty self-manage, or Department Heads upload on their behalf
+ Office/department closure status — visible to students in real time
+ Analytics dashboard — descriptive, pattern, and AI-generated prescriptive insights (Google Gemini API)
+ -based account management — pre-assigned roles with an approval workflow for self-registration

# Command
+ python -m venv venv
+ venv\Scripts\activate
+ pip install -r requirements.txt