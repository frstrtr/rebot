"""
tron_callbacks.py
Handles TRON-specific callbacks (e.g., for TronScan API interactions).
"""

import logging
from aiogram import html, types
from aiogram.types import (
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest

from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError
from datetime import datetime
from decimal import (
    Decimal,
)  # Not directly used here but good for consistency if amounts were decimal
import asyncio  # Added for periodic typing

from extapi.tronscan.client import TronScanAPI
from .states import AddressProcessingStates  # If TRON AI check sets states
from .helpers import send_typing_periodically  # Added for periodic typing

# Use database to store and toggle watch state
from database.connection import SessionLocal
from database.queries import get_user_watch_state, set_user_watch_state


async def handle_update_report_tronscan_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles the 'Update Report (TRC20)' button click for TronScan."""
    await callback_query.answer("Fetching TRC20 report from TronScan...")
    user_data = await state.get_data()
    address = user_data.get("current_action_address")

    if not address:
        logging.warning(
            f"Could not retrieve address from state for TronScan report. UserID: {callback_query.from_user.id}"
        )
        await callback_query.message.answer(
            "Error: Could not retrieve address for the report. Please try again.",
            show_alert=True,
        )
        return

    api_client = TronScanAPI()
    report_content = f"TRC20 Transaction Report for Address: {address}\n"
    report_content += (
        f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
    )
    fetch_limit = 200

    try:
        await callback_query.message.answer(
            f"Querying TronScan for TRC20 transfers of <code>{address}</code> (limit {fetch_limit})...",
            parse_mode="HTML",
        )

        history_data = await api_client.get_trc20_transaction_history(
            address=address, limit=fetch_limit, start=0
        )

        if history_data and history_data.get("token_transfers"):
            transactions = history_data.get("token_transfers", [])
            total_found_api = history_data.get("total", len(transactions))

            report_content += f"Found {len(transactions)} transactions in this batch (API reports total: {total_found_api}).\n"
            if total_found_api > len(transactions):
                report_content += "Note: More transactions might exist than shown in this batch due to API limits.\n"
            report_content += "--------------------------------------------------\n"

            for tx in transactions:
                raw_timestamp_ms = tx.get("block_ts")
                human_readable_timestamp = "N/A"
                if raw_timestamp_ms is not None:
                    try:
                        timestamp_seconds = float(raw_timestamp_ms) / 1000.0
                        dt_object = datetime.fromtimestamp(timestamp_seconds)
                        human_readable_timestamp = dt_object.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    except (ValueError, TypeError):
                        human_readable_timestamp = "Invalid Timestamp"

                token_info = tx.get("tokenInfo", {})
                token_abbr = token_info.get("tokenAbbr", "N/A")
                token_name = token_info.get("tokenName", "Unknown Token")
                token_decimals = int(token_info.get("tokenDecimal", 0))

                quant_raw = tx.get("quant")
                amount_formatted = "N/A"
                if quant_raw is not None:
                    try:
                        amount_formatted = str(int(quant_raw) / (10**token_decimals))
                    except (ValueError, TypeError):
                        amount_formatted = f"{quant_raw} (raw)"

                report_content += (
                    f"Timestamp: {human_readable_timestamp} (Raw: {raw_timestamp_ms})\n"
                    f"TxID: {tx.get('transaction_id', 'N/A')}\n"
                    f"From: {tx.get('from_address', 'N/A')}\n"
                    f"To: {tx.get('to_address', 'N/A')}\n"
                    f"Token: {token_name} ({token_abbr})\n"
                    f"Amount: {amount_formatted} {token_abbr} (Raw Quant: {quant_raw})\n"
                    f"Confirmed: {tx.get('confirmed', 'N/A')}\n"
                    f"--------------------------------------------------\n"
                )
        elif history_data:
            report_content += (
                "No TRC20 transactions found or response format unexpected.\n"
            )
            report_content += f"API Response: {str(history_data)[:500]}...\n"
        else:
            report_content += (
                "Failed to fetch TRC20 transaction history from TronScan.\n"
            )

        report_file = BufferedInputFile(
            report_content.encode("utf-8"), filename=f"tronscan_report_{address}.txt"
        )
        await callback_query.message.answer_document(report_file)

    except Exception as e:
        logging.error(
            f"Error generating TronScan report for {address}: {e}", exc_info=True
        )
        await callback_query.message.answer(
            f"Sorry, an error occurred while generating the report for {address}."
        )
    finally:
        await api_client.close_session()


async def handle_ai_scam_check_tron_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles the 'AI Scam Check (TRC20)' button click. Gathers data and prompts for language."""
    await callback_query.answer("Performing AI Scam Check for TRC20 transactions...")
    user_data = await state.get_data()
    address = user_data.get("current_action_address")

    if not address:
        logging.warning(
            f"Could not retrieve address from state for AI Scam Check. UserID: {callback_query.from_user.id}"
        )
        await callback_query.message.answer(
            "Error: Could not retrieve address for the AI report. Please try again.",
            show_alert=True,
        )
        return

    try:
        await callback_query.message.edit_text(
            text=f"{callback_query.message.text}\n\n🔄 Gathering comprehensive data for <code>{html.quote(address)}</code>. This may take a moment...",
            parse_mode="HTML",
            reply_markup=None,
        )
    except TelegramAPIError as e:
        logging.warning(
            f"Could not edit message text/markup in handle_ai_scam_check_tron_callback: {e}"
        )
        # If edit fails, send a new message
        await callback_query.message.answer(
            f"🔄 Gathering comprehensive data for <code>{html.quote(address)}</code> for AI analysis. This may take a moment...",
            parse_mode="HTML",
        )

    # --- Start periodic typing ---
    stop_typing_event = asyncio.Event()
    typing_task = asyncio.create_task(
        send_typing_periodically(
            callback_query.bot, callback_query.from_user.id, stop_typing_event
        )
    )
    # --- End periodic typing ---

    tron_api_client = TronScanAPI()
    enriched_data_for_ai = f"Comprehensive AI Scam Analysis Request for TRON Address: {html.quote(address)}\n"
    enriched_data_for_ai += (
        f"Report requested on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
    )
    fetch_limit_trc20_history = 50
    full_blacklist_entries = []

    try:
        try:
            blacklist_response = await tron_api_client.get_stablecoin_blacklist(
                limit=100000
            )
            if blacklist_response and isinstance(blacklist_response.get("data"), list):
                full_blacklist_entries = blacklist_response["data"]
                logging.info(
                    f"Fetched {len(full_blacklist_entries)} entries from stablecoin blacklist for AI check of {address}."
                )
            else:
                logging.warning(
                    f"Could not fetch or parse stablecoin blacklist for AI check of {address}. Response: {blacklist_response}"
                )
        except Exception as e_bl:
            logging.error(
                f"Error fetching stablecoin blacklist for AI for {address}: {e_bl}"
            )
            enriched_data_for_ai += f"Section: Blacklist Status\n--------------------------\nError fetching stablecoin blacklist: {html.quote(str(e_bl))}\n--------------------------\n\n"

        enriched_data_for_ai += await _format_account_info_for_ai(
            address, tron_api_client
        )
        enriched_data_for_ai += await _format_blacklist_status_for_ai(
            address, full_blacklist_entries
        )
        enriched_data_for_ai += await _format_account_tags_for_ai(
            address, tron_api_client
        )
        enriched_data_for_ai += await _format_trc20_balances_for_ai(
            address, tron_api_client, max_to_show=10
        )
        enriched_data_for_ai += await _format_account_transfer_amounts_for_ai(
            address, tron_api_client, max_details_to_show=10
        )
        enriched_data_for_ai += await _format_related_accounts_for_ai(
            address, tron_api_client, full_blacklist_entries, max_to_show=10
        )

        trc20_history_summary = f"Section: Recent TRC20 Transactions (Analysis based on up to {fetch_limit_trc20_history} most recent transactions)\n--------------------------\n"
        history_data = await tron_api_client.get_trc20_transaction_history(
            address=address, limit=fetch_limit_trc20_history, start=0
        )
        if history_data and history_data.get("token_transfers"):
            transactions = history_data.get("token_transfers", [])
            total_found_api = history_data.get(
                "total", len(transactions)
            )  # Total transactions API claims to have for this address/query

            trc20_history_summary += (
                f"Fetched {len(transactions)} TRC20 transactions for analysis.\n"
            )
            trc20_history_summary += f"The API reports a total of {total_found_api} TRC20 transactions for this address.\n"

            if not transactions:
                trc20_history_summary += (
                    "No TRC20 transactions were found in the fetched batch.\n"
                )
            else:
                if len(transactions) < total_found_api:
                    trc20_history_summary += f"Note: The transaction list below is partial, showing the {len(transactions)} most recent ones due to the fetch limit of {fetch_limit_trc20_history}. More older transactions exist.\n"
                elif len(transactions) == total_found_api and total_found_api > 0:
                    trc20_history_summary += "Note: The transaction list below should represent all TRC20 transactions for this address as reported by the API for this query.\n"
                elif total_found_api == 0 and len(transactions) == 0:
                    trc20_history_summary += (
                        "No TRC20 transactions reported by the API for this address.\n"
                    )
                else:  # len(transactions) > 0 and (total_found_api might be less than len(transactions) or 0, which is unusual)
                    trc20_history_summary += f"Displaying {len(transactions)} fetched. API total count is {total_found_api} (interpret with caution if inconsistent).\n"

                for tx_idx, tx in enumerate(transactions):
                    raw_timestamp_ms = tx.get("block_ts")
                    human_readable_timestamp = "N/A"
                    if raw_timestamp_ms is not None:
                        try:
                            human_readable_timestamp = datetime.fromtimestamp(
                                float(raw_timestamp_ms) / 1000.0
                            ).strftime("%Y-%m-%d %H:%M:%S")
                        except (ValueError, TypeError):
                            human_readable_timestamp = "Invalid Timestamp"
                    token_info = tx.get("tokenInfo", {})
                    token_abbr = token_info.get("tokenAbbr", "N/A")
                    token_name = token_info.get("tokenName", "Unknown Token")
                    token_decimals = int(token_info.get("tokenDecimal", 0))
                    quant_raw = tx.get("quant")
                    amount_formatted = "N/A"
                    if quant_raw is not None:
                        try:
                            amount_formatted = str(
                                int(quant_raw) / (10**token_decimals)
                            )
                        except (ValueError, TypeError):
                            amount_formatted = f"{quant_raw} (raw)"
                    trc20_history_summary += (
                        f"Tx {tx_idx + 1}:\n"
                        f"  Time: {human_readable_timestamp}, TxID: {html.quote(tx.get('transaction_id', 'N/A'))}\n"
                        f"  From: {html.quote(tx.get('from_address', 'N/A'))}, To: {html.quote(tx.get('to_address', 'N/A'))}\n"
                        f"  Token: {html.quote(token_name)} ({html.quote(token_abbr)}), Amount: {html.quote(amount_formatted)} {html.quote(token_abbr)}\n"
                        f"  Confirmed: {tx.get('confirmed', 'N/A')}\n---\n"
                    )
        elif history_data:
            trc20_history_summary += "No TRC20 transactions found (API returned data but no 'token_transfers' list) or response format unexpected for history.\n"
        else:
            trc20_history_summary += "Failed to fetch TRC20 transaction history from TronScan. Completeness of transaction data cannot be determined.\n"
        trc20_history_summary += "--------------------------\n\n"
        enriched_data_for_ai += trc20_history_summary

        if (
            "Could not retrieve" in enriched_data_for_ai
            and "Failed to fetch" in enriched_data_for_ai
            and "No TRC20 transactions found" in enriched_data_for_ai
        ):  # Basic check
            await callback_query.message.answer(
                "Could not fetch sufficient transaction data for AI analysis. Please try again later or check the address on an explorer."
            )
            return
        logging.debug(
            f"Gathered AI Scam Check data for {address}:\n{enriched_data_for_ai}..."
        )
        await state.update_data(
            ai_enriched_data=enriched_data_for_ai, current_action_address=address
        )

        language_buttons = [
            [
                InlineKeyboardButton(text="🇬🇧 English", callback_data="ai_lang:en"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="ai_lang:ru"),
            ]
        ]
        reply_markup_lang = InlineKeyboardMarkup(inline_keyboard=language_buttons)

        await callback_query.message.edit_text(
            text=f"Data gathered for <code>{html.quote(address)}</code>.\n📊 Please choose the report language:",
            parse_mode="HTML",
            reply_markup=reply_markup_lang,
        )
        await state.set_state(AddressProcessingStates.awaiting_ai_language_choice)

    except Exception as e:
        logging.error(
            f"Error during AI Scam Check data gathering for {address}: {e}",
            exc_info=True,
        )
        await callback_query.message.answer(
            f"Sorry, an error occurred while gathering data for {html.quote(address)}."
        )
    finally:
        await tron_api_client.close_session()
        # --- Stop periodic typing ---
        stop_typing_event.set()
        try:
            await typing_task
        except asyncio.CancelledError:
            logging.info(
                f"Typing task for chat {callback_query.from_user.id} was cancelled during Tron data gathering."
            )
        except Exception as e_task_await:
            logging.error(
                f"Error awaiting typing task for chat {callback_query.from_user.id} during Tron data gathering: {e_task_await}",
                exc_info=True,
            )
        # --- End stop periodic typing ---


async def handle_watch_new_memo_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles the 'Watch New Memo' button click."""
    user_data = await state.get_data()
    address = user_data.get("current_action_address")

    if not address:
        logging.warning(
            f"Could not retrieve address from state for Watch New Memo. UserID: {callback_query.from_user.id}"
        )
        await callback_query.message.answer(
            "Error: Could not retrieve address for watching memos. Please try again.",
            show_alert=True,
        )
        return

    db = SessionLocal()
    telegram_user_id = callback_query.from_user.id
    blockchain = "tron"  # or derive from context if needed
    # Get current state from DB
    current_state = get_user_watch_state(db, telegram_user_id, address, blockchain)
    # Toggle state
    new_watching = not bool(current_state.get("watch_memos", False))
    set_user_watch_state(
        db, telegram_user_id, address, blockchain, watch_memos=new_watching
    )
    db.close()

    # Sync FSM state for UI consistency
    await state.update_data(watch_memos=new_watching)

    # Edit the source keyboard: update the button text in the original keyboard
    keyboard = callback_query.message.reply_markup
    if keyboard:
        new_keyboard = []
        for row in keyboard.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data == "watch_new_memo":
                    checkbox = "✅" if new_watching else "☐"
                    logging.debug(
                        f"UserID: {telegram_user_id} {'started' if new_watching else 'stopped'} watching new memos on {address}."
                    )
                    new_row.append(
                        InlineKeyboardButton(
                            text=f"👀 Watch Memos {checkbox}",
                            callback_data="watch_new_memo",
                        )
                    )
                else:
                    new_row.append(button)
            new_keyboard.append(new_row)
        reply_markup = InlineKeyboardMarkup(inline_keyboard=new_keyboard)
    else:
        reply_markup = None

    # Only update if markup actually changed
    if reply_markup and keyboard:
        try:
            # Compare the inline_keyboard lists for actual change
            if reply_markup.inline_keyboard != keyboard.inline_keyboard:
                await callback_query.message.edit_reply_markup(
                    reply_markup=reply_markup
                )
            else:
                # No change, answer callback to avoid silent error
                await callback_query.answer()
        except Exception as e:
            if isinstance(e, TelegramBadRequest) and "message is not modified" in str(
                e
            ):
                await callback_query.answer()
            else:
                raise
    # await callback_query.message.edit_text(
    #     f"{'Now watching' if watching else 'Stopped watching'} for new memos on <code>{html.quote(address)}</code>.",
    #     parse_mode="HTML"
    # )


async def handle_watch_blockchain_events_callback(
    callback_query: types.CallbackQuery, state: FSMContext
):
    """Handles the 'Watch Blockchain Events' button click."""
    user_data = await state.get_data()
    address = user_data.get("current_action_address")

    if not address:
        logging.warning(
            f"Could not retrieve address from state for Watch Blockchain Events. UserID: {callback_query.from_user.id}"
        )
        await callback_query.message.answer(
            "Error: Could not retrieve address for watching blockchain events. Please try again.",
            show_alert=True,
        )
        return

    db = SessionLocal()
    telegram_user_id = callback_query.from_user.id
    blockchain = "tron"  # or derive from context if needed
    # Get current state from DB
    current_state = get_user_watch_state(db, telegram_user_id, address, blockchain)
    # Toggle state
    new_watching = not bool(current_state.get("watch_events", False))
    set_user_watch_state(
        db, telegram_user_id, address, blockchain, watch_events=new_watching
    )
    db.close()

    # Optionally sync FSM state for UI consistency
    await state.update_data(watch_events=new_watching)

    # Edit the source keyboard: update the button text in the original keyboard
    keyboard = callback_query.message.reply_markup
    if keyboard:
        new_keyboard = []
        for row in keyboard.inline_keyboard:
            new_row = []
            for button in row:
                if button.callback_data == "watch_blockchain_events":
                    checkbox = "✅" if new_watching else "☐"
                    logging.debug(
                        f"UserID: {telegram_user_id} {'started' if new_watching else 'stopped'} watching blockchain events on {address}."
                    )
                    new_row.append(
                        InlineKeyboardButton(
                            text=f"🔔 Watch TXs {checkbox}",
                            callback_data="watch_blockchain_events",
                        )
                    )
                else:
                    new_row.append(button)
            new_keyboard.append(new_row)
        reply_markup = InlineKeyboardMarkup(inline_keyboard=new_keyboard)
    else:
        reply_markup = None

    # Only update if markup actually changed
    if reply_markup and keyboard:
        try:
            if reply_markup.inline_keyboard != keyboard.inline_keyboard:
                await callback_query.message.edit_reply_markup(
                    reply_markup=reply_markup
                )
            else:
                # No change, answer callback to avoid silent error
                await callback_query.answer()
        except Exception as e:
            if isinstance(e, TelegramBadRequest) and "message is not modified" in str(
                e
            ):
                await callback_query.answer()
            else:
                raise
    # await callback_query.message.edit_text(
    #     f"{'Now watching' if watching else 'Stopped watching'} for blockchain events on <code>{html.quote(address)}</code>.",
    #     parse_mode="HTML"
    # )


async def _format_account_info_for_ai(address: str, api_client: TronScanAPI) -> str:
    """Formats account info for AI processing, including scam-relevant details."""
    info_summary = (
        "Section: Account Overview & Risk Indicators\n--------------------------\n"
    )
    try:
        account_info = await api_client.get_account_info(address)
        if account_info:
            # Basic Info
            trx_balance_sun = account_info.get("balance", 0)
            trx_balance = trx_balance_sun / 1_000_000
            account_name = account_info.get("name", "N/A")

            # Timestamps
            create_time_ms = account_info.get("date_created")
            creation_time_str = "N/A"
            if create_time_ms:
                try:
                    creation_time_str = datetime.fromtimestamp(
                        create_time_ms / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S UTC")
                except Exception:
                    pass

            latest_op_time_ms = account_info.get("latest_operation_time")
            latest_op_time_str = "N/A"
            if latest_op_time_ms:
                try:
                    latest_op_time_str = datetime.fromtimestamp(
                        latest_op_time_ms / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S UTC")
                except Exception:
                    pass

            # Transaction Counts
            total_tx_count = account_info.get("totalTransactionCount", "N/A")
            tx_in_count = account_info.get("transactions_in", "N/A")
            tx_out_count = account_info.get("transactions_out", "N/A")

            # Network Participation & Risk Flags
            total_frozen_sun = account_info.get("totalFrozen", 0)
            total_frozen_trx = total_frozen_sun / 1_000_000
            feedback_risk = account_info.get("feedbackRisk", False)

            tags = []
            for tag_key in ["redTag", "greyTag", "blueTag", "publicTag"]:
                tag_value = account_info.get(tag_key)
                if tag_value:
                    tags.append(
                        f"{tag_key.replace('Tag','').capitalize()}: {tag_value}"
                    )
            tags_str = ", ".join(tags) if tags else "None"

            # Permissions
            owner_permission_str = "N/A"
            owner_permission = account_info.get("ownerPermission", {})
            if owner_permission and isinstance(owner_permission.get("keys"), list):
                owner_addresses = [
                    key.get("address")
                    for key in owner_permission["keys"]
                    if key.get("address")
                ]
                if owner_addresses:
                    owner_permission_str = ", ".join(owner_addresses)

            active_permission_str = "N/A"
            active_permissions = account_info.get("activePermissions", [])
            if active_permissions and isinstance(active_permissions, list):
                active_addresses = set()
                for perm in active_permissions:
                    if isinstance(perm.get("keys"), list):
                        for key in perm["keys"]:
                            if key.get("address"):
                                active_addresses.add(key.get("address"))
                if active_addresses:
                    active_permission_str = ", ".join(list(active_addresses))

            info_summary += (
                f"Address: {html.quote(address)}\n"
                f"Account Name: {html.quote(account_name)}\n"
                f"TRX Balance: {trx_balance:.6f} TRX\n"
                f"Creation Time: {creation_time_str}\n"
                f"Last Activity Time: {latest_op_time_str}\n\n"
                f"--- Transaction Profile ---\n"
                f"Total Transactions: {total_tx_count}\n"
                f"Incoming Transactions: {tx_in_count}\n"
                f"Outgoing Transactions: {tx_out_count}\n\n"
                f"--- Network & Security Profile ---\n"
                f"Total Frozen TRX: {total_frozen_trx:.6f} TRX\n"
                f"Owner Permission Authorized To: {html.quote(owner_permission_str)}\n"
                f"Active Permission(s) Authorized To: {html.quote(active_permission_str)}\n"
                f"TronScan Tags: {html.quote(tags_str)}\n"
                f"Community Risk Feedback: {'Yes' if feedback_risk else 'No'}\n"
            )
        else:
            info_summary += "Could not retrieve basic account information.\n"
    except Exception as e:
        logging.error(f"Error fetching account info for AI for {address}: {e}")
        info_summary += f"Error fetching account info: {html.quote(str(e))}\n"
    info_summary += "--------------------------\n\n"
    return info_summary


async def _format_account_tags_for_ai(address: str, api_client: TronScanAPI) -> str:
    """Formats account tags for AI processing."""
    tags_summary = "Section: Account Tags\n--------------------------\n"
    try:
        tags_data = await api_client.get_account_tags(address)
        found_tags = []
        if tags_data:
            if isinstance(tags_data.get("tags"), list) and tags_data["tags"]:
                for tag_info in tags_data["tags"]:
                    found_tags.append(tag_info.get("tag", "Unknown Tag"))
            elif tags_data.get("tag"):
                found_tags.append(tags_data.get("tag"))
            elif (
                address in tags_data
                and isinstance(tags_data[address], dict)
                and tags_data[address].get("tag")
            ):
                found_tags.append(tags_data[address]["tag"])
        if found_tags:
            tags_summary += f"Tags: {html.quote(', '.join(list(set(found_tags))))}\n"
        else:
            tags_summary += "No specific tags found for this address.\n"
    except Exception as e:
        logging.error(f"Error fetching account tags for AI for {address}: {e}")
        tags_summary += f"Error fetching account tags: {html.quote(str(e))}\n"
    tags_summary += "(Note: Tags can indicate exchange, scammer, whale, etc.)\n--------------------------\n\n"
    return tags_summary


async def _format_trc20_balances_for_ai(
    address: str, api_client: TronScanAPI, max_to_show: int = 50
) -> str:
    """Formats TRC20 token balances for AI processing."""
    balances_summary = f"Section: Top TRC20 Token Balances (Max {max_to_show} shown)\n--------------------------\n"
    try:
        balances_data = await api_client.get_account_trc20_balances(address, limit=50)
        # XXX
        logging.info(
            f"Fetched TRC20 balances for {address}: {str(balances_data)[:500]}"
        )  # Log the fetched data for debugging 500 chars
        if balances_data and isinstance(
            balances_data.get("data"), list
        ):  # Changed 'trc20token_balances' to 'data'
            tokens = balances_data["data"]  # Changed 'trc20token_balances' to 'data'
            if tokens:
                # Filter out the TRX entry if present, as it's often included but not a TRC20 token
                trc20_tokens = [
                    token for token in tokens if token.get("tokenId") != "_"
                ]

                for i, token in enumerate(trc20_tokens[:max_to_show]):
                    token_name = token.get("tokenName", "N/A")
                    token_abbr = token.get("tokenAbbr", "N/A")
                    balance_raw = token.get("balance")  # This is the raw balance string
                    token_decimals = int(token.get("tokenDecimal", 0))
                    balance_formatted = "N/A"

                    # The 'quantity' field seems to be the already decimal-adjusted balance as a float or string
                    # The 'balance' field is the raw integer amount
                    if balance_raw is not None:
                        try:
                            # Use 'quantity' if available and seems more reliable, otherwise parse 'balance'
                            if "quantity" in token:
                                balance_formatted = f"{float(token['quantity']):.6f}"  # Assuming quantity is already adjusted
                            else:
                                balance_formatted = (
                                    f"{int(balance_raw) / (10**token_decimals):.6f}"
                                )
                        except (ValueError, TypeError, KeyError):
                            # Fallback to raw balance if formatting fails
                            try:
                                balance_formatted = (
                                    f"{int(balance_raw) / (10**token_decimals):.6f}"
                                )
                            except (ValueError, TypeError):
                                balance_formatted = f"{balance_raw} (raw)"

                    balances_summary += f"  - {html.quote(token_name)} ({html.quote(token_abbr)}): {html.quote(balance_formatted)}\n"

                if len(trc20_tokens) > max_to_show:
                    balances_summary += f"(Showing top {max_to_show} TRC20 balances out of {len(trc20_tokens)} found in API batch of up to {balances_data.get('total', 50)})\n"
                elif not trc20_tokens:  # If after filtering, no TRC20 tokens remain
                    balances_summary += (
                        "No TRC20 token balances found (excluding TRX if present).\n"
                    )

            else:  # This case means balances_data['data'] was an empty list
                balances_summary += (
                    "No token balances found in the API response data list.\n"
                )
        elif (
            balances_data
            and "total" in balances_data
            and balances_data.get("total") == 0
        ):
            balances_summary += (
                "No TRC20 token balances found (API reports total: 0).\n"
            )
        else:
            balances_summary += "Could not retrieve TRC20 token balances or response format was unexpected.\n"
            if balances_data:
                balances_summary += (
                    f"API Response (first 200 chars): {str(balances_data)[:200]}...\n"
                )
    except Exception as e:
        logging.error(
            f"Error fetching TRC20 balances for AI for {address}: {e}", exc_info=True
        )
        balances_summary += f"Error fetching TRC20 balances: {html.quote(str(e))}\n"
    balances_summary += "--------------------------\n\n"
    return balances_summary


async def _format_account_transfer_amounts_for_ai(
    address: str, api_client: TronScanAPI, max_details_to_show: int = 10
) -> str:
    """Formats account transfer amounts for AI processing."""
    amounts_summary = (
        "Section: Account Fund Flow Summary (USD)\n--------------------------\n"
    )
    try:
        transfer_amounts = await api_client.get_account_transfer_amounts(address)
        if transfer_amounts:
            if transfer_amounts.get("transfer_in"):
                in_data = transfer_amounts["transfer_in"]
                amounts_summary += "Transfer In:\n"
                amounts_summary += f"  Total Records: {in_data.get('total', 'N/A')}\n"
                amounts_summary += (
                    f"  Total USD Amount: {in_data.get('amountTotal', 'N/A')}\n"
                )
                if isinstance(in_data.get("data"), list) and in_data["data"]:
                    amounts_summary += (
                        f"  Top Senders (Max {max_details_to_show} shown):\n"
                    )
                    for item in in_data["data"][:max_details_to_show]:
                        amounts_summary += f"    - Address: {html.quote(item.get('address','N/A'))}, Amount USD: {item.get('amountInUsd','N/A')}, Tag: {html.quote(item.get('addressTag','N/A'))}\n"
            else:
                amounts_summary += "No 'transfer_in' data found.\n"
            amounts_summary += "\n"
            if transfer_amounts.get("transfer_out"):
                out_data = transfer_amounts["transfer_out"]
                amounts_summary += "Transfer Out:\n"
                amounts_summary += f"  Total Records: {out_data.get('total', 'N/A')}\n"
                amounts_summary += (
                    f"  Total USD Amount: {out_data.get('amountTotal', 'N/A')}\n"
                )
                if isinstance(out_data.get("data"), list) and out_data["data"]:
                    amounts_summary += (
                        f"  Top Receivers (Max {max_details_to_show} shown):\n"
                    )
                    for item in out_data["data"][:max_details_to_show]:
                        amounts_summary += f"    - Address: {html.quote(item.get('address','N/A'))}, Amount USD: {item.get('amountInUsd','N/A')}, Tag: {html.quote(item.get('addressTag','N/A'))}\n"
            else:
                amounts_summary += "No 'transfer_out' data found.\n"
        else:
            amounts_summary += "Could not retrieve account fund flow summary.\n"
    except Exception as e:
        logging.error(
            f"Error fetching account transfer amounts for AI for {address}: {e}"
        )
        amounts_summary += (
            f"Error fetching account fund flow summary: {html.quote(str(e))}\n"
        )
    amounts_summary += "--------------------------\n\n"
    return amounts_summary


async def _format_blacklist_status_for_ai(
    address_to_check: str, full_blacklist_entries: list, for_related: bool = False
) -> str:
    """Formats the blacklist status for AI processing."""
    if not full_blacklist_entries:
        if not for_related:
            return f"Section: Blacklist Status for {html.quote(address_to_check)}\n--------------------------\nCould not check blacklist (no data provided).\n--------------------------\n\n"
        return ""
    found_on_blacklist = False
    blacklist_details = ""
    for entry in full_blacklist_entries:
        if entry.get("blackAddress") == address_to_check:
            token_name = entry.get("tokenName", "N/A")
            reason = entry.get("remark", "No specific reason provided")
            entry_time_ms = entry.get("time")
            entry_time_str = "N/A"
            if entry_time_ms:
                try:
                    entry_time_str = datetime.fromtimestamp(
                        entry_time_ms / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S UTC")
                except:
                    pass
            if for_related:
                blacklist_details = f" (<b>WARNING: ON STABLECOIN BLACKLIST</b> - Token: {html.quote(token_name)})"
            else:
                blacklist_details = (
                    f"WARNING: Address is ON the stablecoin blacklist.\n"
                    f"  Token: {html.quote(token_name)}\n"
                    f"  Reason/Remark: {html.quote(reason)}\n"
                    f"  Blacklisted On: {entry_time_str}\n"
                    f"  Transaction Hash (related to blacklisting): {html.quote(entry.get('transHash', 'N/A'))}\n"
                )
            found_on_blacklist = True
            break
    if for_related:
        return blacklist_details
    blacklist_summary = f"Section: Stablecoin Blacklist Status for {html.quote(address_to_check)}\n--------------------------\n"
    if found_on_blacklist:
        blacklist_summary += blacklist_details
    else:
        blacklist_summary += "Address is NOT found on the stablecoin blacklist.\n"
    blacklist_summary += "--------------------------\n\n"
    return blacklist_summary


async def _format_related_accounts_for_ai(
    address: str,
    api_client: TronScanAPI,
    full_blacklist_entries: list,
    max_to_show: int = 10,
) -> str:
    """Formats related accounts for AI processing."""
    related_summary = f"Section: Top Related Accounts (Interacted With - Max {max_to_show} shown)\n--------------------------\n"
    try:
        related_data = await api_client.get_account_related_accounts(address)
        if related_data and isinstance(related_data.get("data"), list):
            accounts = related_data["data"]
            if accounts:
                for acc_data in accounts[:max_to_show]:
                    related_address = acc_data.get("related_address", "N/A")
                    blacklist_note = await _format_blacklist_status_for_ai(
                        related_address, full_blacklist_entries, for_related=True
                    )
                    related_summary += (
                        f"  - Address: {html.quote(related_address)}{blacklist_note}, "
                        f"Tag: {html.quote(acc_data.get('addressTag', 'N/A'))}, "
                        f"In USD: {acc_data.get('inAmountUsd', 'N/A')}, "
                        f"Out USD: {acc_data.get('outAmountUsd', 'N/A')}\n"
                    )
                if len(accounts) > max_to_show:
                    related_summary += f"(Showing top {max_to_show} related accounts out of {len(accounts)} found)\n"
            else:
                related_summary += "No related accounts found.\n"
        else:
            related_summary += "Could not retrieve related accounts information.\n"
    except Exception as e:
        logging.error(f"Error fetching related accounts for AI for {address}: {e}")
        related_summary += f"Error fetching related accounts: {html.quote(str(e))}\n"
    related_summary += "--------------------------\n\n"
    return related_summary
