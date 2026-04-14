from web3 import Web3
from dotenv import load_dotenv
import os

load_dotenv()

w3 = Web3(Web3.HTTPProvider('https://polygon.publicnode.com'))
funder = os.getenv('FUNDER_ADDRESS')
balance = w3.eth.get_balance(Web3.to_checksum_address(funder))
print(f'MATIC di wallet: {w3.from_wei(balance, "ether"):.4f} MATIC')
