"""Application exceptions. Messages are safe to return to API clients."""


class AppError(Exception):
    status_code = 500
    code = "internal_error"
    default_message = "An unexpected error occurred."

    def __init__(self, message=None, *, details=None, code=None):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.details = details or {}
        if code:
            self.code = code


class ValidationError(AppError):
    status_code = 400
    code = "validation_error"
    default_message = "The request is invalid."


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = "A valid Supabase access token is required."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "You do not have permission to perform this operation."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "The request conflicts with the current state."


class DatabaseError(AppError):
    status_code = 503
    code = "database_unavailable"
    default_message = "The database is unavailable or returned an error."


class ExternalServiceError(AppError):
    status_code = 502
    code = "external_service_error"
    default_message = "An upstream service failed."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    default_message = "The service is not configured or unavailable."
