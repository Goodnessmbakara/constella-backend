from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, HttpUrl
import requests
import PyPDF2
import io
import tempfile
import os
from typing import Optional, Tuple

router = APIRouter(prefix="/helpers", tags=["helpers"])

class PDFUrlRequest(BaseModel):
    url: HttpUrl
    timeout: Optional[int] = 30

class PDFResponse(BaseModel):
    text: str
    num_pages: int
    url: str

def read_pdf_from_url(url: str, timeout: int = 30) -> Tuple[str, int]:
    """
    Read PDF content from a URL and return the parsed text and number of pages.

    Args:
        url: The URL of the PDF to read
        timeout: Request timeout in seconds

    Returns:
        Tuple containing (extracted_text, num_pages)

    Raises:
        requests.RequestException: If PDF download fails
        PyPDF2.errors.PdfReadError: If PDF parsing fails
        Exception: For any other unexpected errors
    """
    # Download the PDF
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()

    # Check if the response is actually a PDF
    content_type = response.headers.get('content-type', '')
    if 'application/pdf' not in content_type and not url.endswith('.pdf'):
        # Try to parse anyway, but warn
        pass

    # Create a BytesIO object from the PDF content
    pdf_bytes = io.BytesIO(response.content)

    # Parse the PDF
    pdf_reader = PyPDF2.PdfReader(pdf_bytes)

    # Extract text from all pages
    text_content = ""
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text_content += page.extract_text() + "\n"

    # Clean up the text (remove excessive whitespace)
    text_content = " ".join(text_content.split())

    return text_content, len(pdf_reader.pages)

@router.post("/read_pdf", response_model=PDFResponse)
async def read_pdf(request: PDFUrlRequest):
    """
    Read PDF content from a URL and return the parsed text.

    Args:
        request: PDFUrlRequest containing the URL and optional timeout

    Returns:
        PDFResponse with extracted text, number of pages, and source URL
    """
    try:
        text_content, num_pages = read_pdf_from_url(str(request.url), request.timeout)

        return PDFResponse(
            text=text_content,
            num_pages=num_pages,
            url=str(request.url)
        )

    except requests.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to download PDF from URL: {str(e)}"
        )
    except PyPDF2.errors.PdfReadError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse PDF: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )
