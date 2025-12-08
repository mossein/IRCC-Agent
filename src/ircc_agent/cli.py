"""Command-line interface for IRCC PDF Agent."""

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ircc_agent import __version__

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)

app = typer.Typer(
    name="ircc-agent",
    help="LLM-powered agent for filling IRCC immigration PDF applications.",
    add_completion=False,
)
console = Console()


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        console.print(f"[bold blue]IRCC Agent[/] v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
):
    """IRCC PDF Agent - Intelligent form filling assistant."""
    pass


@app.command()
def ingest(
    documents_dir: Path = typer.Argument(
        ...,
        help="Directory containing user documents (PDFs, images, text files).",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        "-r/-R",
        help="Search subdirectories for documents.",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        "-c",
        help="Clear existing documents before ingesting.",
    ),
):
    """Ingest user documents into the RAG vector store.

    This command processes all supported documents in the specified directory,
    extracts text content, and stores embeddings for later retrieval.

    Supported formats: PDF, PNG, JPG, TIFF, TXT, MD
    """
    from ircc_agent.rag import VectorStore, load_documents_from_directory

    console.print(
        Panel.fit(
            f"[bold]Ingesting documents from:[/] {documents_dir}",
            title="📁 Document Ingestion",
        )
    )

    try:
        # Load vector store
        store = VectorStore()

        if clear:
            console.print("[yellow]Clearing existing documents...[/]")
            store.clear()

        # Load documents with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Loading documents...", total=None)
            documents = load_documents_from_directory(
                documents_dir,
                recursive=recursive,
            )

        if not documents:
            console.print("[yellow]No documents found.[/]")
            raise typer.Exit(1)

        console.print(f"[green]Found {len(documents)} document pages/sections[/]")

        # Add to vector store
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("Embedding and storing documents...", total=None)
            ids = store.add_documents(documents)

        console.print(
            Panel.fit(
                f"✅ [bold green]Successfully ingested {len(ids)} chunks[/]\n"
                f"📊 Total documents in store: {store.count}",
                title="Complete",
            )
        )

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        logger.exception("Ingestion failed")
        raise typer.Exit(1)


@app.command()
def fill(
    form_path: Path = typer.Argument(
        ...,
        help="Path to the IRCC PDF form to fill.",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for filled PDF (default: form_filled.pdf).",
    ),
    history: Optional[list[Path]] = typer.Option(
        None,
        "--history",
        "-h",
        help="Directories containing previously filled forms to use as data source.",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Interactive mode to review and edit before saving.",
    ),
):
    """Fill an IRCC PDF form using ingested documents.

    The agent will:
    1. Check for previously filled similar forms (highest priority)
    2. Search ingested documents for relevant information via RAG
    3. Use LLM to extract and validate field values
    4. Fill the PDF form and save the output

    Example with historical forms:
        ircc-agent fill forms/IMM5257.pdf --history ~/old_applications
    """
    from ircc_agent.agent import IRCCAgent
    from ircc_agent.config import settings

    # Determine output path
    if output is None:
        output = form_path.parent / f"{form_path.stem}_filled.pdf"

    console.print(
        Panel.fit(
            f"[bold]Form:[/] {form_path.name}\n"
            f"[bold]Output:[/] {output}"
            + (f"\n[bold]History:[/] {', '.join(str(h) for h in history)}" if history else ""),
            title="📝 Form Filling",
        )
    )

    try:
        agent = IRCCAgent()

        # Check if documents are ingested
        if agent.vector_store.count == 0 and not history:
            console.print(
                "[yellow]⚠️  No documents ingested. Run 'ircc-agent ingest' first.[/]"
            )
            raise typer.Exit(1)

        if agent.vector_store.count > 0:
            console.print(f"[dim]Using {agent.vector_store.count} document chunks[/]")
        
        if history:
            console.print(f"[dim]Searching {len(history)} historical form directories[/]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Extracting and filling form...", total=None)

            result = agent.fill_form(
                form_path=form_path,
                output_path=output,
                historical_forms_dirs=history,
                interactive=interactive,
            )

        # Display results
        _display_fill_results(result)

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        logger.exception("Form filling failed")
        raise typer.Exit(1)


