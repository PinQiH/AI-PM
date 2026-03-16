import os
import PyPDF2
from docx import Document
import pandas as pd
from typing import Optional

def extract_text_from_file(file_path: str, file_type: str) -> Optional[str]:
    """
    根據副檔名解析文檔並萃取文字
    """
    if not os.path.exists(file_path):
        return None

    try:
        if file_type == "pdf":
            text = ""
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            return text.strip()

        elif file_type == "docx" or file_type == "doc":
            doc = Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
            return text.strip()

        elif file_type in ["xlsx", "xls", "csv"]:
            if file_type == "csv":
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            # 將表格轉為字串表示
            return df.to_string(index=False)

        elif file_type == "txt":
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().strip()

        else:
            # 不支援的格式
            raise ValueError(f"Unsupported file type: {file_type}")

    except Exception as e:
        print(f"Error parsing file {file_path}: {e}")
        return None
