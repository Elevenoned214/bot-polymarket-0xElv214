from dotenv import load_dotenv
import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
from py_clob_client.constants import POLYGON

load_dotenv()

# Coba tanpa funder dulu
client = ClobClient(
    host="https://clob.polymarket.com",
    key=os.getenv('PRIVATE_KEY'),
    chain_id=POLYGON,
)
client.set_api_creds(client.create_or_derive_api_creds())

print("=== Tanpa FUNDER_ADDRESS ===")
resp = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
print(resp)

print("\n=== Dengan FUNDER_ADDRESS ===")
client2 = ClobClient(
    host="https://clob.polymarket.com",
    key=os.getenv('PRIVATE_KEY'),
    chain_id=POLYGON,
    funder=os.getenv('FUNDER_ADDRESS'),
)
client2.set_api_creds(client2.create_or_derive_api_creds())
resp2 = client2.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
print(resp2)
