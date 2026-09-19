from aiogram import Router

from app.handlers import booking, location, menu, my_tests, results, start
from app.handlers.admin import router as admin_router


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(menu.router)
    root.include_router(booking.router)
    root.include_router(my_tests.router)
    root.include_router(results.router)
    root.include_router(location.router)
    root.include_router(admin_router)
    return root
