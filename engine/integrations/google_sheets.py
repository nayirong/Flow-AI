"""
Google Sheets data sync integration for the Flow AI engine.

Post-write sync — Supabase is always the source of truth.
Sheets is a fire-and-forget read-only mirror for the business owner.

All sync functions MUST NEVER raise exceptions (entire body wrapped in try/except).
All gspread calls are synchronous — wrap in loop.run_in_executor.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_SGT = timezone(timedelta(hours=8))


def _to_sgt(ts) -> str:
    """Convert a UTC timestamp (ISO string or datetime) to Singapore Time (UTC+8)."""
    if not ts:
        return ""
    try:
        if isinstance(ts, datetime):
            dt = ts
        else:
            ts_str = str(ts).replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_SGT).strftime("%Y-%m-%d %H:%M SGT")
    except Exception:
        return str(ts)


# Column headers (exact order matters — must match Supabase column names used in row mappers)
CUSTOMER_HEADERS = [
    "ID",
    "Phone Number",
    "Display Name",
    "First Seen",
    "Last Seen",
    "Booking Count",
    "Escalation Flag",
    "Notes",
    "Escalation Reason",
]

BOOKING_HEADERS = [
    "ID",
    "Phone Number",
    "Customer Name",
    "Service Type",
    "Unit Count",
    "Aircon Brand",
    "Booking Date",
    "Booking Time",
    "Address",
    "Postal Code",
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
        _to_sgt(data.get("first_seen", "")),
        _to_sgt(data.get("last_seen", "")),
        str(data.get("total_bookings", 0)),
        "TRUE" if data.get("escalation_flag") else "FALSE",
        str(data.get("notes", "") or ""),
        str(data.get("escalation_reason", "") or ""),
    ]


def _booking_to_row(data: dict) -> list:
    """
    Convert booking dict to row list in BOOKING_HEADERS order.

    Note: booking_tools.py uses different column names:
    - booking_id → id
    - slot_date  → booking_date
    - slot_window → booking_time
    - booking_status → status
    """
    return [
        str(data.get("id") or data.get("booking_id", "")),
        str(data.get("phone_number", "")),
        str(data.get("customer_name", "")),
        str(data.get("service_type", "")),
        str(data.get("unit_count", "")),
        str(data.get("aircon_brand", "") or ""),
        str(data.get("booking_date") or data.get("slot_date", "")),
        str(data.get("booking_time") or data.get("slot_window", "")),
        str(data.get("address", "")),
        str(data.get("postal_code", "")),
        str(data.get("notes", "") or ""),
        str(data.get("status") or data.get("booking_status", "")),
        _to_sgt(data.get("created_at", "")),
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
        # Log as non-critical failure (does not block any customer-facing flow)
        try:
            from engine.integrations.observability import log_noncritical_failure
            asyncio.create_task(log_noncritical_failure(
                source="sheets_sync_customer",
                error_type=type(e).__name__,
                error_message=str(e),
                client_id=client_id,
                context={"row_id": str(customer_data.get("id", ""))},
            ))
        except Exception:
            pass  # Observability must never raise


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
        # Log as non-critical failure (booking is already in Supabase — Sheets is mirror only)
        try:
            from engine.integrations.observability import log_noncritical_failure
            asyncio.create_task(log_noncritical_failure(
                source="sheets_sync_booking",
                error_type=type(e).__name__,
                error_message=str(e),
                client_id=client_id,
                context={"row_id": str(booking_data.get("id") or booking_data.get("booking_id", ""))},
            ))
        except Exception:
            pass  # Observability must never raise