def _display_fill_results(result: dict):
    """Display form filling results in a nice format."""
    console.print()

    # Status panel
    status = "✅ Success" if result["status"] == "success" else "❌ Failed"
    
    # Build status message
    status_msg = f"{status}\n[bold]Output:[/] {result['output_path']}\n"
    status_msg += f"[bold]Fields filled:[/] {result['filled_fields']}"
    
    # Show data sources breakdown
    from_history = result.get("fields_from_history", 0)
    from_rag = result.get("fields_from_rag", 0)
    
    if from_history or from_rag:
        status_msg += f"\n  • From historical forms: {from_history}"
        status_msg += f"\n  • From RAG documents: {from_rag}"
    
    # Show which historical form was used
    if result.get("historical_form_used"):
        status_msg += f"\n[bold]Historical form:[/] {Path(result['historical_form_used']).name}"
    
    console.print(Panel.fit(status_msg, title="Results"))

    # Missing fields
    if result.get("missing_fields"):
        console.print("\n[yellow]⚠️  Missing information:[/]")
        for field in result["missing_fields"][:10]:
            console.print(f"  • {field}")

        if result.get("clarification_needed"):
            console.print("\n[bold]Questions to gather missing info:[/]")
            for q in result["clarification_needed"]:
                console.print(f"  ❓ {q.get('question', q)}")

    # Validation issues
    validation = result.get("validation", {})
    if validation.get("issues"):
        console.print("\n[yellow]⚠️  Validation issues:[/]")
        for issue in validation["issues"]:
            console.print(f"  • {issue.get('field', 'Unknown')}: {issue.get('issue', '')}")


@app.command()
def inspect(
    form_path: Path = typer.Argument(
        ...,
        help="Path to the PDF form to inspect.",
        exists=True,
    ),
):
    """Inspect a PDF form to see its fields and structure.

    Useful for understanding what fields need to be filled.
    """
    from ircc_agent.pdf import FormFieldExtractor

    console.print(Panel.fit(f"[bold]Inspecting:[/] {form_path.name}", title="🔍 Form Inspection"))

    try:
        extractor = FormFieldExtractor(form_path)

        console.print(f"\n[bold]Form Type:[/] {extractor.form_type.value.upper()}")

        fields = extractor.extract_fields()

        if not fields:
            console.print("[yellow]No fillable fields found in this PDF.[/]")
            return

        # Group by field type
        by_type = {}
        for f in fields:
            type_name = f.field_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(f)

        # Summary table
        summary = Table(title="Field Summary")
        summary.add_column("Type", style="cyan")
        summary.add_column("Count", justify="right")

        for type_name, type_fields in sorted(by_type.items()):
            summary.add_row(type_name, str(len(type_fields)))

        console.print(summary)

        # Detailed table
        console.print(f"\n[bold]Total fields: {len(fields)}[/]")

        table = Table(title="Form Fields", show_lines=True)
        table.add_column("Name", style="green", max_width=40)
        table.add_column("Type", style="cyan")
        table.add_column("Page", justify="right")
        table.add_column("Options/Value", max_width=30)

        for f in fields[:50]:  # Limit to 50 for display
            options_str = ""
            if f.options:
                options_str = ", ".join(f.options[:3])
                if len(f.options) > 3:
                    options_str += f" (+{len(f.options) - 3} more)"
            elif f.value:
                options_str = str(f.value)[:30]

            table.add_row(
                f.name[:40],
                f.field_type.value,
                str(f.page),
                options_str,
            )

        if len(fields) > 50:
            table.add_row("...", "...", "...", f"(+{len(fields) - 50} more fields)")

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        logger.exception("Inspection failed")
        raise typer.Exit(1)


@app.command()
def status():
    """Show status of the current document store and configuration."""
    from ircc_agent.config import settings
    from ircc_agent.rag import VectorStore

    console.print(Panel.fit("[bold]IRCC Agent Status[/]", title="📊 Status"))

    # Configuration
    config_table = Table(title="Configuration")
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value")

    config_table.add_row("LLM Provider", settings.llm_provider)
    config_table.add_row("Model", settings.model_name)
    config_table.add_row("Chunk Size", str(settings.chunk_size))
    config_table.add_row("Retrieval K", str(settings.retrieval_k))

    console.print(config_table)

    # Vector store status
    try:
        store = VectorStore()
        doc_count = store.count

        console.print(f"\n[bold]Document Store:[/] {doc_count} chunks indexed")

        if doc_count == 0:
            console.print(
                "[yellow]No documents ingested. "
                "Run 'ircc-agent ingest <directory>' to add documents.[/]"
            )
    except Exception as e:
        console.print(f"[yellow]Could not access document store: {e}[/]")


