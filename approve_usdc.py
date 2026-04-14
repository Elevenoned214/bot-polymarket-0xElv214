from web3 import Web3
from dotenv import load_dotenv
import os

load_dotenv()

w3 = Web3(Web3.HTTPProvider('https://polygon.publicnode.com'))

PRIVATE_KEY = os.getenv('PRIVATE_KEY')
FUNDER      = Web3.to_checksum_address(os.getenv('FUNDER_ADDRESS'))
USDC        = Web3.to_checksum_address('0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174')

# Kontrak yang perlu di-approve
CONTRACTS = [
    ('CTF Exchange',          '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E'),
    ('Neg Risk CTF Exchange', '0xC5d563A36AE78145C45a50134d48A1215220f80a'),
    ('Neg Risk Adapter',      '0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296'),
]

USDC_ABI = [
    {"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
]

usdc = w3.eth.contract(address=USDC, abi=USDC_ABI)
MAX_AMOUNT = 2**256 - 1

balance = usdc.functions.balanceOf(FUNDER).call()
print(f'USDC balance: ${balance / 1e6:.2f}')

for name, addr in CONTRACTS:
    addr = Web3.to_checksum_address(addr)
    print(f'\nApproving {name}...')
    try:
        tx = usdc.functions.approve(addr, MAX_AMOUNT).build_transaction({
            'from':     FUNDER,
            'nonce':    w3.eth.get_transaction_count(FUNDER),
            'gas':      100000,
            'gasPrice': w3.eth.gas_price,
        })
        signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt.status == 1:
            print(f'  ✅ OK | tx: {tx_hash.hex()}')
        else:
            print(f'  ❌ Gagal | tx: {tx_hash.hex()}')
    except Exception as e:
        print(f'  ❌ Error: {e}')

print('\nDone! Coba jalanin cek_balance.py lagi.')
