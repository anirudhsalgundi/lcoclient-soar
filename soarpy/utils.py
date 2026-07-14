import requests
from rich.console import Console
from rich.table import Table

from soarpy.logger import get_logger

logger = get_logger(__name__)


def _stats(lco_token: str, headers: dict) -> None: #FIXME in dev

    proposals_response = requests.get('https://observe.lco.global/api/proposals/', headers=headers)
    proposals_data = proposals_response.json()

    # active_proposals = [p for p in proposals_data['results'] if p.get('active')]
    active_proposals = [p for p in proposals_data['results'] if p['active'] == True]
    logger.info(f"Total proposals: {proposals_data['count']} | Active: {len(active_proposals)}\n\n")

    console = Console()
    table = Table(
        title="LCO/SOAR Active Proposals", 
        style="cyan", 
        header_style="bold white",
        border_style="bright_black"
    )

    table.add_column("ID", style="bold magenta", no_wrap=True)
    table.add_column("Proposal Title", style="white")
    table.add_column("Status", style="green", justify="center")

    for p in active_proposals:
        table.add_row(p['id'], p['title'], p['active'] and "[green]Active[/green]" or "[red]Inactive[/red]")

    console.print(table)


    return None