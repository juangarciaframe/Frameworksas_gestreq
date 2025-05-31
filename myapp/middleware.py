from django.shortcuts import redirect, render
from myapp.models import Empresa
import logging
from django.http import HttpResponseServerError, HttpResponseBadRequest
from django.core.exceptions import PermissionDenied, ValidationError  # Import ValidationError


logger = logging.getLogger(__name__)


class CompanyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            if request.user.is_authenticated:
                # logger.debug(f"CompanyMiddleware: User '{request.user.username}' is authenticated.")
                selected_company_id = request.session.get('selected_company_id')
                # logger.debug(f"CompanyMiddleware: Session selected_company_id = '{selected_company_id}' for path '{request.path}'")
                if selected_company_id:
                    try:
                        request.selected_company = Empresa.objects.get(
                            codigoempresa=selected_company_id)
                        # logger.debug(f"CompanyMiddleware: Successfully fetched Empresa '{request.selected_company.nombreempresa}' for user '{request.user.username}' on path '{request.path}'.")
                    except Empresa.DoesNotExist:
                        request.selected_company = None
                        # logger.warning(f"CompanyMiddleware: Empresa with codigoempresa '{selected_company_id}' not found in DB. selected_company set to None for path '{request.path}'.")
                else:
                    request.selected_company = None
                    # logger.debug(f"CompanyMiddleware: No 'selected_company_id' in session. selected_company set to None for path '{request.path}'.")
            else:
                request.selected_company = None
                # logger.debug(f"CompanyMiddleware: User not authenticated. selected_company set to None for path '{request.path}'.")
            response = self.get_response(request)
            return response
        except Exception as e:
            # Mantener este logger.error general es buena idea, pero los específicos de depuración se van.
            logger.error(f"Error in CompanyMiddleware on path '{request.path}': {e}", exc_info=True)
            return self.get_response(request)  # importante retornar la response.


class ErrorHandlingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code >= 400:
            logger.error(f"Error {response.status_code} on {request.path}")
            return self.handle_error_response(request, response)
        return response

    def process_exception(self, request, exception):
        logger.exception(f"Exception on {request.path}")
        if isinstance(exception, PermissionDenied):
            return self.handle_permission_denied(request, exception)
        return self.handle_exception(request, exception)

    def handle_error_response(self, request, response):
        if response.status_code == 400:
            return render(request, 'myapp/mi_pagina_de_error.html',
                          {'error_code': response.status_code, 'message': response.reason_phrase},
                          status=response.status_code)
        elif response.status_code == 404:
            return render(request, 'myapp/mi_pagina_de_error.html', {'error_code': response.status_code},
                          status=response.status_code)
        elif response.status_code == 500:
            # We need to get the exception from the request
            exception = request.exception if hasattr(request, 'exception') else None
            return render(request, 'myapp/mi_pagina_de_error.html', {'error_code': response.status_code, 'exception': exception},
                          status=response.status_code)
        else:
            return render(request, 'myapp/mi_pagina_de_error.html', {'error_code': response.status_code},
                          status=response.status_code)

    def handle_exception(self, request, exception):
        # We need to add the exception to the request
        request.exception = exception
        return render(request, 'myapp/mi_pagina_de_error.html', {'exception': exception, 'error_code': 500},
                      status=500)

    def handle_permission_denied(self, request, exception):
        # We need to add the exception to the request
        request.exception = exception
        return render(request, 'myapp/mi_pagina_de_error.html', {'exception': exception, 'error_code': 403},
                      status=403)
