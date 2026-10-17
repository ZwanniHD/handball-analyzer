from pathlib import Path
import requests

BASE_URL = "https://handball360.isquad.de/dhb_acta_completa_pdf.php?id_partido="


def download_pdf(
    match_id: str, output_dir: Path = Path("data/raw_pdfs")
) -> Path:
  """Lädt die Spielbericht-PDF für eine gegebene Match ID herunter."""
  output_dir.mkdir(parents=True, exist_ok=True)
  file_path = output_dir / f"match_{match_id}.pdf"

  if file_path.exists():
    print(f"PDF für Match {match_id} existiert bereits lokal.")
    return file_path

  url = f"{BASE_URL}{match_id}"
  print(f"Lade Spielbericht herunter: {url}")

  response = requests.get(url, timeout=15)
  response.raise_for_status()

  with open(file_path, "wb") as f:
    f.write(response.content)

  print(f"Gespeichert unter: {file_path}")
  return file_path


if __name__ == "__main__":
  # Test mit der Spiel-ID aus deiner Beispiel-PDF (392542)[cite: 1]
  test_id = "392542"
  download_pdf(test_id)