"""
ProShop tool library API client.

Handles OAuth authentication and GraphQL queries/mutations for:
- Reading tool records
- Creating tool records from manufacturer specs
- Updating tool records (specs, approved brands, notes)
- Querying vendor purchase orders for pricing
"""

import os
import time
import threading
import requests


PROSHOP_BASE_URL = "https://traxismfg.adionsystems.com"
GRAPHQL_URL = f"{PROSHOP_BASE_URL}/api/graphql"
TOKEN_URL = f"{PROSHOP_BASE_URL}/home/member/oauth/accesstoken"

# Tool fields scope (BA16 client) — purchaseorders:r confirmed working at runtime
TOOLS_SCOPE = "parts:rwdp+workorders:rwdp+users:r+tools:rwdp+toolpots:r+purchaseorders:r"

# Accounting client for VPO queries needing contacts:r (supplier names)
ACCOUNTING_SCOPE = "invoices:rwdp+bills:rwdp+estimates:rwdp+quotes:rwdp+customerpos:rwdp+packingslips:rwdp+purchaseorders:rwdp+contacts:r+parts:r"

# .traxis.env search paths
ENV_PATHS = [
    os.path.join(os.path.expanduser("~"), ".traxis.env"),
    os.path.join(os.path.expanduser("~"), "Dropbox", "MACHINE COMM Traxis", "Keys", ".traxis.env"),
    os.path.join(os.path.dirname(__file__), "..", "1. Proshop Automations", ".traxis.env"),
]

# Fields to query on a tool record
TOOL_QUERY_FIELDS = """
    toolNumber description toolGroupLetter
    cutDiameter numberOfFlutes overallLength lengthOfCut
    shankDiameter helixAngle coating toolMaterial tipAngle
    throughCoolant fluteType size ansiCatalogNumber isoCatalogNumber
    purchasingNotes status quantity location
    insertInscribedCircle insertShape insertThickness
    numberOfCuttingCorners pitch fullProfile cornerRadius
    approvedBrands(pageSize: 10) {
        records { approvedBrand vendorToolId cost leadTime }
    }
"""


def _load_env():
    """Load credentials from .traxis.env file."""
    for path in ENV_PATHS:
        if os.path.exists(path):
            env = {}
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
            return env
    raise FileNotFoundError(
        f".traxis.env not found in any of: {ENV_PATHS}"
    )


class GraphQLError(Exception):
    def __init__(self, errors):
        self.errors = errors
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__("; ".join(messages))


