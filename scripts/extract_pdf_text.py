
from pdfminer.high_level import extract_text

def extract_text_from_pdf(pdf_path):
    try:
        return extract_text(pdf_path)
    except Exception as e:
        return f"Error extracting text: {e}"

if __name__ == "__main__":
    import sys
    pdf_path = sys.argv[1]
    output_path = sys.argv[2]
    text = extract_text_from_pdf(pdf_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
