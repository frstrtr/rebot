# rebot_main.py

"""
AIogram bot main module
"""

import logging
import asyncio
import logging
import sys
import contextvars
import os
import datetime
from logging.handlers import TimedRotatingFileHandler

from aiogram import Bot, Dispatcher, BaseMiddleware, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter  # MODIFIED: Imported Command
from aiogram.types import Update

from config.credentials import Credentials
from config.config import Config  # Config is already imported
from database import create_tables
from database.connection import SessionLocal

from database.queries import (
    get_all_watched_addresses,
    get_address_public_memos,
    get_user_watch_states,
    update_user_watch_state_last_memo_id,
    update_user_watch_state_last_state,
)

# Import User model for DB ID lookups
from database.models import User
from utils.tronscan import get_tron_account_changes

from handlers import (
    command_start_handler,
    handle_message_with_potential_crypto_address,
    handle_story,
    checkmemo_handler,
    handle_blockchain_clarification_callback,
    # handle_memo_action_callback, # Updated
    handle_show_public_memos_callback,  # Updated
    handle_show_private_memos_callback,  # New
    handle_request_memo_callback,  # New
    # handle_proceed_to_memo_stage_callback, # Updated
    handle_skip_address_action_stage_callback,
    handle_update_report_tronscan_callback,
    handle_ai_scam_check_tron_callback,  # New handler import
    handle_ai_language_choice_callback,  # New handler import for AI language choice
    handle_ai_response_memo_action_callback,  # New handler import for AI memo actions
    handle_show_token_transfers_evm_callback,  # ADDED
    handle_ai_scam_check_evm_callback,  # ADDED
    handle_admin_cancel_delete_memo_callback,  # ADDED for admin memo deletion cancellation
    handle_admin_request_delete_memo_callback,  # ADDED for admin memo deletion request
    handle_admin_confirm_delete_memo_callback,  # ADDED for admin memo deletion confirmatio
    # tron specific handlers
    handle_watch_new_memo_callback,  # Reusing the same handler for public memos
    handle_watch_blockchain_events_callback,  # Reusing the same handler for private memos
)
from handlers.states import AddressProcessingStates  # Import the missing states

MAX_MSG_LENGTH = 4096  # Telegram max message length for HTML

# 1. Define Context Variable for user_id
user_id_context = contextvars.ContextVar("user_id_context", default="N/A")


# 2. Custom Logging Filter to add user_id to log records
class UserIdContextFilter(logging.Filter):
    """class UserIdContextFilter(logging.Filter):
    A custom logging filter that adds user_id to log records.
    This filter retrieves the user_id from the context variable and adds it to the log record.
    """

    def filter(self, record):
        record.user_id = user_id_context.get()
        return True


# 3. Custom Logging Formatter for Admin Colors
class AdminColorLogFormatter(logging.Formatter):
    """
    A custom logging formatter that colors the UserID based on admin status.
    Admins (from Config.ADMINS) will have their UserID colored purple.
    Other UserIDs will be colored yellow.
    """

    def format(self, record):
        user_id_str = getattr(
            record, "user_id", "N/A"
        )  # user_id is added by UserIdContextFilter
        is_admin = False

        # Config.ADMINS stores admin IDs as integers
        # record.user_id is a string from contextvars
        if user_id_str.isdigit():
            try:
                user_id_int = int(user_id_str)
                if hasattr(Config, "ADMINS") and isinstance(
                    Config.ADMINS, (list, set, tuple)
                ):
                    if user_id_int in Config.ADMINS:
                        is_admin = True
            except ValueError:
                # This case should ideally not be reached if user_id_str.isdigit() is true
                pass  # Not an admin if conversion fails

        # Determine color based on admin status
        # Ensure Config.PURPLE and Config.YELLOW are defined
        color_code = Config.PURPLE if is_admin else Config.YELLOW
        reset_color_code = Config.RESET_COLOR  # Ensure Config.RESET_COLOR is defined

        # Create a new field on the record for the colored user_id string
        record.colored_user_id = f"{color_code}{user_id_str}{reset_color_code}"

        # Call the parent class's format method to complete the formatting.
        # This will use the format string provided during initialization of the formatter,
        # substituting %(colored_user_id)s with the value we just set.
        return super().format(record)


