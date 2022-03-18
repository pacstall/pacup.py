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


from asyncio.locks import Semaphore
from asyncio.subprocess import PIPE, Process, create_subprocess_shell
from logging import getLogger
from pathlib import Path
from typing import Dict, List, Optional

from httpx import AsyncClient, HTTPStatusError, RequestError
from rich.progress import Progress, TaskID

from pacup.version import Version

log = getLogger("rich")


def extract_var(line: str, var: str) -> str:
    """
    Strips off ``var=`` and quotes from a line and returns the variable.

    Parameters
    ----------
    line
        The pacscript line.
    var
        The variable to extract.

    Returns
    -------
    str
        Extracted variable.
    """

    return line.replace(var, "").strip('"')


async def query_data(pacscript_reader_process: Process, query_command: str) -> str:
    """
    Queries data off of the pacscript parsing subprocess.

    Parameters
    ----------
    pacscript_reader_process
        The pacscript reading subprocess.
    query_command
        The command to execute in the ``pacscript_reader_process``.

    Returns
    -------
    str
        The output of ``query_command`` in the subprocess.
    """

    assert pacscript_reader_process.stdin is not None
    assert pacscript_reader_process.stdout is not None

    pacscript_reader_process.stdin.write(f"{query_command};echo\n".encode())
    await pacscript_reader_process.stdin.drain()

    output = await pacscript_reader_process.stdout.read(999999)

    return output.decode().strip()


class Url:
    line_number: int = -1
    value: str = ""

    def __init__(self, line_number: int = -1, value: str = ""):
        self.line_number = line_number
        self.value = value

    def __repr__(self) -> str:
        return f"Url(line_number={self.line_number}, value={self.value})"


