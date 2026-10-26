"""Domain errors raised by services. main.py turns them into the same JSON bodies FastAPI uses."""


class AppError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class ValidationFailed(AppError):
    status_code = 400


class NotFound(AppError):
    status_code = 404
