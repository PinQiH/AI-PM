import hashlib

def calculate_md5(file_content: bytes) -> str:
    """計算 bytes 內容的 MD5 雜湊值"""
    return hashlib.md5(file_content).hexdigest()

def calculate_md5_from_path(file_path: str) -> str:
    """從檔案路徑計算 MD5 雜湊值 (適用於大型檔案)"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()
