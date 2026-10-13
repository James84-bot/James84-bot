"""Request ID middleware: tags every log line and response with an ID so a
user's error report can be matched to server logs."""

import uuid

from .logging import request_id_var


class RequestIdMiddleware:
    header = "HTTP_X_REQUEST_ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get(self.header, "")
        # Accept a client-supplied ID only if it looks sane; otherwise generate one.
        rid = incoming if 8 <= len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex
        token = request_id_var.set(rid)
        request.request_id = rid
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = rid
        return response
