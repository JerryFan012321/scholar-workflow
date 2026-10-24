"""IP-pinned HTTPS acquisition retaining original-host TLS and proxy routing."""
from __future__ import annotations

import ipaddress
import queue
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit
from urllib.request import getproxies

import httpx

DNS_SECONDS = 10


class NetworkSafetyError(Exception):
    """A fixed diagnostic code, never resolver, proxy or certificate details."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class OriginTLSContext(ssl.SSLContext):
    """Restore original SNI/certificate hostname after connecting to a pinned IP.

    HTTP CONNECT's TLS upgrade does not consume HTTPX's sni_hostname extension.
    A per-origin context therefore maps exactly the validated connection IP in
    both socket and TLS-in-TLS BIO paths. The HTTPS proxy has a separate context.
    """

    def __new__(cls, hostname: str, address: str):
        return super().__new__(cls, ssl.PROTOCOL_TLS_CLIENT)

    def __init__(self, hostname: str, address: str):
        self.origin_hostname = hostname
        self.pinned_address = address
        self.minimum_version = ssl.TLSVersion.TLSv1_2
        self.load_default_certs()
        self.check_hostname = True
        self.verify_mode = ssl.CERT_REQUIRED

    def _origin_name(self, server_hostname: str | None) -> str:
        if server_hostname != self.pinned_address:
            raise NetworkSafetyError("unsafe_url")
        return self.origin_hostname

    def wrap_socket(self, sock, server_side=False, do_handshake_on_connect=True,
                    suppress_ragged_eofs=True, server_hostname=None, session=None):
        return super().wrap_socket(
            sock, server_side=server_side, do_handshake_on_connect=do_handshake_on_connect,
            suppress_ragged_eofs=suppress_ragged_eofs,
            server_hostname=self._origin_name(server_hostname), session=session,
        )

    def wrap_bio(self, incoming, outgoing, server_side=False, server_hostname=None, session=None):
        return super().wrap_bio(
            incoming, outgoing, server_side=server_side,
            server_hostname=self._origin_name(server_hostname), session=session,
        )


def is_synthetic_client(client: httpx.Client) -> bool:
    """Only an entirely MockTransport-backed injected client may bypass DNS.

    HTTPX has no public client transport accessor; fail closed on an unfamiliar
    client shape rather than allowing mounted real transports to bypass pinning.
    """
    return (isinstance(getattr(client, "_transport", None), httpx.MockTransport)
            and isinstance(getattr(client, "_mounts", None), dict)
            and all(transport is None or isinstance(transport, httpx.MockTransport)
                    for transport in client._mounts.values()))


def _resolve_global(host: str, port: int, timeout: float) -> str:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        results: queue.Queue = queue.Queue(maxsize=1)

        def resolve() -> None:
            try:
                records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM,
                                             proto=socket.IPPROTO_TCP)
            except Exception:  # noqa: BLE001 - Resolver errors must not escape this boundary.
                results.put(None)
            else:
                results.put(records)

        # A stalled OS resolver cannot hold process exit or the channel deadline.
        threading.Thread(target=resolve, daemon=True, name="research-public-dns").start()
        try:
            records = results.get(timeout=max(0.001, min(DNS_SECONDS, timeout)))
        except queue.Empty:
            raise NetworkSafetyError("network_error") from None
        if not records:
            raise NetworkSafetyError("network_error")
        try:
            addresses = [ipaddress.ip_address(record[4][0]) for record in records]
        except (ValueError, IndexError, TypeError):
            raise NetworkSafetyError("unsafe_url") from None
    else:
        addresses = [literal]
    # Mixed public/private answers are refused, not merely filtered.
    if not addresses or any(
        not address.is_global or address.is_multicast or address.is_reserved
        or getattr(address, "is_site_local", False) for address in addresses
    ):
        raise NetworkSafetyError("unsafe_url")
    return str(addresses[0])


def _bypass_proxy(host: str, port: int, no_proxy: str) -> bool:
    for raw_entry in no_proxy.split(","):
        entry = raw_entry.strip().lower()
        if entry == "*":
            return True
        if not entry:
            continue
        if "://" in entry:
            parts = urlsplit(entry)
            if parts.scheme not in {"https", "all"}:
                continue
            entry = parts.netloc
        try:
            network = ipaddress.ip_network(entry, strict=False)
            if ipaddress.ip_address(host) in network:
                return True
            continue
        except ValueError:
            pass
        if entry.startswith("["):
            parsed = urlsplit("https://" + entry)
            domain, entry_port = parsed.hostname or "", parsed.port
        elif entry.count(":") == 1:
            domain, raw_port = entry.rsplit(":", 1)
            if not raw_port.isdigit():
                continue
            entry_port = int(raw_port)
        else:
            domain, entry_port = entry, None
        if entry_port is not None and entry_port != port:
            continue
        if domain.startswith("*."):
            domain = domain[1:]
        if (domain.startswith(".") and host.endswith(domain)
                or host == domain or host.endswith("." + domain)):
            return True
    return False


def _proxy_for(host: str, port: int) -> httpx.Proxy | None:
    proxies = getproxies()
    if _bypass_proxy(host, port, proxies.get("no", "")):
        return None
    value = proxies.get("https") or proxies.get("all")
    if not value:
        return None
    if "://" not in value:
        value = "http://" + value
    parts = urlsplit(value)
    # SOCKS needs a dependency not shipped here; never silently bypass a proxy.
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise NetworkSafetyError("unsupported_proxy")
    context = ssl.create_default_context() if parts.scheme == "https" else None
    return httpx.Proxy(value, ssl_context=context)


def send_pinned(request: httpx.Request, *, timeout: float) -> tuple[httpx.Response, httpx.Client]:
    """Send a fresh request whose TCP/CONNECT target cannot be rebound by DNS.

    The caller closes both returned objects after reading. Proxy endpoints are
    operator-trusted routing configuration; origin addresses still must be global.
    No source cookies, authentication or credentials are obtained here.
    """
    deadline = time.monotonic() + timeout
    host = request.url.host
    port = request.url.port or 443
    address = _resolve_global(host, port, timeout)
    proxy = _proxy_for(host, port)
    context = OriginTLSContext(host, address)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise NetworkSafetyError("limit_exceeded")
    transport = httpx.HTTPTransport(verify=context, proxy=proxy, trust_env=True, retries=0)
    client = httpx.Client(transport=transport, trust_env=False, follow_redirects=False)
    headers = request.headers.copy()
    headers["Host"] = request.url.netloc.decode("ascii")
    extensions = dict(request.extensions)
    extensions["timeout"] = {key: remaining for key in ("connect", "read", "write", "pool")}
    pinned = httpx.Request(request.method, request.url.copy_with(host=address),
                           headers=headers, stream=request.stream, extensions=extensions)
    try:
        response = client.send(pinned, stream=True, auth=None, follow_redirects=False)
    except BaseException:
        client.close()
        raise
    return response, client
