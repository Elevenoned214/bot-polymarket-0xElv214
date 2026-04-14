from dotenv import load_dotenv
import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

load_dotenv()
client = ClobClient(
    'https://clob.polymarket.com',
    key=os.getenv('PRIVATE_KEY'),
    chain_id=137,
    signature_type=2,
    funder=os.getenv('FUNDER_ADDRESS')
)
client.set_api_creds(client.create_or_derive_api_creds())
params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
resp = client.get_balance_allowance(params)
print(resp)
print(type(resp))