@app.command()
def fill_xfa(
    form_path: Path = typer.Argument(
        ...,
        help="Path to the XFA PDF form to fill.",
        exists=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for filled form.",
    ),
    history: Optional[list[Path]] = typer.Option(
        None,
        "--history",
        "-h",
        help="Directories containing previously filled forms.",
    ),
    generate_js: bool = typer.Option(
        False,
        "--generate-js",
        "-j",
        help="Generate JavaScript file for manual use in Acrobat instead of automation.",
    ),
):
    """Fill an XFA form using Adobe Acrobat automation.

    This command uses Adobe Acrobat's JavaScript API to fill XFA forms
    that cannot be filled with standard PDF libraries.

    Example:
        ircc-agent fill-xfa form.pdf -o filled_form.pdf
        ircc-agent fill-xfa form.pdf --generate-js  # Creates JS file for manual use
    """
    from ircc_agent.agent.core import IRCCAgent
    from ircc_agent.pdf.extractor import FormFieldExtractor, FormType
    from ircc_agent.pdf.acrobat_automation import (
        AdobeAcrobatAutomation,
        generate_acrobat_javascript,
        save_acrobat_javascript,
    )

    console.print(Panel(f"🔧 XFA Form Filling\n[dim]{form_path.name}[/]"))

    # Check if it's actually an XFA form
    extractor = FormFieldExtractor(form_path)
    if extractor.form_type != FormType.XFA:
        console.print(
            f"[yellow]This is not an XFA form (detected: {extractor.form_type.value}). "
            "Use 'ircc-agent fill' instead.[/]"
        )
        raise typer.Exit(1)

    # Extract fields
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Extracting XFA fields...", total=None)
        fields = extractor.extract_fields()

    console.print(f"[green]Found {len(fields)} XFA fields[/]")

    # Get data using the agent
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Extracting data from documents...", total=None)
        
        try:
            agent = IRCCAgent()
            
            # Use batch extraction - process fields directly
            field_values = agent._extract_batch(fields)
        except Exception as e:
            console.print(f"[red]Error extracting data: {e}[/]")
            field_values = {}

    filled_count = sum(1 for v in field_values.values() if v)
    console.print(f"[green]Extracted values for {filled_count} fields[/]")

    # Either generate JS file or use automation
    if generate_js:
        js_path = output or form_path.parent / f"{form_path.stem}_fill.js"
        save_acrobat_javascript(field_values, js_path)
        console.print(Panel(
            f"✅ Generated JavaScript file\n"
            f"[bold]{js_path}[/]\n\n"
            f"To use:\n"
            f"1. Open the PDF in Adobe Acrobat\n"
            f"2. Press Ctrl+J to open JavaScript console\n"
            f"3. Paste the contents of the JS file\n"
            f"4. Press Enter to run",
            title="JavaScript Generated",
        ))
    else:
        # Use direct XFA PDF writing
        from ircc_agent.pdf.xfa_writer import fill_xfa_with_fdf
        
        output_path = output or form_path.parent / f"{form_path.stem}_filled.pdf"
        
        console.print("[dim]Writing to XFA PDF...[/]")
        
        try:
            result_path = fill_xfa_with_fdf(form_path, field_values, output_path)
            
            console.print(Panel(
                f"✅ XFA Form Filled\n"
                f"Output: [bold]{result_path}[/]\n"
                f"Fields with values: {filled_count}",
                title="Complete",
            ))
        except Exception as e:
            console.print(f"[red]Error writing PDF: {e}[/]")
            raise typer.Exit(1)