class Pacscript:
    def __init__(
        self,
        path: Path,
        pkgname: str,
        version: Version,
        url: Url,
        hash_line: int,
        maintainer: str,
        repology_filters: Dict[str, str],
        release_notes: Dict[str, str],
        lines: List[str],
    ):
        """
        Parameters
        ----------
        path
            The path to the pacscript.
        pkgname
            The package name.
        version
            The package version.
        url
            The url to the package.
        hash_line
            The line number of the hash.
        maintainer
            The maintainer of the pacscript.
        repology_filters
            The repology filters.
        release_notes
            The release notes.
        lines
            The lines of the pacscript.
        """

        self.path = path
        self.pkgname = pkgname
        self.version = version
        self.url = url
        self.hash_line = hash_line
        self.maintainer = maintainer
        self.repology_filters = repology_filters
        self.release_notes = release_notes
        self.lines = lines

    @classmethod
    async def parse(
        cls,
        path: Path,
        client: AsyncClient,
        semaphore: Semaphore,
        task: TaskID,
        progress: Progress,
        show_filters: Optional[bool],
    ) -> "Pacscript":
        """
        Parses a pacscript file.

        Parameters
        ----------
        path
            The path to the pacscript file.
        client
            The Async HTTP client to use.
        semaphore
            The semaphore to use.
        task
            The parsing task to update.
        progress
            The progress bar to use.
        show_filters
            Whether to show the repology filters and filtrate.

        Returns
        -------
        Pacscript
            The parsed pacscript object.
        """

        log.info(f"Parsing {path.name}...")
        with path.open() as file:
            lines = file.readlines()

        # Get the package name
        pkgname = path.stem.replace("-bin", "").replace("-deb", "").replace("-app", "")

        # Instantiate placeholder variables
        version = Version()
        url = Url()
        hash_line = -1  # Which line contains the hash
        maintainer = ""
        repology_filters: Dict[str, str] = {}

        pacscript_reader_process = await create_subprocess_shell(
            "/bin/bash", stdin=PIPE, stdout=PIPE
        )

        assert pacscript_reader_process.stdin is not None
        log.info(f"Sourcing {path.name}...")
        pacscript_reader_process.stdin.write(f"source {path.absolute()}\n".encode())
        await pacscript_reader_process.stdin.drain()

        # Parse the pacscript file
        for line_number, line in enumerate(lines):
            line = line.strip()
            if line.startswith("pkgname="):
                log.info(f"Found pkgname: {line}")
                pkgname = (
                    await query_data(pacscript_reader_process, "echo ${pkgname}")
                    if ("$" in line) or ("\\" in line)
                    else extract_var(line, "pkgname=")
                )

            elif line.startswith("version="):
                log.info(f"Found version: {line}")
                version = (
                    Version(
                        line_number,
                        await query_data(pacscript_reader_process, "echo ${version}"),
                    )
                    if ("$" in line) or ("\\" in line)
                    else Version(
                        line_number,
                        extract_var(line, "version="),
                    )
                )

            elif line.startswith("url="):
                log.info(f"Found url: {line}")
                url = (
                    Url(
                        line_number,
                        await query_data(pacscript_reader_process, "echo ${url}"),
                    )
                    if ("$" in line) or ("\\" in line)
                    else Url(
                        line_number,
                        extract_var(line, "url="),
                    )
                )
            elif line.startswith("hash="):
                log.info(f"Found hash: {line}")
                hash_line = line_number

            elif line.startswith("maintainer="):
                log.info(f"Found maintainer: {line}")
                maintainer = (
                    await query_data(pacscript_reader_process, "echo ${maintainer}")
                    if ("$" in line) or ("\\" in line)
                    else extract_var(line, "maintainer=")
                )

            elif line.startswith("repology="):
                log.info(f"Found repology: {line}")
                repology_output = await query_data(
                    pacscript_reader_process,
                    'for property in "${repology[@]}"; do echo "${property}"; done',
                )

                try:
                    for repology_filter in repology_output.splitlines():
                        filter_key, filter_value = repology_filter.split(": ")
                        repology_filters[filter_key] = filter_value
                except ValueError:
                    log.error(f"Failed to parse repology filters for {path.stem}.")
                else:
                    log.debug(f"{repology_filters = }")

        version.latest = await Version.get_latest_version(
            repology_filters, client, semaphore, show_filters
        )

        # Fetch the release notes
        release_notes: Dict[str, str] = {}
        try:
            owner = url.value.split("/")[3]
            repo = url.value.split("/")[4]

            log.debug(f"{owner = }")
            log.debug(f"{repo = }")

            # Get each versions release notes between current and latest
            release_notes_apis = {
                "github": f"https://api.github.com/repos/{owner}/{repo}/releases",
                # BUG: GitLab doesn't work
                "gitlab": f"https://{url.value.split('/')[2]}/api/v4/projects/{owner}%2F{repo}/releases",
                "bitbucket": f"https://api.bitbucket.org/2.0/repositories/{owner}/{repo}/releases",
            }

            release_note_api = release_notes_apis[url.value.split("/")[2].split(".")[0]]

            log.info(f"release_note_api = {release_note_api}")

        except (IndexError, KeyError):
            release_notes = {}
        else:
            try:
                response = await client.get(release_note_api)
                response.raise_for_status()
            except (HTTPStatusError, RequestError):
                release_notes = {}
            else:
                json = response.json()
                # Find out how many releases there are between current and latest
                current_release_index = 0
                if "github" in url.value:
                    for index, releases in enumerate(json):
                        if (
                            releases["tag_name"].capitalize().replace("V", "")
                            == version.current
                        ):
                            current_release_index = index
                            break
                elif "gitlab" in url.value:
                    for index, releases in enumerate(json()):
                        if (
                            releases["tag_name"].capitalize().replace("V", "")
                            == version.current
                        ):
                            current_release_index = index
                            break
                elif "bitbucket" in url.value:
                    for index, releases in enumerate(json()):
                        if (
                            releases["name"].capitalize().replace("V", "")
                            == version.current
                        ):
                            current_release_index = index
                            break

                log.debug(f"{current_release_index = }")

                for index, release_note in enumerate(json):
                    if current_release_index == index:
                        break
                    if "github" in url.value:
                        if release_note["tag_name"]:
                            release_notes[release_note["tag_name"]] = release_note[
                                "body"
                            ]
                    elif "gitlab" in url.value:
                        release_notes[release_note["tag_name"]] = release_note[
                            "description"
                        ]
                    elif "bitbucket" in url.value:
                        release_notes[release_note["name"]] = release_note[
                            "description"
                        ]

        pacscript_reader_process.stdin.close()
        await pacscript_reader_process.wait()

        progress.advance(task)

        # Return the parsed pacscript object
        return cls(
            path=path,
            pkgname=pkgname,
            version=version,
            url=url,
            hash_line=hash_line,
            maintainer=maintainer,
            repology_filters=repology_filters,
            release_notes=release_notes,
            lines=lines,
        )

    def __repr__(self) -> str:
        return f"Pacscript(name={self.path.name}, pkgname={self.pkgname}, version={self.version}, url={self.url}, hash_line={self.hash_line}, maintainer='{self.maintainer}' repology_filters={self.repology_filters})"