# 4. Aiogram Middleware to extract and set user_id in context
class UserIdLoggingMiddleware(BaseMiddleware):
    """Middleware to extract user_id from the event and set it in context variable."""

    async def __call__(self, handler, event: Update, data: dict):
        user_id_to_log = "N/A"

        if event.message and event.message.from_user:
            user_id_to_log = event.message.from_user.id
        elif event.edited_message and event.edited_message.from_user:
            user_id_to_log = event.edited_message.from_user.id
        elif event.channel_post and event.channel_post.from_user:
            user_id_to_log = (
                event.channel_post.from_user.id
                if event.channel_post.from_user
                else "Channel"
            )
        elif event.edited_channel_post and event.edited_channel_post.from_user:
            user_id_to_log = (
                event.edited_channel_post.from_user.id
                if event.edited_channel_post.from_user
                else "Channel"
            )
        elif event.inline_query and event.inline_query.from_user:
            user_id_to_log = event.inline_query.from_user.id
        elif event.chosen_inline_result and event.chosen_inline_result.from_user:
            user_id_to_log = event.chosen_inline_result.from_user.id
        elif event.callback_query and event.callback_query.from_user:
            user_id_to_log = event.callback_query.from_user.id
        elif event.shipping_query and event.shipping_query.from_user:
            user_id_to_log = event.shipping_query.from_user.id
        elif event.pre_checkout_query and event.pre_checkout_query.from_user:
            user_id_to_log = event.pre_checkout_query.from_user.id
        elif event.poll_answer and event.poll_answer.user:
            user_id_to_log = event.poll_answer.user.id
        elif event.my_chat_member and event.my_chat_member.from_user:
            user_id_to_log = event.my_chat_member.from_user.id
        elif event.chat_member and event.chat_member.from_user:
            user_id_to_log = event.chat_member.from_user.id
        elif event.chat_join_request and event.chat_join_request.from_user:
            user_id_to_log = event.chat_join_request.from_user.id

        token = user_id_context.set(str(user_id_to_log))
        try:
            return await handler(event, data)
        finally:
            user_id_context.reset(token)


class Rebot:
    """Main bot class"""

    def __init__(self):
        self.credentials = Credentials()
        self.parse_mode = Config.PARSE_MODE
        self.rebot_dp = Dispatcher()
        self.rebot_dp.update.outer_middleware(UserIdLoggingMiddleware())
        self.bot = self.create_bot()
        self.setup_handlers()
        self.init_database()

    def create_bot(self):
        """Function to create the bot"""
        token = self.credentials.get_bot_token()
        if token is None:
            raise ValueError("Bot token must not be None.")
        return Bot(
            token=token,
            default=DefaultBotProperties(
                parse_mode=self.parse_mode,
            ),
        )

    def init_database(self):
        """Initialize the database"""
        try:
            create_tables()
            logging.info("Database initialized successfully")
        except Exception as e:
            logging.error("Failed to initialize database: %s", e)
            raise

    def setup_handlers(self):
        """Function to setup all the handlers for the bot"""
        # Register message handlers
        # Use Command filter to pass CommandObject to command_start_handler
        self.rebot_dp.message.register(
            command_start_handler, Command(commands=["start"])
        )
        self.rebot_dp.message.register(
            checkmemo_handler,
            Command(commands=["checkmemo"]),  # Using Command filter is often cleaner
            # lambda m: m.text and m.text.startswith("/checkmemo"), # Your original lambda is also fine
        )
        self.rebot_dp.message.register(
            handle_message_with_potential_crypto_address,
            F.text | F.caption,  # Handles messages with text or caption in any state
            StateFilter("*"),  # Explicitly allowing any state
        )
        # self.rebot_dp.message.register(handle_story) # This was for F.story, if you still need it
        self.rebot_dp.message.register(
            handle_story, F.story
        )  # Registering for story content

        # Register callback query handlers
        self.rebot_dp.callback_query.register(
            handle_blockchain_clarification_callback,
            F.data.startswith("clarify_bc:"),
        )

        # Register update report handler
        self.rebot_dp.callback_query.register(
            handle_update_report_tronscan_callback,
            F.data.startswith("update_report_tronscan"),
        )

        # self.rebot_dp.callback_query.register(
        #     handle_memo_action_callback, # This was for buttons from _prompt_for_next_memo
        #     F.data.startswith("memo_action:"),
        # )

        self.rebot_dp.callback_query.register(
            handle_show_public_memos_callback,  # Changed from show_prev_memos
            F.data == "show_public_memos",
        )

        self.rebot_dp.callback_query.register(
            handle_show_private_memos_callback,
            F.data == "show_private_memos",
        )

        # self.rebot_dp.callback_query.register(
        #     handle_proceed_to_memo_stage_callback, # Replaced by request_memo:type
        #     F.data == "proceed_to_memo_stage",
        # )

        self.rebot_dp.callback_query.register(
            handle_request_memo_callback,  # Handles request_memo:public and request_memo:private
            F.data.startswith("request_memo:"),
        )

        self.rebot_dp.callback_query.register(
            handle_skip_address_action_stage_callback,
            F.data == "skip_address_action_stage",  # MODIFIED from startswith
        )

        self.rebot_dp.callback_query.register(
            handle_ai_scam_check_tron_callback,  # New handler for AI scam check
            F.data == "ai_scam_check_tron",  # Callback data for the new handler
        )

        self.rebot_dp.callback_query.register(
            handle_ai_language_choice_callback,  # New handler for AI language choice
            AddressProcessingStates.awaiting_ai_language_choice,  # Filter by state
            F.data.startswith("ai_lang:"),
        )

        self.rebot_dp.callback_query.register(
            handle_ai_response_memo_action_callback,  # Handler for AI response memo buttons
            F.data.startswith("ai_memo_action:"),
        )

        # ADDED NEW HANDLERS FOR EVM
        self.rebot_dp.callback_query.register(
            handle_show_token_transfers_evm_callback,
            F.data == "show_token_transfers",  # MODIFIED from startswith
        )

        self.rebot_dp.callback_query.register(
            handle_ai_scam_check_evm_callback,
            F.data == "ai_scam_check_evm",  # MODIFIED from startswith
        )

        self.rebot_dp.callback_query.register(
            handle_admin_request_delete_memo_callback,
            F.data.startswith("admin_request_delete_memo:"),
        )

        self.rebot_dp.callback_query.register(
            handle_admin_confirm_delete_memo_callback,
            F.data.startswith("admin_confirm_delete_memo:"),
        )

        self.rebot_dp.callback_query.register(
            handle_admin_cancel_delete_memo_callback,
            F.data.startswith("admin_cancel_delete_memo:"),
        )

        self.rebot_dp.callback_query.register(
            handle_watch_new_memo_callback,  # Reusing the same handler for public memos
            F.data == "watch_new_memo",  # MODIFIED to use exact match
        )

        self.rebot_dp.callback_query.register(
            handle_watch_blockchain_events_callback,  # Reusing the same handler for private memos
            F.data == "watch_blockchain_events",  # MODIFIED to use exact match
        )

        # Register other handlers if any
        # self.rebot_dp.my_chat_member.register(member_status_update_handler)
        # self.rebot_dp.errors.register(unhandled_updates_handler)


