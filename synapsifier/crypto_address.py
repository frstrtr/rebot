import re
# import hashlib
import base58
import bech32
import logging
from Crypto.Hash import keccak  # Add this import at the top

class CryptoAddressFinder:
    """
    A class to identify cryptocurrency addresses in a given text and validate them using checksum algorithms.
    Supports Bitcoin, Ethereum, Solana, Tron, Ripple (XRP), Stellar, TON, OMNI, Tezos, Avalanche, Aptos, Near, Celo,
    Cosmos, Polkadot Asset Hub, Liquid, EOS, Kaia, SLP, Algorand, Kusama Asset Hub, and BASE blockchain addresses.
    """

    def __init__(self):
        # Define regex patterns for various blockchain addresses
        # TODO: bitcoin lower and upper case need to be checked
        self.patterns = {
            "bitcoin": (
                r'\b('
                r'1[a-km-zA-HJ-NP-Z1-9]{25,34}'                  # Legacy
                r'|3[a-km-zA-HJ-NP-Z1-9]{25,34}'                 # P2SH
                r'|bc1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{39,87}' # Bech32/Bech32m (SegWit v0/v1+), 42-90 chars total
                r')\b'
            ),
            "ethereum": r'\b0x[a-fA-F0-9]{40}\b',  # Ethereum-compatible (Ethereum, BSC, Polygon, Avalanche, BASE)
            "solana": r'\b[A-HJ-NP-Za-km-z1-9]{32,44}\b',
            "tron": r'\bT[a-zA-Z0-9]{33}\b',
            "ripple": r'\br[a-zA-Z0-9]{24,34}\b',
            "stellar": r'\bG[A-Z2-7]{55}\b',
            "ton": r'\b(EQ|Ef|kQ)[A-Za-z0-9_-]{46}\b',
            "tezos": r'\btz[1-3][a-zA-Z0-9]{33}\b',
            "cosmos": r'\bcosmos1[a-zA-Z0-9]{38,}\b',
            "polkadot": r'\b1[a-zA-Z0-9]{47}\b',
            "algorand": r'\b[A-Z2-7]{58}\b',
        }

    def validate_checksum(self, blockchain_name, address_to_validate):
        """
        Validate the checksum of a given address for a specific blockchain.

        :param blockchain: The blockchain name.
        :param address: The address to validate.
        :return: True if the checksum is valid, False otherwise.
        """
        if blockchain_name == "bitcoin":
            if address_to_validate.startswith("bc1"):
                try:
                    hrp, data = bech32.bech32_decode(address_to_validate)
                    # hrp should be 'bc' for mainnet, data should not be None and length > 0
                    return hrp == "bc" and data is not None and len(data) > 0
                except Exception:
                    return False
            else:
                try:
                    decoded = base58.b58decode_check(address_to_validate)
                    return True
                except ValueError:
                    return False
        elif blockchain_name == "ethereum":
            if address_to_validate.startswith("0x") and len(address_to_validate) == 42:
                addr = address_to_validate[2:]
                if addr.islower() or addr.isupper():
                    return True
                # Use Keccak-256 for EIP-55 checksum
                k = keccak.new(digest_bits=256)
                k.update(addr.lower().encode())
                keccak_hash = k.hexdigest()
                checksum_address = "0x"
                for i, c in enumerate(addr):
                    if c.isalpha():
                        checksum_address += c.upper() if int(keccak_hash[i], 16) >= 8 else c.lower()
                    else:
                        checksum_address += c
                return checksum_address == address_to_validate
            return False
        elif blockchain_name == "ripple":
            try:
                decoded = base58.b58decode_check(address_to_validate)
                return True
            except ValueError:
                return False
        elif blockchain_name == "stellar":
            try:
                decoded = base58.b58decode(address_to_validate)
                return len(decoded) == 32
            except ValueError:
                return False
        elif blockchain_name == "cosmos":
            try:
                hrp, data = bech32.bech32_decode(address_to_validate)
                return hrp == "cosmos" and data is not None
            except ValueError:
                return False
        elif blockchain_name == "polkadot":
            try:
                decoded = base58.b58decode_check(address_to_validate)
                return len(decoded) == 35
            except ValueError:
                return False
        elif blockchain_name == "algorand":
            try:
                decoded = base58.b58decode(address_to_validate)
                return len(decoded) == 32
            except ValueError:
                return False
        # Add checksum validation for other blockchains here
        return True  # Default to True for blockchains without checksum validation

    def find_addresses(self, text):
        """
        Find all cryptocurrency addresses in the given text and validate their checksums.

        :param text: The input text to search for addresses.
        :return: A dictionary with blockchain names as keys and lists of valid addresses as values.
        """
        results = {blockchain: [] for blockchain in self.patterns.keys()}

        for _blockchain, pattern in self.patterns.items():
            matches = re.findall(pattern, text)
            logging.info("[%s] Regex matches: %s", _blockchain, matches)
            for _address in matches:
                if self.validate_checksum(_blockchain, _address):
                    logging.info("[%s] Address passed checksum: %s", _blockchain, _address)
                    results[_blockchain].append(_address)
                else:
                    logging.warning("[%s] Address failed checksum: %s", _blockchain, _address)

        # Remove empty results
        return {blockchain: addresses for blockchain, addresses in results.items() if addresses}


if __name__ == "__main__":
    # Example usage
    sample_text = """
    Here are some crypto addresses:
    Bitcoin: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
    Ethereum: 0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe
    Ripple: rEb8TK3gBgk5auZkwc6sHnwrGVJH8DuaLh
    Stellar: GCFX4V4X7Z2X6X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X
    Cosmos: cosmos1vladlqg7t7v9l9w0j9q9w9w9w9w9w9w9w9w9w9w9
    Polkadot: 1vladlqg7t7v9l9w0j9q9w9w9w9w9w9w9w9w9w9w9w9
    """

    finder = CryptoAddressFinder()
    crypto_addresses = finder.find_addresses(sample_text)

    print("Found cryptocurrency addresses:")
    for blockchain, addresses in crypto_addresses.items():
        print(f"{blockchain.capitalize()}:")
        for address in addresses:
            print(f"  {address}")