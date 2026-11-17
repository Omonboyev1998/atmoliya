from datetime import datetime
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config import REPORTS_DIR
from database.db import (
    get_fund_stats,
    get_all_members,
    get_member_debts,
    get_recent_transactions,
    get_connection
)

async def generate_financial_report() -> Path:
    wb = openpyxl.Workbook()

    # Ranglar va uslublar
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    sub_header_fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
    green_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    red_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")

    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=11, bold=True)
    font_regular = Font(name="Calibri", size=11)
    font_title = Font(name="Calibri", size=16, bold=True, color="1F497D")

    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    stats = await get_fund_stats()
    members = await get_all_members(active_only=True)

    # ================= 1. UMUMIY HOLAT (SUMMARY) =================
    ws_summary = wb.active
    ws_summary.title = "Kassa Holati"
    ws_summary.views.sheetView[0].showGridLines = True

    ws_summary["B2"] = "KAFEDRA FONDI MOLIYAVIY HISOBOTI"
    ws_summary["B2"].font = font_title
    ws_summary["B3"] = f"Hisobot shakllantirilgan sana: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    ws_summary["B3"].font = Font(name="Calibri", size=10, italic=True)

    summary_data = [
        ("KASSA JORIY BALANSI (QOLDIQ)", f"{stats['balance']:,} so'm", True),
        ("Jami tushumlar (Kirim)", f"{stats['total_income']:,} so'm", False),
        ("  - Oylik badallar (50 000 so'm)", f"{stats['monthly_income']:,} so'm", False),
        ("  - Tug'ilgan kun yig'imlari (25 000 so'm)", f"{stats['birthday_income']:,} so'm", False),
        ("Jami xarajatlar (Chiqim)", f"{stats['total_expense']:,} so'm", False),
        ("  - Tug'ilgan kun mukofotlari (500 000 so'm)", f"{stats['gifts_expense']:,} so'm", False),
        ("  - Boshqa kafedra xarajatlari", f"{stats['other_expense']:,} so'm", False),
        ("Kafedraning faol a'zolari soni", f"{len(members)} nafar", False),
    ]

    row_idx = 5
    for label, val, is_highlight in summary_data:
        cell_lbl = ws_summary.cell(row=row_idx, column=2, value=label)
        cell_val = ws_summary.cell(row=row_idx, column=3, value=val)

        cell_lbl.border = thin_border
        cell_val.border = thin_border
        cell_val.alignment = Alignment(horizontal="right")

        if is_highlight:
            cell_lbl.font = font_bold
            cell_val.font = font_bold
            cell_lbl.fill = sub_header_fill
            cell_val.fill = sub_header_fill
        else:
            cell_lbl.font = font_regular
            cell_val.font = font_regular
        row_idx += 1

    # ================= 2. XODIMLAR VA QARZLAR =================
    ws_members = wb.create_sheet(title="Xodimlar va Badallar")
    ws_members.views.sheetView[0].showGridLines = True

    headers = [
        "T/r", "Xodim F.I.SH", "Telefon", "Tug'ilgan sana",
        "To'lanmagan oylik (so'm)", "To'lanmagan t-kun (so'm)", "Jami qarz (so'm)", "Holat"
    ]

    for col_idx, h in enumerate(headers, 1):
        cell = ws_members.cell(row=1, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    total_unpaid_all = 0
    for idx, m in enumerate(members, 1):
        debts = await get_member_debts(m["id"])
        monthly_debt_sum = sum(d["amount"] for d in debts["monthly_debts"])
        bday_debt_sum = sum(d["amount"] for d in debts["birthday_debts"])
        total_m_debt = debts["total_debt"]
        total_unpaid_all += total_m_debt

        row_data = [
            idx,
            m["full_name"],
            m.get("phone") or "-",
            m["birth_date"],
            monthly_debt_sum,
            bday_debt_sum,
            total_m_debt,
            "Qarzdor" if total_m_debt > 0 else "Qarzi yo'q"
        ]

        row_num = idx + 1
        for col_idx, val in enumerate(row_data, 1):
            cell = ws_members.cell(row=row_num, column=col_idx, value=val)
            cell.font = font_regular
            cell.border = thin_border
            if col_idx in [5, 6, 7]:
                cell.number_format = '#,##0'
                cell.alignment = Alignment(horizontal="right")
            elif col_idx in [1, 3, 4, 8]:
                cell.alignment = Alignment(horizontal="center")

            if col_idx == 8:
                cell.fill = red_fill if total_m_debt > 0 else green_fill

    # Jami qator
    summary_row = len(members) + 2
    ws_members.cell(row=summary_row, column=2, value="JAMI:").font = font_bold
    ws_members.cell(row=summary_row, column=7, value=total_unpaid_all).font = font_bold
    ws_members.cell(row=summary_row, column=7).number_format = '#,##0'
    ws_members.cell(row=summary_row, column=7).alignment = Alignment(horizontal="right")

    # ================= 3. TRANSAKSIYALAR (KASSA DAFTARI) =================
    ws_tx = wb.create_sheet(title="Kassa Jurnali")
    ws_tx.views.sheetView[0].showGridLines = True

    tx_headers = ["ID", "Vaqt", "Turi", "Kategoriya", "Summa (so'm)", "Xodim", "Tafsilot"]
    for col_idx, h in enumerate(tx_headers, 1):
        cell = ws_tx.cell(row=1, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    with get_connection() as conn:
        transactions = conn.execute("""
            SELECT t.*, m.full_name 
            FROM transactions t
            LEFT JOIN members m ON t.member_id = m.id
            ORDER BY t.id DESC
        """).fetchall()

    for idx, tx in enumerate(transactions, 2):
        tx_type_str = "Kirim" if tx["type"] == "income" else "Chiqim"
        row_vals = [
            tx["id"],
            tx["created_at"],
            tx_type_str,
            tx["category"],
            tx["amount"],
            tx["full_name"] or "-",
            tx["description"] or "-"
        ]
        for col_idx, val in enumerate(row_vals, 1):
            cell = ws_tx.cell(row=idx, column=col_idx, value=val)
            cell.font = font_regular
            cell.border = thin_border
            if col_idx == 5:
                cell.number_format = '#,##0'
                cell.alignment = Alignment(horizontal="right")
                cell.fill = green_fill if tx["type"] == "income" else red_fill
            elif col_idx in [1, 2, 3]:
                cell.alignment = Alignment(horizontal="center")

    # Barcha varaqlarda ustun kengliklarini avtomatik moslashtirish
    for sheet in wb.worksheets:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len:
                    max_len = len(val)
            sheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = REPORTS_DIR / f"kafedra_fondi_hisobot_{now_str}.xlsx"
    wb.save(file_path)
    return file_path