async def main():
    """Main function"""
    rebot = Rebot()
    logging.info(
        "Bot created successfully: %s",
        rebot.bot.id,  # Logging bot ID or username can be useful
    )
    asyncio.create_task(poll_and_notify(rebot.bot))
    await rebot.rebot_dp.start_polling(rebot.bot)


async def poll_and_notify(bot):
    """Background polling task for memos and balance changes."""
    while True:
        db = SessionLocal()
        watched = get_all_watched_addresses(db)
        for watch in watched:
            telegram_user_id = watch.user.telegram_id  # For messaging only
            db_user_id = watch.user_id  # Internal DB ID for all DB updates
            logging.info(f"Polling address changes: {watch.address} for user: {telegram_user_id}")
            address = watch.address
            blockchain = watch.blockchain

            state_dict = get_user_watch_states(db, telegram_user_id) or {}
            key = f"{address}:{blockchain.lower()}"
            state = state_dict.get(key, {})

            # Poll memos if enabled
            if state.get("watch_memos"):
                memos = get_address_public_memos(address)
                last_memo_id = state.get("last_memo_id")
                new_memos = [m for m in memos if m["id"] != last_memo_id]
                if new_memos:
                    logging.info(f"New memos for {address} available: {new_memos}")
                    await bot.send_message(
                        telegram_user_id, f"New memos for {address}: {new_memos}"
                    )
                    # Update persistent last_memo_id
                    update_user_watch_state_last_memo_id(db, db_user_id, address, blockchain, new_memos[-1]["id"])

            # Poll balances if enabled
            if state.get("watch_events"):
                prev_data = state.get("last_state")
                if prev_data is None:
                    # First run: fetch and store current state, do not notify
                    _changes, _current_, full_response = get_tron_account_changes(address, None)
                    updated = update_user_watch_state_last_state(db, db_user_id, address, blockchain, full_response)
                    if not updated:
                        from database.queries import set_user_watch_state
                        set_user_watch_state(db, telegram_user_id, address, blockchain, watch_events=True)
                        update_user_watch_state_last_state(db, db_user_id, address, blockchain, full_response)
                    logging.info(f"First run for {address}: state stored, no notification sent.")
                    continue
                changes, _current_, full_response = get_tron_account_changes(address, prev_data)
                logging.info(f"poll_and_notify: address={address} changes={changes['changed'] is True}")
                # If changes were detected, format and send the message
                if changes["changed"] is True:
                    logging.debug(f"Changes detected for {address}")
                    # Prepare message details
                    details = changes.get("details", {})
                    lines = []
                    # Show changes for root keys
                    root_keys = [
                        "transactions_out",
                        "balance",
                        "transactions_in",
                        "totalTransactionCount",
                        "transactions",
                        "latest_operation_time",
                        "activated",
                    ]
                    for k in root_keys:
                        v = details.get(k, {})
                        prev_v = v.get("prev")
                        curr_v = v.get("curr")
                        if k == "latest_operation_time":
                            # Show only the last value in human-readable format
                            latest_op_human = details.get("latest_operation_time_human")
                            if latest_op_human:
                                lines.append(f"<b>{k}</b>: <b>{latest_op_human}</b>")
                            elif curr_v is not None:
                                # Fallback: try to format curr_v as datetime
                                try:
                                    dt = datetime.datetime.fromtimestamp(float(curr_v))
                                    lines.append(
                                        f"<b>{k}</b>: <b>{dt.strftime('%Y-%m-%d %H:%M:%S')}</b>"
                                    )
                                except Exception:
                                    lines.append(f"<b>{k}</b>: <b>{curr_v}</b>")
                            # Do not show diff for this key
                            continue
                        if (
                            prev_v is not None
                            and curr_v is not None
                            and prev_v != curr_v
                        ):
                            try:
                                diff = float(curr_v) - float(prev_v)
                                sign = "+" if diff > 0 else "-"
                                diff_str = f" ({sign}{int(abs(diff))})"
                            except Exception:
                                diff_str = ""
                            lines.append(
                                f"<b>{k}</b> changed: <b>{prev_v}</b> → <b>{curr_v}</b>{diff_str}"
                            )
                        elif curr_v is not None:
                            lines.append(f"<b>{k}</b>: <b>{curr_v}</b>")
                    # Show token changes
                    for token in details.get("withPriceTokens", []):
                        tid = token.get("tokenId")
                        name = (
                            token.get("tokenName", {}).get("curr")
                            if isinstance(token.get("tokenName"), dict)
                            else token.get("tokenName")
                        )
                        abbr = (
                            token.get("tokenAbbr", {}).get("curr")
                            if isinstance(token.get("tokenAbbr"), dict)
                            else token.get("tokenAbbr")
                        )
                        balance = token.get("balance", {})
                        amount = token.get("amount", {})
                        token_decimal = None
                        # Try to get tokenDecimal from current token snapshot
                        if "tokenDecimal" in token:
                            td = token["tokenDecimal"]
                            if isinstance(td, dict):
                                token_decimal = (
                                    td.get("curr")
                                    if isinstance(td.get("curr"), int)
                                    else None
                                )
                            elif isinstance(td, int):
                                token_decimal = td
                        elif "tokenDecimal" in token.get("curr", {}):
                            td = token["curr"]["tokenDecimal"]
                            if isinstance(td, dict):
                                token_decimal = (
                                    td.get("curr")
                                    if isinstance(td.get("curr"), int)
                                    else None
                                )
                            elif isinstance(td, int):
                                token_decimal = td
                        balance_prev = balance.get("prev")
                        balance_curr = balance.get("curr")
                        # Only show if balance changed (ignore amount-only changes)
                        if (
                            balance_prev is not None
                            and balance_curr is not None
                            and balance_prev != balance_curr
                        ):
                            diff = float(balance_curr) - float(balance_prev)
                            sign = "+" if diff > 0 else "-"
                            prev_fmt = format_balance(balance_prev, token_decimal)
                            curr_fmt = format_balance(balance_curr, token_decimal)
                            if token_decimal is not None:
                                diff_shifted = diff / (10**token_decimal)
                                diff_fmt = f"{abs(diff_shifted):.6f}".rstrip("0").rstrip(".")
                                change_line = f"balance: {prev_fmt} → {curr_fmt} ({sign}{diff_fmt})"
                            else:
                                diff_fmt = f"{abs(diff):.6f}".rstrip("0").rstrip(".")
                                change_line = f"balance: {prev_fmt} → {curr_fmt} ({sign}{diff_fmt})"
                            token_line = f"Token <b>{name}</b> ({abbr}): {change_line}"
                            lines.append(token_line)
                    # Always show static info
                    bot_username = getattr(bot, "username", Config.BOT_USERNAME)
                    deeplink = f"https://t.me/{bot_username}?start={address}"
                    tronscan_link = f"https://tronscan.org/#/address/{address}"
                    lines.append(f'Address: <a href="{deeplink}">{address}</a>')
                    lines.append(
                        f'TronScan: <a href="{tronscan_link}">{tronscan_link}</a>'
                    )
                    public_tag = details.get("publicTag")
                    if public_tag:
                        lines.append(f"Public Tag: <b>{public_tag}</b>")
                    date_created_human = details.get("date_created_human")
                    if date_created_human:
                        lines.append(f"Date Created: <b>{date_created_human}</b>")
                    latest_op_human = details.get("latest_operation_time_human")
                    if latest_op_human:
                        lines.append(f"Latest Operation: <b>{latest_op_human}</b>")

                    msg = "\n".join(lines)

                    def split_message(text, max_length):
                        lines = text.split("\n")
                        chunks = []
                        current_chunk = []
                        current_len = 0
                        for line in lines:
                            if current_len + len(line) + 1 > max_length:
                                chunks.append("\n".join(current_chunk))
                                current_chunk = [line]
                                current_len = len(line) + 1
                            else:
                                current_chunk.append(line)
                                current_len += len(line) + 1
                        if current_chunk:
                            chunks.append("\n".join(current_chunk))
                        return chunks

                    msg_chunks = split_message(msg, MAX_MSG_LENGTH - 50)
                    total_parts = len(msg_chunks)
                    for idx, chunk in enumerate(msg_chunks, 1):
                        part_info = f"\n--- End of Part {idx} of {total_parts} ---"
                        await bot.send_message(
                            telegram_user_id,
                            chunk + part_info,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                        )
                # Always update persistent last_state with the latest full response
                update_user_watch_state_last_state(db, db_user_id, address, blockchain, full_response)
        db.close()
        await asyncio.sleep(30)


