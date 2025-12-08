"""Core agent logic for IRCC form filling."""

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from ircc_agent.agent.prompts import (
    BATCH_EXTRACTION_PROMPT,
    CLARIFICATION_PROMPT,
    FIELD_EXTRACTION_PROMPT,
    SYSTEM_PROMPT,
    VALIDATION_PROMPT,
)
from ircc_agent.config import settings
from ircc_agent.pdf.extractor import FieldType, FormField, FormFieldExtractor
from ircc_agent.pdf.filler import PDFFiller
from ircc_agent.rag.store import VectorStore

logger = logging.getLogger(__name__)


class IRCCAgent:
    """LLM agent for extracting information and filling IRCC forms."""

    def __init__(
        self,
        vector_store: VectorStore | None = None,
    ):
        """Initialize the agent.

        Args:
            vector_store: Optional pre-configured vector store.
        """
        self.vector_store = vector_store or VectorStore()
        self._llm = None

    @property
    def llm(self):
        """Get or create the LLM client. Uses OpenAI if available, else Gemini."""
        if self._llm is None:
            # Prefer OpenAI (more reliable rate limits)
            if settings.openai_api_key:
                from langchain_openai import ChatOpenAI
                model_name = getattr(settings, 'openai_model_name', 'gpt-5.1')
                logger.info(f"Using OpenAI LLM ({model_name})")
                self._llm = ChatOpenAI(
                    model=model_name,
                    openai_api_key=settings.openai_api_key,
                    temperature=settings.temperature,
                )
            elif settings.google_api_key:
                logger.info(f"Using Google Gemini LLM ({settings.model_name})")
                self._llm = ChatGoogleGenerativeAI(
                    model=settings.model_name,
                    google_api_key=settings.google_api_key,
                    temperature=settings.temperature,
                )
            else:
                raise RuntimeError("No LLM API key configured. Set OPENAI_API_KEY or GOOGLE_API_KEY.")
        return self._llm

    def extract_field_value(
        self,
        field: FormField,
        context_docs: list | None = None,
    ) -> dict[str, Any]:
        """Extract value for a single field using RAG.

        Args:
            field: Form field to extract value for.
            context_docs: Optional pre-retrieved context documents.

        Returns:
            Dictionary with extracted value and metadata.
        """
        # Get relevant context if not provided
        if context_docs is None:
            # Create a search query based on field name and tooltip
            query = f"{field.name} {field.tooltip}".strip()
            context_docs = self.vector_store.similarity_search(query)

        # Format context for prompt
        context = "\n\n---\n\n".join(
            [f"[Source: {doc.metadata.get('source', 'unknown')}]\n{doc.page_content}" 
             for doc in context_docs]
        )

        # Format options if applicable
        options_text = ""
        if field.options:
            options_text = f"**Available Options**: {', '.join(field.options)}"

        # Create prompt
        prompt = FIELD_EXTRACTION_PROMPT.format(
            field_name=field.name,
            field_type=field.field_type.value,
            tooltip=field.tooltip or "No description available",
            options_text=options_text,
            context=context if context else "No relevant documents found.",
        )

        # Query LLM
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        try:
            response = self.llm.invoke(messages)
            result = self._parse_json_response(response.content)
            return result
        except Exception as e:
            logger.error(f"Error extracting field '{field.name}': {e}")
            return {"value": "NOT FOUND", "confidence": "low", "error": str(e)}

    def extract_all_fields(
        self,
        form_path: Path | str,
        batch_size: int = 10,
    ) -> dict[str, Any]:
        """Extract values for all fields in a form.

        Args:
            form_path: Path to the PDF form.
            batch_size: Number of fields to process in each batch.

        Returns:
            Dictionary mapping field names to extracted values.
        """
        extractor = FormFieldExtractor(form_path)
        fields = extractor.extract_fields()

        if not fields:
            logger.warning("No form fields found")
            return {}

        logger.info(f"Extracting values for {len(fields)} fields")

        results = {}
        
        # Process fields in batches for efficiency
        for i in range(0, len(fields), batch_size):
            batch = fields[i:i + batch_size]
            batch_results = self._extract_batch(batch)
            results.update(batch_results)

        return results

    def _extract_batch(self, fields: list[FormField]) -> dict[str, Any]:
        """Extract values for a batch of fields."""
        # Create combined query for context retrieval
        combined_query = " ".join([f.name for f in fields])
        context_docs = self.vector_store.similarity_search(combined_query, k=10)

        context = "\n\n---\n\n".join(
            [f"[Source: {doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
             for doc in context_docs]
        )

        # Format fields for prompt
        fields_json = json.dumps(
            [{"name": f.name, "type": f.field_type.value, "options": f.options}
             for f in fields],
            indent=2
        )

        prompt = BATCH_EXTRACTION_PROMPT.format(
            fields_json=fields_json,
            context=context if context else "No documents available.",
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        try:
            response = self.llm.invoke(messages)
            result = self._parse_json_response(response.content)

            # Extract just the values
            extracted = {}
            for field_name, data in result.items():
                if isinstance(data, dict):
                    value = data.get("value", "NOT FOUND")
                else:
                    value = data
                extracted[field_name] = value

            return extracted
        except Exception as e:
            logger.error(f"Error in batch extraction: {e}")
            # Fall back to individual extraction
            results = {}
            for field in fields:
                result = self.extract_field_value(field, context_docs)
                results[field.name] = result.get("value", "NOT FOUND")
            return results

    def validate_filled_data(
        self,
        filled_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate filled form data for consistency and accuracy.

        Args:
            filled_data: Dictionary of field names to values.

        Returns:
            Validation results with issues and suggestions.
        """
        # Get context for validation
        combined_query = " ".join(list(filled_data.keys())[:10])
        context_docs = self.vector_store.similarity_search(combined_query, k=5)

        context = "\n\n".join([doc.page_content for doc in context_docs])

        prompt = VALIDATION_PROMPT.format(
            filled_data=json.dumps(filled_data, indent=2),
            context=context,
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        try:
            response = self.llm.invoke(messages)
            return self._parse_json_response(response.content)
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return {"is_valid": True, "issues": [], "warnings": [str(e)]}

    def get_clarification_questions(
        self,
        missing_fields: list[str],
    ) -> list[dict[str, str]]:
        """Generate user-friendly questions for missing fields.

        Args:
            missing_fields: List of field names that couldn't be filled.

        Returns:
            List of questions to ask the user.
        """
        prompt = CLARIFICATION_PROMPT.format(
            missing_fields=json.dumps(missing_fields, indent=2)
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        try:
            response = self.llm.invoke(messages)
            result = self._parse_json_response(response.content)
            return result.get("questions", [])
        except Exception as e:
            logger.error(f"Error generating questions: {e}")
            return [{"field": f, "question": f"What is your {f}?"} for f in missing_fields]

    def fill_form(
        self,
        form_path: Path | str,
        output_path: Path | str,
        historical_forms_dirs: list[Path | str] | None = None,
        interactive: bool = False,
    ) -> dict[str, Any]:
        """Complete workflow: extract, validate, and fill a form.

        Prioritizes data sources in this order:
        1. Previously filled forms of the same type (highest confidence)
        2. RAG extraction from user documents
        3. Manual input (if interactive)

        Args:
            form_path: Path to the IRCC PDF form.
            output_path: Path for the filled output PDF.
            historical_forms_dirs: Directories to search for previously filled forms.
            interactive: Whether to prompt for missing fields.

        Returns:
            Dictionary with filled data and status.
        """
        from ircc_agent.pdf.history import FilledFormParser, find_historical_form_data

        form_path = Path(form_path)
        output_path = Path(output_path)

        logger.info(f"Starting form fill: {form_path.name}")

        # Step 0: Check for previously filled similar forms
        historical_data = {}
        historical_source = None
        
        if historical_forms_dirs:
            search_dirs = [Path(d) for d in historical_forms_dirs]
            parser = FilledFormParser()
            
            for search_dir in search_dirs:
                if search_dir.exists():
                    matching_forms = parser.find_similar_forms(form_path, search_dir)
                    if matching_forms:
                        # Use the form with most filled fields
                        best_match = matching_forms[0]
                        historical_data = best_match.fields
                        historical_source = str(best_match.form_path)
                        logger.info(
                            f"Found historical form: {best_match.form_path.name} "
                            f"with {len(historical_data)} pre-filled values"
                        )
                        break

        # Step 1: Extract remaining field values using RAG
        extracted = self.extract_all_fields(form_path)

        # Step 2: Merge data - historical takes priority
        merged_data = {}
        data_sources = {}  # Track where each value came from
        
        for field_name, value in extracted.items():
            if field_name in historical_data and historical_data[field_name]:
                # Use historical value (higher confidence)
                merged_data[field_name] = historical_data[field_name]
                data_sources[field_name] = "historical"
            elif value != "NOT FOUND":
                # Use RAG-extracted value
                merged_data[field_name] = value
                data_sources[field_name] = "rag"
            else:
                # Not found anywhere
                data_sources[field_name] = "missing"

        # Step 3: Identify missing fields
        missing = [k for k, v in data_sources.items() if v == "missing"]
        from_history = [k for k, v in data_sources.items() if v == "historical"]
        from_rag = [k for k, v in data_sources.items() if v == "rag"]

        logger.info(
            f"Data sources - Historical: {len(from_history)}, "
            f"RAG: {len(from_rag)}, Missing: {len(missing)}"
        )

        # Step 4: Validate merged data
        to_fill = {k: v for k, v in merged_data.items() if v}
        validation = self.validate_filled_data(to_fill)

        # Step 5: Fill the form
        filler = PDFFiller(form_path)
        preview = filler.preview_fill(to_fill)

        filled_path = filler.fill(to_fill, output_path)

        result = {
            "status": "success",
            "output_path": str(filled_path),
            "filled_fields": len(to_fill),
            "fields_from_history": len(from_history),
            "fields_from_rag": len(from_rag),
            "missing_fields": missing,
            "historical_form_used": historical_source,
            "validation": validation,
            "preview": preview,
        }

        if missing:
            result["clarification_needed"] = self.get_clarification_questions(missing[:5])

        return result

    def _parse_json_response(self, content: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines)

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            # Try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            return {"raw_response": content, "parse_error": str(e)}
