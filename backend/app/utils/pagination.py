from flask import request

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def parse_pagination(default_size=DEFAULT_PAGE_SIZE, max_size=MAX_PAGE_SIZE):
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", default_size, type=int)

    if page is None or page < 1:
        page = 1
    if size is None or size < 1:
        size = default_size

    return page, min(size, max_size)
