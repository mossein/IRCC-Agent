"""Document loader for processing user documents (PDFs, images, text)."""

import logging
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class DocumentLoader:
    """Load and extract text from various document formats."""

    SUPPORTED_EXTENSIONS = {
        ".pdf": "pdf",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".bmp": "image",
        ".txt": "text",
        ".md": "text",
        ".doc": "text",
        ".docx": "text",
    }

    def __init__(self, use_ocr: bool = True):
        """Initialize document loader.

        Args:
            use_ocr: Whether to use OCR for images and scanned PDFs.
        """
        self.use_ocr = use_ocr
        self._tesseract_available: Optional[bool] = None

    @property
    def tesseract_available(self) -> bool:
        """Check if tesseract is available for OCR."""
        if self._tesseract_available is None:
            try:
                import pytesseract

                pytesseract.get_tesseract_version()
                self._tesseract_available = True
            except Exception:
                self._tesseract_available = False
                logger.warning(
                    "Tesseract not available. OCR will be disabled. "
                    "Install with: brew install tesseract"
                )
        return self._tesseract_available

    def load_file(self, file_path: Path) -> list[Document]:
        """Load a single file and return extracted documents.

        Args:
            file_path: Path to the file to load.

        Returns:
            List of Document objects with extracted text.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = file_path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            logger.warning(f"Unsupported file type: {ext}")
            return []

        doc_type = self.SUPPORTED_EXTENSIONS[ext]
        metadata = {
            "source": str(file_path),
            "filename": file_path.name,
            "extension": ext,
        }

        try:
            if doc_type == "pdf":
                return self._load_pdf(file_path, metadata)
            elif doc_type == "image":
                return self._load_image(file_path, metadata)
            elif doc_type == "text":
                return self._load_text(file_path, metadata)
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return []

        return []

    def _load_pdf(self, file_path: Path, metadata: dict) -> list[Document]:
        """Extract text from PDF using PyMuPDF."""
        documents = []

        with fitz.open(file_path) as pdf:
            for page_num, page in enumerate(pdf, start=1):
                text = page.get_text()

                # If page has little text, try OCR if available
                if len(text.strip()) < 50 and self.use_ocr and self.tesseract_available:
                    text = self._ocr_page(page)

                if text.strip():
                    page_metadata = {**metadata, "page": page_num}
                    documents.append(Document(page_content=text, metadata=page_metadata))

        logger.info(f"Loaded {len(documents)} pages from {file_path.name}")
        return documents

    def _ocr_page(self, page: fitz.Page) -> str:
        """Perform OCR on a PDF page."""
        try:
            import pytesseract
            from PIL import Image
            import io

            # Render page to image
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better OCR
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            # Run OCR
            text = pytesseract.image_to_string(img)
            return text
        except Exception as e:
            logger.warning(f"OCR failed: {e}")
            return ""

    def _load_image(self, file_path: Path, metadata: dict) -> list[Document]:
        """Extract text from image using OCR."""
        if not self.use_ocr or not self.tesseract_available:
            logger.warning(f"Cannot process image {file_path.name}: OCR not available")
            return []

        try:
            import pytesseract
            from PIL import Image

            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)

            if text.strip():
                return [Document(page_content=text, metadata=metadata)]
        except Exception as e:
            logger.error(f"Error OCR-ing image {file_path}: {e}")

        return []

    def _load_text(self, file_path: Path, metadata: dict) -> list[Document]:
        """Load plain text file."""
        try:
            text = file_path.read_text(encoding="utf-8")
            if text.strip():
                return [Document(page_content=text, metadata=metadata)]
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                text = file_path.read_text(encoding="latin-1")
                if text.strip():
                    return [Document(page_content=text, metadata=metadata)]
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        return []


def load_documents_from_directory(
    directory: Path,
    recursive: bool = True,
    use_ocr: bool = True,
) -> list[Document]:
    """Load all documents from a directory.

    Args:
        directory: Path to directory containing documents.
        recursive: Whether to search subdirectories.
        use_ocr: Whether to use OCR for images.

    Returns:
        List of Document objects from all files.
    """
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    loader = DocumentLoader(use_ocr=use_ocr)
    documents = []

    pattern = "**/*" if recursive else "*"
    for file_path in directory.glob(pattern):
        if file_path.is_file():
            docs = loader.load_file(file_path)
            documents.extend(docs)

    logger.info(f"Loaded {len(documents)} documents from {directory}")
    return documents
