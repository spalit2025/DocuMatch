"""
Extraction Engine for DocuMatch Architect.

Uses local LLM (Ollama) to extract structured data from invoice documents.
"""

import json
import logging
import re
from typing import Callable, Optional, TypeVar

import requests

from .models import InvoiceSchema, LineItem, PurchaseOrderSchema

# Configure logging
logger = logging.getLogger(__name__)

T = TypeVar("T")

# System prompt for invoice extraction
EXTRACTION_SYSTEM_PROMPT = """You are a precise data extraction engine. Your task is to extract invoice information from document text and output it as valid JSON.

IMPORTANT RULES:
1. Output ONLY valid JSON - no explanations, no markdown, no additional text
2. Extract all available information from the document
3. If a field is not found, use null for optional fields or reasonable defaults
4. Dates should be in YYYY-MM-DD format when possible
5. Amounts should be numbers without currency symbols
6. Be precise with vendor names and invoice numbers

OUTPUT SCHEMA:
{
    "vendor_name": "string (required) - The company/vendor issuing the invoice",
    "invoice_number": "string (required) - The unique invoice identifier",
    "invoice_date": "string (required) - Date of invoice in YYYY-MM-DD format",
    "due_date": "string or null - Payment due date",
    "total_amount": "number (required) - Total invoice amount",
    "currency": "string - Currency code (default: USD)",
    "line_items": [
        {
            "description": "string - Item/service description",
            "quantity": "number - Quantity",
            "unit_price": "number - Price per unit",
            "total": "number - Line item total"
        }
    ],
    "payment_terms": "string or null - e.g., Net 30",
    "billing_address": "string or null - Billing address",
    "notes": "string or null - Additional notes"
}"""


EXTRACTION_USER_PROMPT = """Extract invoice data from the following document text. Output ONLY valid JSON matching the schema.

DOCUMENT TEXT:
{document_text}

JSON OUTPUT:"""


ERROR_RETRY_PROMPT = """Your previous response was not valid JSON. The error was: {error}

Please try again. Output ONLY valid JSON matching the invoice schema, with no additional text or explanation.

DOCUMENT TEXT:
{document_text}

JSON OUTPUT:"""


# System prompt for PO extraction
PO_EXTRACTION_SYSTEM_PROMPT = """You are a precise data extraction engine. Your task is to extract Purchase Order (PO) information from document text and output it as valid JSON.

IMPORTANT RULES:
1. Output ONLY valid JSON - no explanations, no markdown, no additional text
2. Extract all available information from the document
3. If a field is not found, use null for optional fields or reasonable defaults
4. Dates should be in YYYY-MM-DD format when possible
5. Amounts should be numbers without currency symbols
6. Be precise with vendor names and PO numbers

OUTPUT SCHEMA:
{
    "po_number": "string (required) - The unique PO identifier",
    "vendor_name": "string (required) - The supplier/vendor name",
    "order_date": "string (required) - Date PO was created in YYYY-MM-DD format",
    "expected_delivery_date": "string or null - Expected delivery date",
    "total_amount": "number (required) - Total PO amount",
    "currency": "string - Currency code (default: USD)",
    "line_items": [
        {
            "description": "string - Item/service description",
            "quantity": "number - Quantity ordered",
            "unit_price": "number - Price per unit",
            "total": "number - Line item total"
        }
    ],
    "billing_address": "string or null - Billing address",
    "shipping_address": "string or null - Shipping/delivery address",
    "payment_terms": "string or null - e.g., Net 30",
    "contract_reference": "string or null - Reference to contract or agreement",
    "notes": "string or null - Additional notes"
}"""


PO_EXTRACTION_USER_PROMPT = """Extract Purchase Order data from the following document text. Output ONLY valid JSON matching the schema.

DOCUMENT TEXT:
{document_text}

JSON OUTPUT:"""


PO_ERROR_RETRY_PROMPT = """Your previous response was not valid JSON. The error was: {error}

Please try again. Output ONLY valid JSON matching the Purchase Order schema, with no additional text or explanation.

DOCUMENT TEXT:
{document_text}

JSON OUTPUT:"""