# Calculate balance change using tokenDecimal
def format_balance(val, token_decimal=None):
    try:
        if val is None:
            return None
        val = float(val)
        if token_decimal is not None:
            s = f"{val / (10 ** token_decimal):.6f}".rstrip("0").rstrip(".")
            return s if s else "0"
        s = f"{val:.6f}".rstrip("0").rstrip(".")
        return s if s else "0"
    except Exception:
        return str(val)


if __name__ == "__main__":
    # 1. Create the filter and formatters
    custom_filter = UserIdContextFilter()

    # New format string for the console that uses the 'colored_user_id' field
    console_format_string = "%(asctime)s - [%(filename)s:%(lineno)d] - UserID: %(colored_user_id)s - %(message)s"

    # Instantiate AdminColorLogFormatter for console
    console_log_formatter = AdminColorLogFormatter(console_format_string)

    # Formatter for file (no color)
    file_log_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - [%(filename)s:%(lineno)d] - UserID: %(user_id)s - %(message)s"
    )

    # 2. Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(Config.LOG_LEVEL)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_log_formatter)  # Use colored formatter
    console_handler.addFilter(custom_filter)
    root_logger.addHandler(console_handler)

    # File Handler with Timed Rotation
    log_dir = os.path.join(
        os.path.dirname(__file__), "logs"
    )  # Ensure logs directory exists
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file_path = Config.get_log_file_path()
    file_handler = TimedRotatingFileHandler(
        log_file_path, when="midnight", interval=1, backupCount=7, encoding="utf-8"
    )
    file_handler.setFormatter(file_log_formatter)  # Use non-colored formatter for file
    file_handler.addFilter(custom_filter)
    root_logger.addHandler(file_handler)

    logging.info("Logging configured to write to console and file: %s", log_file_path)

    # 3. Configure Aiogram loggers
    aiogram_loggers_to_configure = [
        "aiogram.event",
        "aiogram.dispatcher",
        "aiogram.bot",
    ]
    for logger_name in aiogram_loggers_to_configure:
        logger = logging.getLogger(logger_name)
        logger.setLevel(Config.LOG_LEVEL)
        if logger.hasHandlers():
            logger.handlers.clear()
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        logger.propagate = False

    asyncio.run(main())
