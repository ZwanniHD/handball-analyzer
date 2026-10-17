from pathlib import Path
import pdfplumber

pdf_path = Path("data/raw_pdfs/match_392542.pdf")

if pdf_path.exists():
  with pdfplumber.open(pdf_path) as pdf:
    print("=== SEITE 1 REINETEXT ===")
    print(pdf.pages[0].extract_text())

    print("\n=== SEITE 1 TABELLEN (EXACT) ===")
    tables = pdf.pages[0].extract_tables()
    for t_idx, table in enumerate(tables):
      print(f"\n--- Tabelle {t_idx + 1} ---")
      for row in table[:8]:  # Erste 8 Zeilen der Tabelle
        print(row)
else:
  print(f"PDF nicht gefunden unter: {pdf_path}")