class ExtractionEngine:
    """
    LLM-based extraction engine using Ollama.

    Extracts structured invoice data from markdown text using local LLMs.

    Usage:
        engine = ExtractionEngine(model="phi3.5")
        invoice = engine.extract_invoice_data(markdown_text)
    """

    def __init__(
        self,
        model: str = "phi3.5",
        ollama_host: str = "http://localhost:11434",
        temperature: float = 0.1,
        timeout: int = 120,
    ):
        """
        Initialize the extraction engine.

        Args:
            model: Ollama model name (e.g., "phi3.5", "llama3.2")
            ollama_host: Ollama API endpoint
            temperature: LLM temperature (lower = more deterministic)
            timeout: Request timeout in seconds
        """
        self.model = model
        self.ollama_host = ollama_host.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self._connection_verified = False

    def check_connection(self) -> tuple[bool, str]:
        """Check if Ollama is running and model is available."""
        try:
            response = requests.get(
                f"{self.ollama_host}/api/tags",
                timeout=5
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "").split(":")[0] for m in models]
                if self.model in model_names or any(self.model in m for m in model_names):
                    return True, f"Connected. Model '{self.model}' available."
                return False, f"Model '{self.model}' not found. Available: {', '.join(model_names)}"
            return False, f"Error: Status {response.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Ollama not running. Start with: ollama serve"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def extract_invoice_data(
        self,
        document_text: str,
        max_retries: int = 2,
    ) -> InvoiceSchema:
        """
        Extract structured invoice data from document text.

        Args:
            document_text: The markdown/text content of the invoice
            max_retries: Number of retry attempts on failure

        Returns:
            InvoiceSchema with extracted data

        Raises:
            ExtractionError: If extraction fails after all retries
        """
        return self._extract_with_retry(
            document_text=document_text,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=EXTRACTION_USER_PROMPT,
            retry_prompt=ERROR_RETRY_PROMPT,
            validator_fn=self._validate_invoice,
            doc_type="invoice",
            max_retries=max_retries,
        )

    def extract_po_data(
        self,
        document_text: str,
        max_retries: int = 2,
    ) -> PurchaseOrderSchema:
        """
        Extract structured Purchase Order data from document text.

        Args:
            document_text: The markdown/text content of the PO
            max_retries: Number of retry attempts on failure

        Returns:
            PurchaseOrderSchema with extracted data

        Raises:
            ExtractionError: If extraction fails after all retries
        """
        return self._extract_with_retry(
            document_text=document_text,
            system_prompt=PO_EXTRACTION_SYSTEM_PROMPT,
            user_prompt=PO_EXTRACTION_USER_PROMPT,
            retry_prompt=PO_ERROR_RETRY_PROMPT,
            validator_fn=self._validate_po,
            doc_type="PO",
            max_retries=max_retries,
        )

    def extract_raw(self, document_text: str) -> dict:
        """
        Extract invoice data and return raw dict (before validation).

        Useful for debugging or when you need the raw extracted data.
        """
        if not document_text or not document_text.strip():
            raise ExtractionError("Cannot extract from empty document")

        response = self._call_ollama(
            document_text, EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT
        )
        return self._parse_json_response(response)

    # ==================== CORE EXTRACTION LOGIC ====================

    def _extract_with_retry(
        self,
        document_text: str,
        system_prompt: str,
        user_prompt: str,
        retry_prompt: str,
        validator_fn: Callable[[dict], T],
        doc_type: str,
        max_retries: int = 2,
    ) -> T:
        """
        Generic extraction with retry logic.

        Args:
            document_text: The document text to extract from
            system_prompt: System prompt for the LLM
            user_prompt: User prompt template (must contain {document_text})
            retry_prompt: Retry prompt template (must contain {document_text} and {error})
            validator_fn: Function to validate parsed data into a schema
            doc_type: Human-readable document type for logging
            max_retries: Number of retry attempts

        Returns:
            Validated schema object

        Raises:
            ExtractionError: If extraction fails after all retries
        """
        if not document_text or not document_text.strip():
            raise ExtractionError("Cannot extract from empty document")

        # Truncate very long documents
        max_chars = 15000
        if len(document_text) > max_chars:
            logger.warning(f"Document truncated from {len(document_text)} to {max_chars} chars")
            document_text = document_text[:max_chars]

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                if attempt == 0:
                    response = self._call_ollama(
                        document_text, system_prompt, user_prompt
                    )
                else:
                    response = self._call_ollama(
                        document_text, system_prompt, retry_prompt,
                        error=str(last_error)
                    )

                data = self._parse_json_response(response)
                result = validator_fn(data)

                logger.info(f"Successfully extracted {doc_type} data")
                return result

            except json.JSONDecodeError as e:
                last_error = f"Invalid JSON: {str(e)}"
                logger.warning(f"Attempt {attempt + 1} failed: {last_error}")

            except ExtractionError as e:
                last_error = str(e)
                logger.warning(f"Attempt {attempt + 1} failed: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.error(f"Attempt {attempt + 1} failed with unexpected error: {e}")

        raise ExtractionError(
            f"{doc_type.capitalize()} extraction failed after {max_retries + 1} attempts. Last error: {last_error}"
        )

    def _call_ollama(
        self,
        document_text: str,
        system_prompt: str,
        user_prompt_template: str,
        error: Optional[str] = None,
    ) -> str:
        """Make an extraction request to Ollama."""
        format_kwargs = {"document_text": document_text}
        if error is not None:
            format_kwargs["error"] = error

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt_template.format(**format_kwargs)},
        ]

        return self._make_request(messages)

    def _verify_connection_once(self):
        """Verify Ollama connection and model availability on first use."""
        if self._connection_verified:
            return
        ok, msg = self.check_connection()
        if not ok:
            raise ExtractionError(f"Pre-flight check failed: {msg}")
        self._connection_verified = True

    def _make_request(self, messages: list) -> str:
        """Make request to Ollama API."""
        self._verify_connection_once()
        try:
            response = requests.post(
                f"{self.ollama_host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                    },
                    "format": "json",  # Request JSON output
                },
                timeout=self.timeout,
            )

            if response.status_code != 200:
                raise ExtractionError(f"Ollama API error: {response.status_code} - {response.text}")

            result = response.json()
            content = result.get("message", {}).get("content", "")

            if not content:
                raise ExtractionError("Empty response from Ollama")

            return content

        except requests.exceptions.Timeout:
            raise ExtractionError(f"Request timed out after {self.timeout}s")
        except requests.exceptions.ConnectionError:
            raise ExtractionError("Cannot connect to Ollama. Is it running?")

    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from LLM response, handling common issues."""
        # Clean up response
        response = response.strip()

        # Try direct JSON parse first
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError("Could not parse JSON from response", response, 0)

    # ==================== VALIDATION ====================

    @staticmethod
    def _parse_line_items(data: dict) -> list[LineItem]:
        """Parse line items from extracted data dict."""
        line_items = []
        raw_items = data.get("line_items", [])

        if isinstance(raw_items, list):
            for item in raw_items:
                if isinstance(item, dict):
                    line_items.append(LineItem(
                        description=str(item.get("description", "Unknown")),
                        quantity=float(item.get("quantity", 1)),
                        unit_price=float(item.get("unit_price", 0)),
                        total=float(item.get("total", 0)),
                    ))

        return line_items

    def _validate_invoice(self, data: dict) -> InvoiceSchema:
        """Validate and convert extracted data to InvoiceSchema."""
        try:
            return InvoiceSchema(
                vendor_name=str(data.get("vendor_name", "Unknown Vendor")),
                invoice_number=str(data.get("invoice_number", "N/A")),
                invoice_date=str(data.get("invoice_date", "Unknown")),
                due_date=data.get("due_date"),
                total_amount=float(data.get("total_amount", 0)),
                currency=str(data.get("currency", "USD")),
                line_items=self._parse_line_items(data),
                payment_terms=data.get("payment_terms"),
                billing_address=data.get("billing_address"),
                notes=data.get("notes"),
            )
        except Exception as e:
            raise ExtractionError(f"Validation failed: {str(e)}")

    def _validate_po(self, data: dict) -> PurchaseOrderSchema:
        """Validate and convert extracted data to PurchaseOrderSchema."""
        try:
            return PurchaseOrderSchema(
                po_number=str(data.get("po_number", "N/A")),
                vendor_name=str(data.get("vendor_name", "Unknown Vendor")),
                order_date=str(data.get("order_date", "Unknown")),
                expected_delivery_date=data.get("expected_delivery_date"),
                total_amount=float(data.get("total_amount", 0)),
                currency=str(data.get("currency", "USD")),
                line_items=self._parse_line_items(data),
                billing_address=data.get("billing_address"),
                shipping_address=data.get("shipping_address"),
                payment_terms=data.get("payment_terms"),
                contract_reference=data.get("contract_reference"),
                notes=data.get("notes"),
            )
        except Exception as e:
            raise ExtractionError(f"PO validation failed: {str(e)}")


class ExtractionError(Exception):
    """Exception raised when extraction fails."""
    pass


# Convenience functions
def extract_invoice(
    document_text: str,
    model: str = "phi3.5",
    ollama_host: str = "http://localhost:11434",
) -> InvoiceSchema:
    """
    Extract invoice data from document text.

    Args:
        document_text: The markdown/text content of the invoice
        model: Ollama model to use
        ollama_host: Ollama API endpoint

    Returns:
        InvoiceSchema with extracted data
    """
    engine = ExtractionEngine(model=model, ollama_host=ollama_host)
    return engine.extract_invoice_data(document_text)


def extract_po(
    document_text: str,
    model: str = "phi3.5",
    ollama_host: str = "http://localhost:11434",
) -> PurchaseOrderSchema:
    """
    Extract Purchase Order data from document text.

    Args:
        document_text: The markdown/text content of the PO
        model: Ollama model to use
        ollama_host: Ollama API endpoint

    Returns:
        PurchaseOrderSchema with extracted data
    """
    engine = ExtractionEngine(model=model, ollama_host=ollama_host)
    return engine.extract_po_data(document_text)
