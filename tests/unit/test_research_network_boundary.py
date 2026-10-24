"""Private/unicast boundary independently pinned at registration and connection."""
import pytest

from scholar_workflow.adapters.research_http import NetworkSafetyError, _resolve_global
from scholar_workflow.adapters.research_sources import _AcquisitionError, _public_url
from scholar_workflow.research import ResearchError
from scholar_workflow.research.models import public_url


@pytest.mark.parametrize("address", ["fec0::1", "ff02::1", "224.0.0.1"])
@pytest.mark.parametrize("boundary", ["registration", "request_url", "connection"])
def test_non_public_unicast_is_rejected_without_dns_or_socket(address, boundary):
    host = f"[{address}]" if ":" in address else address
    url = f"https://{host}/feed.xml"
    if boundary == "registration":
        with pytest.raises(ResearchError):
            public_url(url)
    elif boundary == "request_url":
        with pytest.raises(_AcquisitionError):
            _public_url(url)
    else:
        with pytest.raises(NetworkSafetyError):
            _resolve_global(address, 443, 1)


@pytest.mark.parametrize("address", ["1.1.1.1", "2606:4700:4700::1111"])
def test_public_unicast_literal_remains_valid_without_connecting(address):
    host = f"[{address}]" if ":" in address else address
    assert public_url(f"https://{host}/feed.xml")
    assert _public_url(f"https://{host}/feed.xml")
    assert _resolve_global(address, 443, 1) == address
