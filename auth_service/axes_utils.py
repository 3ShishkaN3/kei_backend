def get_axes_username(request, credentials):
    username = credentials.get("username")
    if not username:
        username = request.POST.get("username") or request.POST.get("email")
    return username.lower() if username else None
