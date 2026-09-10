async def handle_request(req, store):
    # adversarial positive: renamed identifiers, extra statements, wrapped use
    state_view = store.snapshot()
    log("acquired")
    total = 1 + 2
    await store.refresh(req)
    print("done", total)
    return state_view.payload["rows"]
