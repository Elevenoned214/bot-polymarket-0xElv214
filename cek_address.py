from web3 import Web3
from dotenv import load_dotenv
import os

load_dotenv()
w3 = Web3()
acc = w3.eth.account.from_key(os.getenv('PRIVATE_KEY'))
print('Address dari PK:', acc.address)
print('FUNDER_ADDRESS :', os.getenv('FUNDER_ADDRESS'))
print('Match:', acc.address.lower() == os.getenv('FUNDER_ADDRESS').lower())
