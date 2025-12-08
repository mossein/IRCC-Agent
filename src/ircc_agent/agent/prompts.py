"""LLM prompts for IRCC form filling agent."""

SYSTEM_PROMPT = """You are an expert immigration assistant specialized in filling out IRCC (Immigration, Refugees and Citizenship Canada) application forms.

Your task is to extract accurate information from the provided documents to fill form fields. Follow these guidelines:

1. **Accuracy**: Only use information explicitly stated in the documents. Never guess or make up information.

2. **Format Compliance**: Format values according to IRCC requirements:
   - Dates: Use DD/MM/YYYY format unless specified otherwise
   - Names: UPPERCASE for surname, Title Case for given names
   - Phone numbers: Include country code (e.g., +1 XXX-XXX-XXXX)
   - Addresses: Follow Canadian postal address format

3. **Missing Information**: If information for a required field is not found in the documents, clearly indicate it as "NOT FOUND" rather than leaving it blank or guessing.

4. **Consistency**: Ensure information is consistent across related fields (e.g., dates of birth, names spelled the same way).

5. **Field Types**:
   - For text fields: Provide the exact value
   - For checkboxes: Respond with true/false
   - For dropdowns: Select from available options
   - For dates: Use the specified format

Always explain your reasoning when the information might be ambiguous."""


FIELD_EXTRACTION_PROMPT = """Based on the following documents, extract the value for this form field:

**Field Name**: {field_name}
**Field Type**: {field_type}
**Field Description/Tooltip**: {tooltip}
{options_text}

**Relevant Documents**:
{context}

---

Respond in JSON format:
{{
    "value": "extracted value or NOT FOUND",
    "confidence": "high/medium/low",
    "source": "which document/section the info came from",
    "reasoning": "brief explanation"
}}"""


BATCH_EXTRACTION_PROMPT = """Based on the following documents, extract values for all these form fields:

**Fields to Extract**:
{fields_json}

**Available Documents**:
{context}

---

Respond with a JSON object mapping field names to their values:
{{
    "field_name_1": {{
        "value": "extracted value or NOT FOUND",
        "confidence": "high/medium/low"
    }},
    "field_name_2": {{
        "value": "extracted value or NOT FOUND", 
        "confidence": "high/medium/low"
    }}
}}

Only include fields you can find information for or mark as NOT FOUND."""


VALIDATION_PROMPT = """Review the following filled form data for accuracy and completeness.

**Form Fields and Values**:
{filled_data}

**Original Documents**:
{context}

---

Check for:
1. Inconsistencies (names spelled differently, conflicting dates)
2. Format issues (wrong date format, missing country codes)
3. Suspicious values (future dates for past events, impossible ages)

Respond in JSON format:
{{
    "is_valid": true/false,
    "issues": [
        {{"field": "field_name", "issue": "description", "suggestion": "corrected value"}}
    ],
    "warnings": ["any other concerns"]
}}"""


CLARIFICATION_PROMPT = """The following required fields could not be filled from the provided documents:

**Missing Fields**:
{missing_fields}

Please provide clear, specific questions to ask the user to collect this missing information.

Respond in JSON format:
{{
    "questions": [
        {{"field": "field_name", "question": "user-friendly question"}}
    ]
}}"""
