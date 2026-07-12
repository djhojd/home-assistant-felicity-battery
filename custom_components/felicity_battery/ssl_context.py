"""SSL context for the FSolar API.

The server at ``shine-api.felicitysolar.com`` serves only its leaf certificate,
omitting the "Xcc Trust OV SSL CA" intermediate. That intermediate is issued by
"Certum Trusted Network CA", which IS in Python's default CA bundle. We bundle
the missing intermediate so verification succeeds on hosts (e.g. a Linux HA
instance) whose trust store doesn't already have it — without trusting any new
root and without disabling verification.
"""

from __future__ import annotations

import ssl
from functools import lru_cache
from pathlib import Path

_INTERMEDIATE_PEM = Path(__file__).parent / "xcc_trust_intermediate.pem"


@lru_cache(maxsize=1)
def get_ssl_context() -> ssl.SSLContext:
    """Return an SSLContext with the bundled Xcc Trust intermediate loaded.

    Loads a certificate file from disk, so call it in an executor — not on the
    event loop.
    """
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=str(_INTERMEDIATE_PEM))
    return ctx
