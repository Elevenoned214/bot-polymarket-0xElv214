from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

w3 = Web3(Web3.HTTPProvider('https://rpc-mainnet.matic.quiknode.pro'))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

# Polymarket Proxy Wallet Factory
FACTORY = Web3.to_checksum_address('0xaB45c5A4B0c941a2F231C6f3baC8F077185625c4')
FACTORY_ABI = [{
    "inputs": [{"name": "owner", "type": "address"}],
    "name": "getAddress",
    "outputs": [{"name": "", "type": "address"}],
    "stateMutability": "view",
    "type": "function"
}]

factory = w3.eth.contract(address=FACTORY, abi=FACTORY_ABI)
metamask = Web3.to_checksum_address('0x817D962F68C0405f6028f2f450fE2491d6E64cD7')

proxy = factory.functions.getAddress(metamask).call()
print(f'MetaMask address : {metamask}')
print(f'Proxy wallet     : {proxy}')
