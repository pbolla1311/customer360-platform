from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "customer360_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "customer360_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)