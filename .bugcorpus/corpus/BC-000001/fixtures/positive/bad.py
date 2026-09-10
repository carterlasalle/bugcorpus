async def handle(request):
    snapshot = get_snapshot()
    await fetch_remote(request)
    return render(snapshot)


def render(snapshot):
    return snapshot.data
