from fastapi import Request
from fastapi.responses import JSONResponse


async def error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "内部服务错误", "error": str(exc)},
    )


async def not_found_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=404,
        content={"detail": "资源不存在"},
    )