class ProShopClient:
    """Lightweight ProShop GraphQL client with OAuth token management."""

    def __init__(self, client_id, client_secret, scope):
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self._token = None
        self._token_obtained_at = 0
        self._token_expires_in = 86400
        self._lock = threading.Lock()

    def _ensure_token(self):
        now = time.time()
        if self._token and now < (self._token_obtained_at + self._token_expires_in - 300):
            return
        with self._lock:
            now = time.time()
            if self._token and now < (self._token_obtained_at + self._token_expires_in - 300):
                return
            self._refresh_token()

    def _refresh_token(self):
        resp = requests.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"OAuth token request failed: {data}")
        self._token = data["access_token"]
        self._token_obtained_at = time.time()
        self._token_expires_in = data.get("expires_in", 86400)

    def execute(self, query, variables=None):
        self._ensure_token()
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = requests.post(
            GRAPHQL_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if resp.status_code == 401:
            self._refresh_token()
            resp = requests.post(
                GRAPHQL_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        resp.raise_for_status()
        body = resp.json()
        if "errors" in body and not body.get("data"):
            raise GraphQLError(body["errors"])
        return body


def get_anthropic_key():
    """Load ANTHROPIC_API_KEY from .traxis.env."""
    env = _load_env()
    key = env.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not found in .traxis.env")
    return key


def get_clients():
    """Create tool client and VPO client from .traxis.env credentials.

    Returns (tools_client, vpo_client). The VPO client may be the same
    as tools_client if contacts:r scope isn't needed, or a separate
    accounting client if supplier names are required.
    """
    env = _load_env()

    tools_client = ProShopClient(
        client_id=env["PROSHOP_CLIENT_ID"],
        client_secret=env["PROSHOP_CLIENT_SECRET"],
        scope=TOOLS_SCOPE,
    )

    # VPO queries use the same client (tools scope includes purchaseorders:r)
    # but supplier names need contacts:r which BA16 doesn't have.
    # Use accounting client for that.
    vpo_client = tools_client
    if env.get("ACCOUNTING_CLIENT_ID"):
        vpo_client = ProShopClient(
            client_id=env["ACCOUNTING_CLIENT_ID"],
            client_secret=env["ACCOUNTING_CLIENT_SECRET"],
            scope=ACCOUNTING_SCOPE,
        )

    return tools_client, vpo_client


def get_tool(client, tool_number):
    """Fetch a single tool record with all relevant fields."""
    result = client.execute(f"""
        {{
            tools(filter: {{ toolNumber: ["{tool_number}"] }}) {{
                records {{ {TOOL_QUERY_FIELDS} }}
            }}
        }}
    """)
    records = result.get("data", {}).get("tools", {}).get("records", [])
    return records[0] if records else None


def get_tools(client, tool_numbers):
    """Fetch multiple tool records."""
    tn_list = ", ".join(f'"{tn}"' for tn in tool_numbers)
    result = client.execute(f"""
        {{
            tools(filter: {{ toolNumber: [{tn_list}] }}) {{
                records {{ {TOOL_QUERY_FIELDS} }}
            }}
        }}
    """)
    return result.get("data", {}).get("tools", {}).get("records", [])


def find_tool_vpo_prices(client, tool_numbers, year="2026"):
    """Search Tool-type VPOs for pricing on specified tools.

    Uses the tools_client (needs purchaseorders:r + tools:r for toolNumberPlainText).
    Supplier names require contacts:r — omitted if scope doesn't cover it.

    Returns dict: {tool_number: {po_id, description, cost_per, quantity, date}}
    """
    # Try with supplier name first, fall back without
    try:
        return _query_vpo_prices(client, tool_numbers, year, include_supplier=True)
    except GraphQLError as e:
        if "contacts module" in str(e):
            return _query_vpo_prices(client, tool_numbers, year, include_supplier=False)
        raise


def _query_vpo_prices(client, tool_numbers, year, include_supplier=True):
    supplier_field = "supplierPlainText" if include_supplier else ""
    query = f"""
        {{
            purchaseOrders(
                filter: {{ year: ["{year}"], poType: ["Tool"] }}
                pageSize: 200
            ) {{
                records {{
                    id date orderStatus {supplier_field}
                    poItems(pageSize: 30) {{
                        records {{
                            toolNumberPlainText
                            description
                            costPer
                            quantity
                            total
                        }}
                    }}
                }}
            }}
        }}
    """
    result = client.execute(query)
    pos = result.get("data", {}).get("purchaseOrders", {}).get("records", [])

    target_set = {tn.upper() for tn in tool_numbers}
    found = {}

    for po in pos:
        for item in po.get("poItems", {}).get("records", []):
            tn = (item.get("toolNumberPlainText") or "").strip().upper()
            if tn in target_set:
                found[tn] = {
                    "po_id": po.get("id"),
                    "date": po.get("date"),
                    "supplier": po.get("supplierPlainText", ""),
                    "description": item.get("description"),
                    "cost_per": item.get("costPer"),
                    "quantity": item.get("quantity"),
                    "total": item.get("total"),
                }
    return found


def add_tool(client, data):
    """Create a new tool record via the addTool mutation.

    data: dict matching AddToolInput fields. Must include toolGroupLetter.
    ProShop auto-assigns the tool number within that group.

    Returns the created tool record with assigned toolNumber.
    """
    result = client.execute(
        """
        mutation AddTool($data: AddToolInput!) {
            addTool(data: $data) {
                %s
            }
        }
        """ % TOOL_QUERY_FIELDS,
        {"data": data},
    )
    return result.get("data", {}).get("addTool")


def update_tool(client, tool_number, data):
    """Update a tool record via the updateTool mutation.

    data: dict matching UpdateToolInput fields. Can include nested
    approvedBrands updates with selector/data pattern.

    Returns the updated tool record.
    """
    result = client.execute(
        """
        mutation UpdateTool($toolNumber: String!, $data: UpdateToolInput!) {
            updateTool(toolNumber: $toolNumber, data: $data) {
                toolNumber description overallLength lengthOfCut
                shankDiameter helixAngle coating ansiCatalogNumber
                purchasingNotes
                approvedBrands(pageSize: 10) {
                    records { approvedBrand vendorToolId cost }
                }
            }
        }
        """,
        {"toolNumber": tool_number, "data": data},
    )
    return result.get("data", {}).get("updateTool")
