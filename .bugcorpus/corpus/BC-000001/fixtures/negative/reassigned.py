async def handle(request):
    snapshot = get_snapshot()
    await fetch_remote(request)
    snapshot = build_default()
    return render(snapshot)
