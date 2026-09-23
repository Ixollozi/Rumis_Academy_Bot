from aiogram import Router

from app.handlers.admin import (
    admins,
    applications,
    dates,
    export,
    notifications,
    post_exam,
    prices,
    results,
)

router = Router(name="admin")
router.include_router(dates.router)
router.include_router(applications.router)
router.include_router(prices.router)
router.include_router(results.router)
router.include_router(post_exam.router)
router.include_router(notifications.router)
router.include_router(admins.router)
router.include_router(export.router)
