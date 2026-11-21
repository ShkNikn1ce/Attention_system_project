def navigation(request):
    unread = 0
    if request.user.is_authenticated:
        unread = request.user.notifications.filter(is_read=False).count()
    return {"unread_notifications": unread}
