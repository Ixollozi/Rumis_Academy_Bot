from aiogram import Router

from app.handlers.admin import applications, dates, export, post_exam, prices, results

router = Router(name="admin")
router.include_router(dates.router)
router.include_router(applications.router)
router.include_router(prices.router)
router.include_router(results.router)
router.include_router(post_exam.router)
router.include_router(export.router)
