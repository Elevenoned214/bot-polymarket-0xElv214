from web3 import Web3
from dotenv import load_dotenv
import os

load_dotenv()

w3 = Web3(Web3.HTTPProvider('https://polygon.publicnode.com'))

FUNDER = os.getenv('FUNDER_ADDRESS')
USDC = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'

abi = [{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]

contract = w3.eth.contract(address=Web3.to_checksum_address(USDC), abi=abi)
balance = contract.functions.balanceOf(Web3.to_checksum_address(FUNDER)).call()

print(f'USDC di wallet Polygon: ${balance / 1e6:.2f}')
