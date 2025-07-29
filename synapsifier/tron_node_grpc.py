#!/usr/bin/env python3
import grpc
import sys
import time
import os

# Import the generated Tron proto modules
# You must generate these from Tron’s proto files using protoc
import wallet_pb2
import wallet_pb2_grpc
import Tron_pb2
from core import Discover_pb2

def clear_line():
    # ANSI escape code to clear the line
    print('\r\033[K', end='')

def get_node_info(stub):
    return stub.GetNodeInfo(wallet_pb2.EmptyMessage())

def get_now_block(stub):
    return stub.GetNowBlock(wallet_pb2.EmptyMessage())

def main():
    try:
        channel = grpc.insecure_channel('127.0.0.1:50051')
        stub = wallet_pb2_grpc.WalletStub(channel)

        print("Checking Tron node sync status (gRPC)... Press Ctrl+C to exit.")

        while True:
            try:
                node_info = get_node_info(stub)
                now_block = get_now_block(stub)

                block_number = now_block.block_header.raw_data.number
                peers = node_info.activeConnectCount
                # Improved sync status logic: compare block heights
                sync = "Synced" if node_info.syncing == False else "Syncing"
                version = node_info.version
                block_time = now_block.block_header.raw_data.timestamp
                # Format block time to human-readable
                from datetime import datetime
                block_time_str = datetime.utcfromtimestamp(block_time / 1000).strftime('%Y-%m-%d %H:%M:%S UTC')

                # Overwrite output in place
                clear_line()
                print(
                    f"Block: {block_number} | Peers: {peers} | Version: {version} | Status: {sync} | Block Time: {block_time_str}",
                    end=''
                )
                sys.stdout.flush()
                time.sleep(5)
            except grpc.RpcError as e:
                clear_line()
                print(f"gRPC error: {e}", end='')
                sys.stdout.flush()
                time.sleep(5)
            except Exception as e:
                clear_line()
                print(f"Error: {e}", end='')
                sys.stdout.flush()
                time.sleep(5)
    except KeyboardInterrupt:
        print("\nExiting.")

if __name__ == "__main__":
    main()