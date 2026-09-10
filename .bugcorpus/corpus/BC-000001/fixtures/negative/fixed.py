async def handle(request):
    snapshot = get_snapshot()
    await fetch_remote(request)
    snapshot = get_snapshot()
    return render(snapshot)


def render(snapshot):
    return snapshot.data
