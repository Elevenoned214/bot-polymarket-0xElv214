from dotenv import load_dotenv
import os, time, hmac, hashlib, base64, requests
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

load_dotenv()

client = ClobClient(
    host="https://clob.polymarket.com",
    key=os.getenv('PRIVATE_KEY'),
    chain_id=POLYGON,
    funder=os.getenv('FUNDER_ADDRESS'),
)

print("Membuat API credentials baru...")
creds = client.create_or_derive_api_creds()
client.set_api_creds(creds)

print(f"API Key: {creds.api_key}")
print(f"Address: {client.get_address()}")

# Test auth dengan query balance
print("\nTest balance query...")
resp = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
print("Balance response:", resp)

# Coba juga query profile
print("\nTest get API keys...")
try:
    keys = client.get_api_keys()
    print("API Keys:", keys)
except Exception as e:
    print("Error get_api_keys:", e)
