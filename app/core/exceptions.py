from fastapi import HTTPException, status


class AppError(Exception):
    """Base application error."""
    def __init__(self, message: str, code: str = "APP_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, id: str):
        super().__init__(f"{resource} with id '{id}' not found", "NOT_FOUND")


class OrderAlreadyAssignedError(AppError):
    def __init__(self):
        super().__init__("Order is already assigned or not pending", "ORDER_ALREADY_ASSIGNED")


class NoDriverAvailableError(AppError):
    def __init__(self):
        super().__init__("No available driver found nearby", "NO_DRIVER_AVAILABLE")


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_ERROR")


class PermissionDeniedError(AppError):
    def __init__(self):
        super().__init__("You don't have permission for this action", "PERMISSION_DENIED")


# Map to HTTP exceptions
def to_http_exception(error: AppError) -> HTTPException:
    mapping = {
        "NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "ORDER_ALREADY_ASSIGNED": status.HTTP_409_CONFLICT,
        "NO_DRIVER_AVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "AUTH_ERROR": status.HTTP_401_UNAUTHORIZED,
        "PERMISSION_DENIED": status.HTTP_403_FORBIDDEN,
    }
    status_code = mapping.get(error.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=status_code, detail={"code": error.code, "message": error.message})
