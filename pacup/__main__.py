#!/usr/bin/env python3

#     ____             __  __
#    / __ \____ ______/ / / /___
#   / /_/ / __ `/ ___/ / / / __ \
#  / ____/ /_/ / /__/ /_/ / /_/ /
# /_/    \__,_/\___/\____/ .___/
#                       /_/
#
# Copyright (C) 2022-present
#
# This file is part of PacUp
#
# PacUp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PacUp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PacUp.  If not, see <https://www.gnu.org/licenses/>.


import hashlib
import subprocess
import sys
from asyncio import gather
from asyncio.events import get_event_loop
from asyncio.locks import Semaphore
from difflib import unified_diff
from logging import basicConfig, getLogger
from os import get_terminal_size, makedirs
from pathlib import Path
from shutil import rmtree
from typing import Dict, Generator, List, NoReturn, Optional

import typer
from httpx import AsyncClient, HTTPStatusError, RequestError
from rich import print as rprint
from rich import traceback
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from pacup.parser import Pacscript
from pacup.version import VersionStatuses

__version__ = "0.1.0"

app = typer.Typer(name="pacup")


async def download(url: str, progress: Progress, task: TaskID) -> str:
    """
    Download a package from a URL.

    Parameters
    ----------
    url
        The URL to download the package from.
    progress
        The progress bar to use.
    task
        The task ID to update.

    Returns
    -------
    str
        The path to the downloaded package.
    """

    download_hash = hashlib.sha256()

    async with AsyncClient(follow_redirects=True).stream("GET", url) as response:
        response.raise_for_status()
        makedirs("/tmp/pacup", exist_ok=True)
        progress.update(task, total=int(response.headers["Content-Length"]))

        with open("/tmp/pacup/" + url.split("/")[-1], "wb") as file:
            progress.start_task(task)

            async for chunk in response.aiter_bytes():
                if chunk:
                    file.write(chunk)
                    progress.update(task, advance=len(chunk))
                    download_hash.update(chunk)

        # NOTE: Hash calculation is only done here at the end
        return download_hash.hexdigest()


async def get_parsed_pacscripts(
    pacscripts: List[Path],
    task: TaskID,
    progress: Progress,
    show_filters: Optional[bool],
) -> List[Pacscript]:
    """
    Get the parsed pacscripts from a list of pacscript paths.

    Parameters
    ----------
    pacscripts
        The list of pacscripts to parse.
    task
        The task ID to update.
    progress
        The progress bar to use.

    Returns
    -------
    List[Pacscript]
        The parsed pacscript objects.
    """

    # NOTE: Repology overloads if more than 11 concurrent requests are made.
    semaphore = Semaphore(11)

    async with AsyncClient() as client:
        return await gather(
            *[
                Pacscript.parse(
                    pacscript,
                    client,
                    semaphore,
                    task,
                    progress,
                    show_filters,
                )
                for pacscript in pacscripts
            ],
            return_exceptions=True,
        )


def validate_parameters(pacscripts: List[Path]) -> List[Path]:
    """
    Validate command parameters.

    Parameters
    ----------
    pacscripts
        The list of pacscript paths passed as arguments.

    Returns
    -------
    List[Path]
        Validated pacscript paths.
    """

    # Check if all the pacscript paths have `.pacscript` prefix
    # Signifying that they are pacscript files.
    if not all(map(lambda pacscript: pacscript.suffix == ".pacscript", pacscripts)):
        raise typer.BadParameter("All pacscripts must have a .pacscript extension.")

    # Error out if any of the pacscripts are `-git` pacscripts
    # Not eligible for pacup
    if any(map(lambda pacscript: pacscript.stem.endswith("-git"), pacscripts)):
        raise typer.BadParameter("Git pacscripts are not supported.")

    return pacscripts


def autocomplete_command(
    ctx: typer.Context,
    incomplete_file_name: str,
) -> Generator[str, None, None]:
    """
    Autocomplete the update command.

    Parameters
    ----------
    ctx
        The typer context.
    incomplete_file_name
        The incomplete file name typed.

    Yields
    ------
    str
        The autocompleted file name.
    """

    # Glob the pacscript files in the current directory with the incomplete
    # file name. We don't want to autocomplete a pacscript file that the user
    # has already typed
    yield from [
        path.name
        for path in Path.cwd().glob(f"{incomplete_file_name}*.pacscript")
        if all(
            suggested_path.name != path.name
            for suggested_path in (ctx.params.get("pacscripts") or [Path()])
        )
    ]


def version_callback(value: bool) -> None:
    if value:
        rprint(f"PacUp {__version__}")
        raise typer.Exit()


