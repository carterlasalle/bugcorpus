async def handle(request):
    try:
        current = get_snapshot()
        await fetch_remote(request)
    except TimeoutError:
        current = get_snapshot()
        raise
    current = get_snapshot()
    return render(current)
