"""
Google Sheets data sync integration for the Flow AI engine.

Post-write sync — Supabase is always the source of truth.
Sheets is a fire-and-forget read-only mirror for the business owner.

All sync functions MUST NEVER raise exceptions (entire body wrapped in try/except).
All gspread calls are synchronous — wrap in loop.run_in_executor.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Column headers (exact order matters)
CUSTOMER_HEADERS = [
    "ID",
    "Phone Number",
    "Display Name",
    "First Seen",
    "Last Seen",
    "Booking Count",
    "Escalation Flag",
]

BOOKING_HEADERS = [
    "ID",
    "Phone Number",
    "Customer Name",
    "Service Type",
    "Booking Date",
    "Booking Time",
    "Address",
    "Postal Code",
    "Unit Number",
    "Notes",
    "Status",
    "Created At",
]


def _build_sheets_client(creds_dict: dict):
    """
    Build an authenticated gspread client.
    
    Runs synchronously — wrap in run_in_executor when called from async code.
    """
    from google.oauth2 import service_account
    import gspread

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=scopes
    )
    return gspread.authorize(credentials)


def _customer_to_row(data: dict) -> list:
    """Convert customer dict to row list in CUSTOMER_HEADERS order."""
    return [
        str(data.get("id", "")),
        str(data.get("phone_number", "")),
        str(data.get("customer_name", "")),
        str(data.get("first_seen", "")),
        str(data.get("last_seen", "")),
        str(data.get("booking_count", 0)),
        "TRUE" if data.get("escalation_flag") else "FALSE",
    ]


def _booking_to_row(data: dict) -> list:
    """
    Convert booking dict to row list in BOOKING_HEADERS order.
    
    Note: booking_tools.py uses different column names:
    - booking_id → id
    - slot_date → booking_date
    - slot_window → booking_time
    - booking_status → status
    """
    return [
        str(data.get("id") or data.get("booking_id", "")),
        str(data.get("phone_number", "")),
        str(data.get("customer_name", "")),
        str(data.get("service_type", "")),
        str(data.get("booking_date") or data.get("slot_date", "")),
        str(data.get("booking_time") or data.get("slot_window", "")),
        str(data.get("address", "")),
        str(data.get("postal_code", "")),
        str(data.get("unit_number", "")),
        str(data.get("notes", "")),
        str(data.get("status") or data.get("booking_status", "")),
        str(data.get("created_at", "")),
    ]


def _sync_row(
    gc,
    spreadsheet_id: str,
    tab_name: str,
    headers: list,
    row_data: list,
    row_id: str,
) -> None:
    """
    Sync a single row to a Google Sheet.
    
    Runs synchronously — wrap in run_in_executor.
    
    Logic:
    1. Get all rows
    2. If empty: write header + data row
    3. If only header: append data row
    4. Scan for existing row by ID (first column)
    5. If found: update
    6. If not found: append
    """
    spreadsheet = gc.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(tab_name)
    
    all_rows = worksheet.get_all_values()
    
    # Empty sheet — write header + data
    if len(all_rows) == 0:
        worksheet.append_row(headers)
        worksheet.append_row(row_data)
        logger.debug(
            f"Sheets sync: created header + row in {tab_name} (ID: {row_id})"
        )
        return

    # First row is not the expected header — insert header at top
    if all_rows[0] != headers:
        worksheet.insert_row(headers, index=1)
        all_rows = [headers] + all_rows
        logger.info(
            f"Sheets sync: inserted missing header row in {tab_name}"
        )

    # Only header row — append data
    if len(all_rows) == 1:
        worksheet.append_row(row_data)
        logger.debug(f"Sheets sync: appended new row to {tab_name} (ID: {row_id})")
        return
    
    # Scan for existing row by ID (first column)
    found_index = None
    for i, row in enumerate(all_rows[1:], start=1):  # skip header
        if row and row[0] == row_id:
            if found_index is None:
                found_index = i
            else:
                logger.warning(
                    f"Sheets sync: duplicate ID {row_id} in {tab_name} "
                    f"(rows {found_index+1} and {i+1}) — updating first match"
                )
                break
    
    if found_index is not None:
        # Update existing row (1-based indexing, +1 for header)
        row_number = found_index + 1
        last_col = chr(ord("A") + len(row_data) - 1)
        range_notation = f"A{row_number}:{last_col}{row_number}"
        worksheet.update(range_notation, [row_data])
        logger.debug(
            f"Sheets sync: updated row {row_number} in {tab_name} (ID: {row_id})"
        )
    else:
        # Append new row
        worksheet.append_row(row_data)
        logger.debug(f"Sheets sync: appended new row to {tab_name} (ID: {row_id})")


async def sync_customer_to_sheets(
    client_id: str,
    client_config,
    customer_data: dict,
) -> None:
    """
    Sync a customer record to Google Sheets (fire-and-forget).
    
    MUST NEVER raise exceptions. All errors are logged and swallowed.
    
    Args:
        client_id: Client identifier
        client_config: ClientConfig object with sheets settings
        customer_data: Customer dict from Supabase
    """
    try:
        # Check if sync is enabled
        if not client_config.sheets_sync_enabled:
            return
        
        if not client_config.sheets_spreadsheet_id:
            logger.error(
                f"Sheets sync enabled but no spreadsheet_id configured "
                f"(client: {client_id})"
            )
            return
        
        if not client_config.sheets_service_account_creds:
            logger.error(
                f"Sheets sync enabled but no service account creds "
                f"(client: {client_id})"
            )
            return
        
        # Build client and sync row
        loop = asyncio.get_event_loop()
        gc = await loop.run_in_executor(
            None,
            _build_sheets_client,
            client_config.sheets_service_account_creds,
        )
        
        row_data = _customer_to_row(customer_data)
        row_id = str(customer_data.get("id", ""))
        
        await loop.run_in_executor(
            None,
            _sync_row,
            gc,
            client_config.sheets_spreadsheet_id,
            "Customers",
            CUSTOMER_HEADERS,
            row_data,
            row_id,
        )
        
        logger.info(
            f"Sheets sync succeeded | client={client_id} table=customers "
            f"row_id={row_id}"
        )
        
    except Exception as e:
        logger.error(
            f"Sheets sync failed | client={client_id} table=customers "
            f"row_id={customer_data.get('id')} error={type(e).__name__}: {e}",
            exc_info=True,
        )


async def sync_booking_to_sheets(
    client_id: str,
    client_config,
    booking_data: dict,
) -> None:
    """
    Sync a booking record to Google Sheets (fire-and-forget).
    
    MUST NEVER raise exceptions. All errors are logged and swallowed.
    
    Args:
        client_id: Client identifier
        client_config: ClientConfig object with sheets settings
        booking_data: Booking dict from Supabase
    """
    try:
        # Check if sync is enabled
        if not client_config.sheets_sync_enabled:
            return
        
        if not client_config.sheets_spreadsheet_id:
            logger.error(
                f"Sheets sync enabled but no spreadsheet_id configured "
                f"(client: {client_id})"
            )
            return
        
        if not client_config.sheets_service_account_creds:
            logger.error(
                f"Sheets sync enabled but no service account creds "
                f"(client: {client_id})"
            )
            return
        
        # Build client and sync row
        loop = asyncio.get_event_loop()
        gc = await loop.run_in_executor(
            None,
            _build_sheets_client,
            client_config.sheets_service_account_creds,
        )
        
        row_data = _booking_to_row(booking_data)
        row_id = str(booking_data.get("id") or booking_data.get("booking_id", ""))
        
        await loop.run_in_executor(
            None,
            _sync_row,
            gc,
            client_config.sheets_spreadsheet_id,
            "Bookings",
            BOOKING_HEADERS,
            row_data,
            row_id,
        )
        
        logger.info(
            f"Sheets sync succeeded | client={client_id} table=bookings "
            f"row_id={row_id}"
        )
        
    except Exception as e:
        logger.error(
            f"Sheets sync failed | client={client_id} table=bookings "
            f"row_id={booking_data.get('id') or booking_data.get('booking_id')} "
            f"error={type(e).__name__}: {e}",
            exc_info=True,
        )
