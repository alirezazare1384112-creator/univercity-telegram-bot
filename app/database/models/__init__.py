"""ORM models.

Importing this package registers every model on ``Base.metadata``,
which is what Alembic autogenerate uses to detect schema changes.
"""

from app.database.models.admin import Admin
from app.database.models.announcement import Announcement
from app.database.models.base import Base, utcnow
from app.database.models.calendar_event import CalendarEvent
from app.database.models.course import Course
from app.database.models.grade import GradeItem
from app.database.models.link import UniversityLink
from app.database.models.note import Note
from app.database.models.notification import NotificationLog
from app.database.models.reminder import Reminder, ReminderNotification
from app.database.models.schedule import WeeklySchedule
from app.database.models.user import User

__all__ = [
    "Admin",
    "Announcement",
    "Base",
    "CalendarEvent",
    "Course",
    "GradeItem",
    "Note",
    "NotificationLog",
    "Reminder",
    "ReminderNotification",
    "UniversityLink",
    "User",
    "WeeklySchedule",
    "utcnow",
]
