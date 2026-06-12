from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from rest_framework.pagination import PageNumberPagination


DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


class StandardResultsPagination(PageNumberPagination):
    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE


def get_positive_int(value, default, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if parsed < 1:
        return default
    if maximum is not None:
        return min(parsed, maximum)
    return parsed


def paginate_queryset(queryset, request, default_page_size=DEFAULT_PAGE_SIZE, max_page_size=MAX_PAGE_SIZE):
    page_size = get_positive_int(
        request.query_params.get("page_size"),
        default_page_size,
        max_page_size,
    )
    requested_page = get_positive_int(request.query_params.get("page"), 1)

    paginator = Paginator(queryset, page_size)
    total_pages = max(paginator.num_pages, 1)
    page_number = min(requested_page, total_pages)

    try:
        page = paginator.page(page_number)
    except (EmptyPage, PageNotAnInteger):
        page = paginator.page(1)

    metadata = {
        "count": paginator.count,
        "current_page": page.number,
        "total_pages": total_pages,
        "page_size": page_size,
        "has_next": page.has_next(),
        "has_previous": page.has_previous(),
    }
    return page.object_list, metadata
