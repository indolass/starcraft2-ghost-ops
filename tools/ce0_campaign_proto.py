"""CE-0 evidence name of the accounting prototype. The logic has been promoted into tools/campaign.py (the launcher side of the campaign, CE-1);
this shim keeps the CE-0 tests and tools/ce0_proto_e2e.py working against the same code. Nothing else lives here."""
from campaign import *  # noqa: F401,F403
from campaign import _ROW, _kv  # noqa: F401
