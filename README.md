# IRCC PDF Agent

LLM-powered agent that auto-fills IRCC (Immigration, Refugees and Citizenship Canada) PDF applications using RAG from user documents.

## Features

- 📁 **Document Ingestion**: Load PDFs, images, and text files from your documents folder
- 🔍 **Smart RAG**: Uses vector embeddings to find relevant information for each form field
- 🤖 **LLM Extraction**: Google Gemini extracts and validates field values
- 📝 **PDF Filling**: Automatically fills PDF forms with extracted data

## Quick Start

### 1. Install

```bash
# Clone and install with UV
cd IRCC-Agent
source $HOME/.local/bin/env  # If UV was just installed
uv sync
```

### 2. Configure

```bash
# Copy the example config
cp .env.example .env

# Edit .env and add your Google API key
# Get one at https://makersuite.google.com/app/apikey
```

### 3. Ingest Your Documents

```bash
# Put your documents (passport, employment letter, etc.) in a folder
# Then ingest them:
uv run ircc-agent ingest /path/to/your/documents
```

### 4. Fill an IRCC Form

```bash
# Download an IRCC form and fill it:
uv run ircc-agent fill forms/IMM5257E.pdf -o filled_form.pdf

# If you have previously filled forms, use them as a data source:
uv run ircc-agent fill forms/IMM5257E.pdf --history ~/old_applications -o filled_form.pdf
```

## Commands

| Command | Description |
|---------|-------------|
| `ircc-agent ingest <dir>` | Ingest documents into RAG store |
| `ircc-agent fill <form>` | Fill a PDF form with extracted data |
| `ircc-agent fill <form> --history <dir>` | Fill using previous forms as priority source |
| `ircc-agent inspect <form>` | View form fields and structure |
| `ircc-agent status` | Show current configuration and stats |

## Data Sources Priority

When filling forms, the agent uses data in this order:

1. **Historical forms** (highest priority) - Previously filled copies of the same form
2. **RAG documents** - Extracted from ingested user documents
3. **Manual input** - Questions for missing fields

## Requirements

- Python 3.11+
- Google API key (for Gemini LLM)
- Tesseract (optional, for OCR): `brew install tesseract`

## Project Structure

```
src/ircc_agent/
├── cli.py          # Command-line interface
├── config.py       # Configuration management
├── rag/            # Document processing & retrieval
│   ├── loader.py   # Multi-format document loading
│   ├── chunker.py  # Text chunking
│   └── store.py    # ChromaDB vector store
├── pdf/            # PDF form handling
│   ├── extractor.py # Form field extraction
│   └── filler.py    # PDF form filling
└── agent/          # LLM agent logic
    ├── prompts.py   # Specialized prompts
    └── core.py      # Agent orchestration
```

## License

MIT