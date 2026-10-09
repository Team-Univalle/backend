"""Inyección de fallos SOLO en qa_settings, sin modificar endpoints productivos."""
import time
from django.conf import settings
from django.http import JsonResponse


class QAFailureMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ('PATCH', 'PUT'):
            flag = settings.BASE_DIR / 'qa-fail-next.flag'
            if flag.exists():
                flag.unlink()
                return JsonResponse({'error': 'Fallo QA controlado. No se guardó nada.'}, status=503)
        delay = settings.BASE_DIR / 'qa-delay.flag'
        if delay.exists() and request.path in ('/conflicts', '/daily-limit'):
            time.sleep(2)
        return self.get_response(request)
