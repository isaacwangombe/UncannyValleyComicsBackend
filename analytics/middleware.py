from .models import Visitor

class VisitorTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/admin') and not request.user.is_staff:
            ip = request.META.get('REMOTE_ADDR')
            Visitor.objects.create(ip_address=ip)
        return self.get_response(request)
