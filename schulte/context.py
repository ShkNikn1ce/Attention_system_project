from pathlib import Path

_CSS = Path(__file__).resolve().parent / "static" / "schulte" / "app.css"


def navigation(request):
    unread = 0
    if request.user.is_authenticated:
        unread = request.user.notifications.filter(is_read=False).count()
    try:
        css_version = int(_CSS.stat().st_mtime)
    except OSError:
        css_version = 1
    return {"unread_notifications": unread, "css_version": css_version}
