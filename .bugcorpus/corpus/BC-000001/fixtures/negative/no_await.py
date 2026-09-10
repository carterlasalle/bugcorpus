def handle(request):
    snapshot = get_snapshot()
    return render(snapshot)
