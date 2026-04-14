from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

RPCS = [
    'https://polygon-rpc.com',
    'https://rpc-mainnet.matic.quiknode.pro',
    'https://rpc-mainnet.maticvigil.com',
    'https://matic-mainnet.chainstacklabs.com',
]

w3 = None
for rpc in RPCS:
    try:
        _w3 = Web3(Web3.HTTPProvider(rpc))
        if _w3.is_connected():
            _w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            w3 = _w3
            print(f'Pakai RPC: {rpc}')
            break
    except:
        continue

if w3 is None:
    print('❌ Semua RPC gagal')
    exit(1)

PRIVATE_KEY = os.getenv('PRIVATE_KEY')
FROM        = Web3.to_checksum_address(w3.eth.account.from_key(PRIVATE_KEY).address)
TO          = Web3.to_checksum_address(os.getenv('FUNDER_ADDRESS'))
AMOUNT      = w3.to_wei(0.5, 'ether')

print(f'Kirim 0.5 MATIC dari {FROM} ke {TO}')

base_fee = w3.eth.get_block('latest')['baseFeePerGas']
tx = {
    'to':                   TO,
    'value':                AMOUNT,
    'gas':                  21000,
    'maxFeePerGas':         base_fee * 2,
    'maxPriorityFeePerGas': w3.to_wei(30, 'gwei'),
    'nonce':                w3.eth.get_transaction_count(FROM),
    'chainId':              137,
    'type':                 2,
}

signed  = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

if receipt.status == 1:
    print(f'✅ Berhasil! tx: {tx_hash.hex()}')
else:
    print(f'❌ Gagal! tx: {tx_hash.hex()}')
