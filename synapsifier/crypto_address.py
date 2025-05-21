import re
import logging
import base64  # Added import

# import hashlib
import base58
import bech32

from utils import segwit_addr
from Crypto.Hash import keccak  # Add this import at the top


# Helper function for CRC16-CCITT (XModem variant)
def crc16_ccitt_xmodem(data: bytes) -> int:
    """
    Calculates CRC16-CCITT (XModem) checksum.
    Polynomial: 0x1021, Initial value: 0x0000.
    """
    crc = 0x0000
    poly = 0x1021
    for byte_val in data:
        crc ^= (byte_val << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
    return crc & 0xFFFF


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
                r"\b("
                r"1[a-km-zA-HJ-NP-Z1-9]{25,34}"  # Legacy
                r"|3[a-km-zA-HJ-NP-Z1-9]{25,34}"  # P2SH
                r"|[bB][cC]1[qpzry9x8gf2tvdw0s3jn54khce6mua7lQPZRY9X8GF2TVDW0S3JN54KHCE6MUA7L]{11,87}"  # Bech32/Bech32m, 14-90 chars total
                r")\b"
            ),
            "ethereum": r"\b0x[a-fA-F0-9]{40}\b",  # Ethereum-compatible (Ethereum, BSC, Polygon, Avalanche, BASE)
            "solana": r"\b[A-HJ-NP-Za-km-z1-9]{32,44}\b",
            "tron": r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b",  # MODIFIED: Stricter Base58 character set
            "ripple": r"\br[a-zA-Z0-9]{24,34}\b",
            "stellar": r"\bG[A-Z2-7]{55}\b",
            "ton": r"\b(?:EQ|UQ|Ef|Uf|kQ|kf)[A-Za-z0-9_-]{46}\b",  # MODIFIED: Made prefix group non-capturing
            "tezos": r"\btz[1-3][a-zA-Z0-9]{33}\b",
            "cosmos": r"\bcosmos1[a-zA-Z0-9]{38,}\b",
            "polkadot": r"\b1[a-zA-Z0-9]{47}\b",
            "algorand": r"\b[A-Z2-7]{58}\b",
        }

    def validate_checksum(self, blockchain_name, address_to_validate):
        """
        Validate the checksum of a given address for a specific blockchain.

        :param blockchain: The blockchain name.
        :param address: The address to validate.
        :return: True if the checksum is valid, False otherwise.
        """
        if blockchain_name == "bitcoin":
            # Convert to lowercase for case-insensitive validation
            addr_lower = address_to_validate.lower()
            if addr_lower.startswith("bc1"):
                hrp = "bc"
                witver, _witprog = segwit_addr.decode(hrp, addr_lower)  # Pass lowercase
                if witver is None:
                    return False
                # witver == 0: Bech32 (SegWit v0), witver == 1: Bech32m (Taproot)
                if addr_lower.startswith("bc1p"):
                    return witver == 1
                elif addr_lower.startswith("bc1q"):
                    return witver == 0
                else:
                    return witver is not None
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
                        checksum_address += (
                            c.upper() if int(keccak_hash[i], 16) >= 8 else c.lower()
                        )
                    else:
                        checksum_address += c
                return checksum_address == address_to_validate
            return False
        elif blockchain_name == "solana":
            try:
                decoded = base58.b58decode(address_to_validate)
                # A Solana public key is 32 bytes long.
                return len(decoded) == 32
            except ValueError:
                # This will catch errors if the address contains invalid Base58 characters
                # or if the address is otherwise malformed for b58decode.
                return False
        elif blockchain_name == "tron":  # ADDED BLOCK FOR TRON
            if not address_to_validate.startswith("T"):  # Basic structural check
                return False
            try:
                # Tron addresses are Base58Check encoded.
                # b58decode_check verifies the checksum and returns the payload.
                # The payload for a mainnet Tron address is 21 bytes:
                # 1 byte for address type (0x41 for 'T') + 20 bytes for the hash.
                decoded_payload = base58.b58decode_check(address_to_validate)
                # Check if the decoded payload is 21 bytes and the first byte matches the Tron prefix.
                return len(decoded_payload) == 21 and decoded_payload[0] == 0x41
            except ValueError:
                # ValueError is raised for invalid Base58 characters or checksum failure.
                return False
        elif blockchain_name == "ton":
            # TON addresses are Base64URL encoded, 48 characters long,
            # and contain an internal CRC16 checksum.
            # The regex r"\b(EQ|UQ|Ef|Uf|kQ|kf)[A-Za-z0-9_-]{46}\b" already ensures length and prefix.
            if len(address_to_validate) != 48:  # Should be guaranteed by regex
                return False
            try:
                # Base64URL decoding requires padding to be a multiple of 4.
                # TON addresses are typically unpadded.
                padded_address = address_to_validate + "=" * (-len(address_to_validate) % 4)
                decoded_bytes = base64.urlsafe_b64decode(padded_address)

                # Decoded TON address should be 36 bytes:
                # 1 byte tag + 1 byte workchain_id + 32 bytes hash + 2 bytes CRC16
                if len(decoded_bytes) != 36:
                    logging.warning(
                        f"TON address {address_to_validate} decoded to unexpected length: {len(decoded_bytes)} bytes (expected 36)"
                    )
                    return False

                data_to_checksum = decoded_bytes[:34]  # Tag, workchain_id, hash
                expected_checksum_bytes = decoded_bytes[34:]  # Last 2 bytes are CRC
                expected_checksum = int.from_bytes(expected_checksum_bytes, "big")

                calculated_checksum = crc16_ccitt_xmodem(data_to_checksum)

                if calculated_checksum == expected_checksum:
                    return True
                else:
                    logging.warning(
                        f"TON address {address_to_validate} CRC16 mismatch. Expected: {expected_checksum:04X}, Calculated: {calculated_checksum:04X}"
                    )
                    return False
            except Exception as e:
                logging.error(f"Error validating TON address {address_to_validate}: {e}")
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
            if matches:  # Only log if matches is not empty
                logging.info("[%s] Regex matches: %s", _blockchain, matches)
                for _address in matches:
                    if self.validate_checksum(_blockchain, _address):
                        logging.info(
                            "[%s] Address passed checksum: %s", _blockchain, _address
                        )
                        results[_blockchain].append(_address)
                    else:
                        logging.warning(
                            "[%s] Address failed checksum: %s", _blockchain, _address
                        )

        # Remove empty results
        return {
            blockchain: addresses
            for blockchain, addresses in results.items()
            if addresses
        }


if __name__ == "__main__":
    # Example usage
    sample_text = """
    Here are some crypto addresses:
    Bitcoin: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
    Ethereum: 0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe
    Ripple: rEb8TK3gBgk5auZkwc6sHnwrGVJH8DuaLh
    Stellar: GCFX4V4X7Z2X6X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X7X
    Cosmos: cosmos1vladlqg7t7v9l9w0j9q9w9w9w9w9
    Polkadot: 1vladlqg7t7v9l9w0j9q9w9w9w9w9
    """

    finder = CryptoAddressFinder()
    crypto_addresses = finder.find_addresses(sample_text)

    print("Found cryptocurrency addresses:")
    for blockchain, addresses in crypto_addresses.items():
        print(f"{blockchain.capitalize()}:")
        for address in addresses:
            print(f"  {address}")