@app.command()
def update(
    show_filters: Optional[bool] = typer.Option(
        None,
        "-r",
        "--show-repology",
        help="Show the parsed repology data.",
    ),
    debug: Optional[bool] = typer.Option(
        None, "-d", "--debug", help="Turn on debugging mode."
    ),
    verbose: Optional[bool] = typer.Option(
        None, "-v", "--verbose", help="Turn on verbose mode."
    ),
    version_option: Optional[bool] = typer.Option(
        None,
        "-V",
        "--version",
        help="Show the version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
    pacscripts: List[Path] = typer.Argument(
        ...,
        help="The pacscripts to update.",
        exists=True,
        writable=True,
        dir_okay=False,
        callback=validate_parameters,
        autocompletion=autocomplete_command,
    ),
) -> NoReturn:
    """Updates specified pacscripts."""

    basicConfig(level="CRITICAL", format="%(message)s", handlers=[RichHandler()])
    log = getLogger("rich")

    if debug:
        log.setLevel("DEBUG")
    log.info(f"PacUp {__version__}")

    with Progress(
        SpinnerColumn(
            spinner_name="bouncingBar",
            finished_text="[bold green]:heavy_check_mark:",
        ),
        "Parsing pacscripts...",
        TextColumn("[bold blue]{task.percentage:.1f}%[/bold blue]"),
        transient=True,
    ) as parsing_pacscripts_progress:
        log.info(f"Parsing {len(pacscripts)} pacscripts")
        task = parsing_pacscripts_progress.add_task(
            "Parsing pacscripts", total=len(pacscripts)
        )
        loop = get_event_loop()
        parsed_pacscripts: List[Pacscript] = loop.run_until_complete(
            get_parsed_pacscripts(
                pacscripts, task, parsing_pacscripts_progress, show_filters
            )
        )
        log.debug(f"{parsed_pacscripts = }")
        parsing_pacscripts_progress.advance(task)

    # Display the summary to the user
    log.info("Sorting parsed pacscripts by version statsuses...")
    version_statuses_table = Table.grid()
    version_statuses_table.add_column()

    outdated_pacscripts: List[Pacscript] = []
    updated_pacscripts: List[Pacscript] = []
    newer_pacscripts: List[Pacscript] = []
    unknown_pacscripts: List[Pacscript] = []
    for pacscript in parsed_pacscripts:
        if pacscript.version.status == VersionStatuses.OUTDATED:
            outdated_pacscripts.append(pacscript)
        elif pacscript.version.status == VersionStatuses.UPDATED:
            updated_pacscripts.append(pacscript)
        elif pacscript.version.status == VersionStatuses.NEWER:
            newer_pacscripts.append(pacscript)
        else:
            unknown_pacscripts.append(pacscript)

    log.debug(
        f"oudated pacscripts = {[pacscript.path.stem for pacscript in outdated_pacscripts]}"
    )
    log.debug(
        f"up-to-date pacscripts = {[pacscript.path.stem for pacscript in updated_pacscripts]}"
    )
    log.debug(
        f"newer pacscripts = {[pacscript.path.stem for pacscript in newer_pacscripts]}"
    )
    log.debug(
        f"unknown pacscripts = {[pacscript.path.stem for pacscript in unknown_pacscripts]}"
    )

    if len(outdated_pacscripts) > 0:
        log.info("Adding outdated pacscripts to version statuses...")
        outdated_pacscripts_table = Table(box=None, expand=True)
        outdated_pacscripts_table.add_column("Pacscript", justify="center")
        outdated_pacscripts_table.add_column("Current", justify="right")
        outdated_pacscripts_table.add_column("Latest", justify="right")
        outdated_pacscripts_table.add_column("Maintainer", justify="center")

        for outdated_pacscript in outdated_pacscripts:
            outdated_pacscripts_table.add_row(
                outdated_pacscript.path.stem,
                outdated_pacscript.version.current,
                outdated_pacscript.version.latest,
                outdated_pacscript.maintainer,
                style="blue",
            )

        version_statuses_table.add_row(
            Panel(outdated_pacscripts_table, title="Outdated", border_style="bold blue")
        )

    if len(updated_pacscripts) > 0:
        log.info("Adding up-to-date pacscripts to version statuses...")
        up_to_date_pacscripts_table = Table(box=None, expand=True)
        up_to_date_pacscripts_table.add_column("Pacscript", justify="center")
        up_to_date_pacscripts_table.add_column("Maintainer", justify="center")

        for updated_pacscript in updated_pacscripts:
            up_to_date_pacscripts_table.add_row(
                updated_pacscript.path.stem,
                updated_pacscript.maintainer,
                style="green",
            )

        version_statuses_table.add_row(
            Panel(
                up_to_date_pacscripts_table,
                title="Up To Date",
                border_style="bold green",
            )
        )

    if len(newer_pacscripts) > 0:
        log.info("Adding newer pacscripts to version statuses...")
        newer_pacscripts_table = Table(box=None, expand=True)
        newer_pacscripts_table.add_column("Pacscript", justify="center")
        newer_pacscripts_table.add_column("Latest", justify="right")
        newer_pacscripts_table.add_column("Current", justify="right")
        newer_pacscripts_table.add_column("Maintainer", justify="center")

        for newer_pacscript in newer_pacscripts:
            newer_pacscripts_table.add_row(
                newer_pacscript.path.stem,
                newer_pacscript.version.latest,
                newer_pacscript.version.current,
                newer_pacscript.maintainer,
                style="magenta",
            )

        version_statuses_table.add_row(
            Panel(newer_pacscripts_table, title="Newer", border_style="bold magenta")
        )

    if len(unknown_pacscripts) > 0:
        log.info("Adding unknown pacscripts to version statuses...")
        unknown_pacscripts_table = Table(box=None, expand=True)
        unknown_pacscripts_table.add_column("Pacscript", justify="center")
        unknown_pacscripts_table.add_column("Current", justify="right")
        unknown_pacscripts_table.add_column("Latest", justify="right")
        unknown_pacscripts_table.add_column("Maintainer", justify="center")

        for unknown_pacscript in unknown_pacscripts:
            unknown_pacscripts_table.add_row(
                unknown_pacscript.path.stem,
                unknown_pacscript.version.current,
                unknown_pacscript.version.latest,
                unknown_pacscript.maintainer,
                style="red",
            )

        version_statuses_table.add_row(
            Panel(
                unknown_pacscripts_table,
                title="Unknown",
                border_style="bold red",
            )
        )

    rprint(
        Panel.fit(version_statuses_table, title="Version statuses", border_style="bold")
    )

    # Loop through the parsed pacscripts and update them
    log.info("Updating pacscripts...")
    successfully_updated_pacscripts: List[Pacscript] = []
    failed_to_update_pacscripts: Dict[Pacscript, str] = {}
    for pacscript in outdated_pacscripts:
        path = pacscript.path
        pkgname = pacscript.pkgname
        version = pacscript.version
        url = pacscript.url
        hash_line = pacscript.hash_line
        release_notes = pacscript.release_notes
        lines = pacscript.lines

        rprint(
            f"[bold blue]=>[/bold blue] Updating {path.stem} pacscript ({version.current} => {version.latest})"
        )

        # Print release notes
        if release_notes:
            log.info("Showing release notes...")
            if Confirm.ask(
                "    [bold blue]::[/bold blue] Do you want to see the release notes?",
                default=True,
            ):
                for release, release_note in release_notes.items():
                    rprint(
                        Panel(
                            Markdown(release_note),
                            title=f"Release notes for {release}",
                            border_style="bold blue",
                        )
                    )
        else:
            rprint("    [bold red]❌[/bold red] Could not find release notes")

        # Download new package
        log.info("Downloading new package...")
        with Progress(
            "   ",
            SpinnerColumn(
                spinner_name="pong", finished_text="[bold green]:heavy_check_mark:"
            ),
            "Downloading package",
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
            "•",
            TimeElapsedColumn(),
            "•",
            TransferSpeedColumn(),
        ) as downloading_package_progress:
            task = downloading_package_progress.add_task(
                "Downloading package", start=False
            )
            try:
                latest_hash = loop.run_until_complete(
                    download(
                        url.value.replace(version.current, version.latest),
                        downloading_package_progress,
                        task,
                    )
                )
            except HTTPStatusError as error:
                downloading_package_progress.advance(task)
                rprint(f"   [bold red]❌[/bold red] Could not download package: {error}")
                failed_to_update_pacscripts[
                    pacscript
                ] = f"HTTP status error: {error.response.status_code}"
                continue

            except RequestError as error:
                parsing_pacscripts_progress.advance(task)
                rprint(f"   [bold red]❌[/bold red] Could not download package: {error}")
                failed_to_update_pacscripts[
                    pacscript
                ] = f"{str(error) or type(error).__name__}"
                continue

        # Edit the pacscript file with the new version and hash
        log.info("Editing pacscript file...")
        rprint("    [bold blue]=>[/bold blue] Editing pacscript")
        edited_lines = lines.copy()
        edited_lines[version.line_number] = f'version="{version.latest}"\n'

        edited_lines[hash_line] = f'hash="{latest_hash}"\n'

        log.info("Computing diff...")
        diff = unified_diff(
            lines,
            edited_lines,
            fromfile=f"Outdated {path.name}",
            tofile=f"Updated {path.name}",
        )

        log.info("Printing diff...")
        rprint(
            Panel(
                Syntax(
                    "".join(diff),
                    "diff",
                    line_numbers=True,
                ),
                title="Diff",
                border_style="bold blue",
            )
        )

        with open(path, "w") as file:
            log.info("Writing pacscript file...")
            file.writelines(edited_lines)

        # Install the new pacscript with pacstall
        log.info("Installing pacscript...")

        rprint("   [bold blue]=>[/bold blue] Installing pacscript using pacstall")
        rprint(f"[bold blue]{'─' * get_terminal_size().columns}[/bold blue]")

        try:
            subprocess.run(["pacstall", "-Il", path.stem], check=True)
        except subprocess.CalledProcessError:
            log.warning(f"Could not install {path.name}")
            rprint(f"[bold red]{'─' * get_terminal_size().columns}\n[/bold red]")
            rprint(
                f"   [bold red]❌[/bold red]Failed to install pacscript [bold red]{path.stem}[/bold red] pacscript\n"
            )
            failed_to_update_pacscripts[
                pacscript
            ] = "Installation using pacstall failed"
            continue
        else:
            rprint(f"[bold blue]{'─' * get_terminal_size().columns}[/bold blue]")
            rprint(
                f"   [bold green]:heavy_check_mark:[/bold green] Successfully installed [bold blue]{path.stem}[/bold blue] pacscript",
            )

        # Ask the user to check the installed package
        # Succeed if the user confirms
        log.info("Asking user to check installed pacscript...")
        if Confirm.ask(f"   [bold blue]::[/bold blue] Does {pkgname} work?"):
            rprint(
                f"   [bold blue]=>[/bold blue] Finished updating pacscript [bold blue]{path.stem}[/bold blue] pacscript!"
            )

            successfully_updated_pacscripts.append(pacscript)
        else:
            rprint(
                f"   [bold red]❌[/bold red] Failed to update pacscript [bold red]{path.stem}[/bold red] pacscript!"
            )
            failed_to_update_pacscripts[pacscript] = f"{pkgname} doesn't work"

        # Clear downloaded packages
        log.info("Clearing downloaded packages...")
        rmtree("/tmp/pacup", ignore_errors=True)

    log.info("Computing summary...")
    summary_table = Table.grid()
    summary_table.add_column()

    if len(successfully_updated_pacscripts) > 0:
        log.info("Adding successfully updated pacscripts to summary...")
        success_table = Table(box=None, expand=True)
        success_table.add_column("Pacscript", justify="center")
        success_table.add_column("Update", justify="center")

        for successfully_updated_pacscript in successfully_updated_pacscripts:
            success_table.add_row(
                f"[bold blue]{successfully_updated_pacscript.path.stem}[/bold blue]",
                f"[bold blue]{successfully_updated_pacscript.version.current}[/bold blue] => [bold blue]{successfully_updated_pacscript.version.latest}[/bold blue]",
            )

        success_panel = Panel(
            success_table,
            title="Success",
            border_style="bold green",
            padding=(0, 0),
        )
        summary_table.add_row(success_panel)

    if len(failed_to_update_pacscripts) > 0:
        log.info("Adding failed pacscripts to summary...")
        failed_table = Table(box=None, expand=True)
        failed_table.add_column("Pacscript", justify="center")
        failed_table.add_column("Update", justify="center")
        failed_table.add_column("Reason", justify="center")

        for (
            failed_to_update_pacscript,
            failiure_reason,
        ) in failed_to_update_pacscripts.items():
            failed_table.add_row(
                f"[bold red]{failed_to_update_pacscript.path.stem}[/bold red]",
                f"[bold red]{failed_to_update_pacscript.version.current}[/bold red] => [bold red]{failed_to_update_pacscript.version.latest}[/bold red]",
                f"[bold red]{failiure_reason}[/bold red]",
            )

        failed_panel = Panel(
            failed_table,
            title="Failures",
            border_style="bold red",
            padding=(0, 0),
        )
        summary_table.add_row(failed_panel)

    if len(successfully_updated_pacscripts) > 0 or len(failed_to_update_pacscripts) > 0:
        log.info("Printing summary...")
        rprint(
            Panel.fit(
                summary_table,
                title="Summary",
                border_style="bold white",
                padding=(0, 0),
            )
        )

    log.debug(
        f"Successfully updated pacscripts = {[pacscript.path.stem for pacscript in successfully_updated_pacscripts]}"
    )
    log.debug(
        f"Failed to update pacscripts = {[(pacscript.path.stem, reason) for pacscript, reason in failed_to_update_pacscripts.items()]}"
    )

    log.info("Exiting...")
    sys.exit(70 if len(failed_to_update_pacscripts) > 0 else 0)


def main() -> None:
    """The main function."""
    traceback.install(show_locals=True)
    app()


if __name__ == "__main__":
    main()
