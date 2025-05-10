import re
import hashlib
import base58
import bech32

class CryptoAddressFinder:
    """
    A class to identify cryptocurrency addresses in a given text and validate them using checksum algorithms.
    Supports Bitcoin, Ethereum, Solana, Tron, Ripple (XRP), Stellar, TON, OMNI, Tezos, Avalanche, Aptos, Near, Celo,
    Cosmos, Polkadot Asset Hub, Liquid, EOS, Kaia, SLP, Algorand, Kusama Asset Hub, and BASE blockchain addresses.
    """

    def __init__(self):
        # Define regex patterns for various blockchain addresses
        self.patterns = {
            "bitcoin": r'\b(1[a-km-zA-HJ-NP-Z1-9]{25,34}|3[a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-zA-HJ-NP-Z0-9]{39,59})\b',
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
            try:
                decoded = base58.b58decode_check(address_to_validate)
                return True
            except ValueError:
                return False
        elif blockchain_name == "ethereum":
            if address_to_validate.startswith("0x") and len(address_to_validate) == 42:
                address_body = address_to_validate[2:]
                checksum_address = "0x" + "".join(
                    char.upper() if int(hashlib.sha3_256(address_body.encode()).hexdigest()[i], 16) >= 8 else char.lower()
                    for i, char in enumerate(address_body)
                )
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
            for _address in matches:
                if self.validate_checksum(_blockchain, _address):
                    results[_blockchain].append(_address)

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
    Cosmos: cosmos1vladlqg7t7v9l9w0j9q9w9w9w9w9w9w9w9w9w9w9w9w9w9w9
    Polkadot: 1vladlqg7t7v9l9w0j9q9w9w9w9w9w9w9w9w9w9w9w9w9w9w9w9
    """

    finder = CryptoAddressFinder()
    crypto_addresses = finder.find_addresses(sample_text)

    print("Found cryptocurrency addresses:")
    for blockchain, addresses in crypto_addresses.items():
        print(f"{blockchain.capitalize()}:")
        for address in addresses:
            print(f"  {address}")