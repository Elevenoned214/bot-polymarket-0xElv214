from dotenv import load_dotenv
import os
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON

load_dotenv()

# Pakai MetaMask private key untuk derive API key Polymarket
client = ClobClient(
    host="https://clob.polymarket.com",
    key=os.getenv('PRIVATE_KEY'),
    chain_id=POLYGON,
)

creds = client.create_or_derive_api_creds()
print("=== API CREDENTIALS POLYMARKET ===")
print(f"API Key    : {creds.api_key}")
print(f"API Secret : {creds.api_secret}")
print(f"API Passphrase: {creds.api_passphrase}")
print(f"Address dari key ini: {client.get_address()}")
