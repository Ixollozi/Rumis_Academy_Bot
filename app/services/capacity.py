from app.db import repo

# Re-export capacity helpers used by handlers
list_available_exam_dates = repo.list_available_exam_dates
is_date_available = repo.is_date_available
paid_count_for_date = repo.paid_count_for_date
