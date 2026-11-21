from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def role_required(*roles: str):
    """Пускает только вошедшего пользователя с одной из ролей."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                return render(request, "schulte/forbidden.html", status=403)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
