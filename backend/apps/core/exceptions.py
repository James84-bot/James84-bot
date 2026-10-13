"""Error handling.

Business rule violations raise `BusinessRuleError` from the service layer. The
API turns them into HTTP 400 (or 409 for conflicts) with a plain-English
message the person at the counter can act on, plus a stable `code` the
frontend can branch on.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class BusinessRuleError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, code: str = "rule_violation", **context):
        super().__init__(message)
        self.message = message
        self.code = code
        self.context = context


class ConflictError(BusinessRuleError):
    """The record changed underneath the request (e.g. already approved)."""

    status_code = status.HTTP_409_CONFLICT


def exception_handler(exc, context):
    if isinstance(exc, BusinessRuleError):
        body = {"detail": exc.message, "code": exc.code}
        if exc.context:
            body["context"] = exc.context
        return Response(body, status=exc.status_code)
    if isinstance(exc, DjangoValidationError):
        exc = DRFValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
    return drf_exception_handler(exc, context)