@app.command()
def fill_gui(
    form: Path = typer.Argument(..., help="Path to the XFA PDF form"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output path for filled PDF"
    ),
    min_confidence: str = typer.Option(
        "medium", "--min-confidence", "-c",
        help="Minimum confidence level: high, medium, low"
    ),
):
    """Fill XFA forms using GUI automation (keeps forms editable).
    
    Uses PyAutoGUI to control Adobe Acrobat and fill forms like a human would.
    Only fills fields with sufficient confidence and validates dropdown options.
    
    ⚠️ DO NOT MOVE YOUR MOUSE during automation!
    """
    form_path = Path(form)
    if not form_path.exists():
        console.print(f"[red]Form not found: {form_path}[/]")
        raise typer.Exit(1)

    console.print(Panel(
        f"🤖 Smart GUI Form Filling\n{form_path.name}",
    ))

    # Extract field info from XFA
    from ircc_agent.pdf.xfa_parser import XFAParser
    from ircc_agent.pdf.gui_automation import SmartFormFiller, FieldToFill
    from ircc_agent.agent.core import IRCCAgent
    
    with Progress(SpinnerColumn(), TextColumn("{task.description}")) as progress:
        # Parse XFA fields
        task = progress.add_task("Parsing XFA fields...")
        parser = XFAParser(form_path)
        xfa_fields = parser.extract_fields()
        console.print(f"Found {len(xfa_fields)} XFA fields")
        
        # Extract data using LLM
        progress.update(task, description="Extracting data with LLM...")
        agent = IRCCAgent()
        
        # Get first 30 important fields (skip empty-named ones)
        important_fields = [f for f in xfa_fields if f.name and f.field_type != "signature"][:30]
        
        # Convert XFAField to FormField for LLM extraction
        from ircc_agent.pdf.extractor import FormField, FieldType
        
        form_fields = []
        for xf in important_fields:
            ft = FieldType.TEXT
            if xf.field_type == "dropdown":
                ft = FieldType.DROPDOWN
            elif xf.field_type == "checkbox":
                ft = FieldType.CHECKBOX
            elif xf.field_type == "date":
                ft = FieldType.DATE
            
            form_fields.append(FormField(
                name=xf.name,
                field_type=ft,
                options=xf.options,
                tooltip=xf.tooltip,
            ))
        
        try:
            extracted = agent._extract_batch(form_fields)
        except Exception as e:
            console.print(f"[red]Error extracting data: {e}[/]")
            extracted = {}
    
    console.print(f"Extracted values for {len(extracted)} fields")
    
    # Build fields to fill with confidence and type info
    fields_to_fill = []
    
    for xfa_field in important_fields:
        if xfa_field.name not in extracted:
            continue
            
        value = extracted[xfa_field.name]
        if not value or str(value) == "NOT FOUND":
            continue
        
        # Determine confidence (for now, set all extracted as medium)
        confidence = "medium"
        
        # For dropdowns, validate against options
        if xfa_field.field_type == "dropdown" and xfa_field.options:
            matched = False
            value_lower = str(value).lower()
            for opt in xfa_field.options:
                if opt and (opt.lower() == value_lower or value_lower in opt.lower()):
                    value = opt  # Use exact option
                    matched = True
                    confidence = "high"
                    break
            if not matched:
                console.print(f"[yellow]⚠️ '{value}' not in dropdown options for {xfa_field.name}[/]")
                confidence = "low"  # Will be skipped
        
        # Filter by confidence
        if min_confidence == "high" and confidence != "high":
            continue
        if min_confidence == "medium" and confidence == "low":
            continue
        
        fields_to_fill.append(FieldToFill(
            name=xfa_field.name,
            value=str(value),
            field_type=xfa_field.field_type,
            options=xfa_field.options,
            confidence=confidence,
        ))
    
    console.print(f"\n[bold]Will fill {len(fields_to_fill)} fields[/]")
    console.print("[yellow]⚠️ DO NOT MOVE YOUR MOUSE during automation![/]")
    console.print("[dim]Move mouse to top-left corner to abort[/]\n")
    
    import time
    time.sleep(3)
    
    # Run GUI automation
    filler = SmartFormFiller()
    filler.open_pdf(form_path)
    time.sleep(3)
    
    filler.go_to_first_field()
    
    filled = 0
    for field in fields_to_fill:
        if filler.fill_field(field):
            filled += 1
        filler.next_field()
        time.sleep(0.3)
    
    console.print(Panel(
        f"✅ GUI Fill Complete\n"
        f"Filled: {filled} fields\n"
        f"[dim]Save manually with Cmd+S[/]",
        title="Done",
    ))


if __name__ == "__main__":
    app()

