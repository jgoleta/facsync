"""Presentation-only steps; no changes to onboarding transitions or permissions."""

STEPS = (
    ('inquiry_form', 'Inquiry', 'Tell us which school you represent.'),
    ('inquiry', 'Initial review', 'The Super Admin reviews your inquiry. Watch your email for a private verification invitation.'),
    ('verification_wait', 'Verification', 'Complete the private verification form and provide your authorization letter.'),
    ('verification_review', 'Verification review', 'The Super Admin checks the school details and your authority. The next steps will arrive by email.'),
    ('registration_wait', 'Registration', 'Complete your school details using the private registration invitation.'),
    ('registration_review', 'Final review', 'Your registration is submitted. Wait for the Super Admin’s approval; you do not need to submit again.'),
    ('approved', 'Approved', 'Your school is approved. Use the School Admin invitation to sign in and activate your account.'),
)


def onboarding_progress(stage):
    current = next((index for index, (key, _, _) in enumerate(STEPS, 1) if key == stage), None)
    if current is None:
        return None
    return {
        'current': current, 'total': len(STEPS), 'label': STEPS[current - 1][1],
        'description': STEPS[current - 1][2], 'complete': stage == 'approved',
        'percent': round((current - 1) / (len(STEPS) - 1) * 100),
        'steps': [{'number': index, 'label': label,
            'state': 'complete' if index < current or stage == 'approved' else 'current' if index == current else 'upcoming'}
            for index, (_, label, _) in enumerate(STEPS, 1)],
    }
