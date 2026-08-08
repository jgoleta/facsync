from faculty.models import StatusHistory as FacultyStatusHistory
from faculty.models import WalkInQueue as FacultyWalkInQueue


class StudentWalkInQueue(FacultyWalkInQueue):
    class Meta:
        proxy = True
        app_label = 'students'
        verbose_name = 'Student Walk-In Queue'
        verbose_name_plural = 'Student Walk-In Queues'


class StudentStatusHistory(FacultyStatusHistory):
    class Meta:
        proxy = True
        app_label = 'students'
        verbose_name = 'Student Status History'
        verbose_name_plural = 'Student Status Histories'
