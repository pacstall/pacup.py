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
from enum import Enum, auto
from logging import getLogger
from typing import Any, Counter, Dict, List, Literal, Optional, Union

from httpx import AsyncClient, HTTPStatusError, RequestError
from packaging import version as pkg_version
from rich import print as rprint
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table

log = getLogger("rich")


class VersionStatuses(Enum):
    UNKNOWN = auto()
    UPDATED = auto()
    OUTDATED = auto()
    NEWER = auto()


class RepologyErrors(str, Enum):
    NOT_FOUND = "Not found on repology"
    NO_PROJECT_FILTER = "No [code]project[/code] filter found in the pacscript"
    NO_FILTERS = "No repology filters found in the pacscript"
    HTTP_STATUS_ERROR = "HTTP status error"
    REQUEST_ERROR = "Request error"


class Version:
    line_number: int = -1
    current: str = ""
    __latest: str = ""

    def __init__(self, line_number: int = -1, version: str = "", latest: str = ""):
        self.line_number = line_number
        self.current = version
        self.latest = latest

    @staticmethod
    async def get_latest_version(
        filters: Dict[str, str],
        client: AsyncClient,
        semaphore: Semaphore,
        show_filters: Optional[bool],
    ) -> (
        Union[
            str,
            Literal[
                RepologyErrors.NOT_FOUND,
                RepologyErrors.NO_PROJECT_FILTER,
                RepologyErrors.NO_FILTERS,
                RepologyErrors.HTTP_STATUS_ERROR,
                RepologyErrors.REQUEST_ERROR,
            ],
        ]
    ):
        """
        Gets the latest version of a package from repology.

        Parameters
        ----------
        filters
            A dictionary of filters to filter repology response.
        client
            The Async HTTP client to use.
        semaphore
            The semaphore to use.
        show_filters
            Whether to show the repology filter and filtrate.

        Returns
        -------
        Union[str, Literal[RepologyErrors.NOT_FOUND, RepologyErrors.NO_PROJECT_FILTER, RepologyErrors.NO_FILTERS, RepologyErrors.HTTP_STATUS_ERROR, RepologyErrors.REQUEST_ERROR]]
            The latest version of the package.
        """
        async with semaphore:
            if not filters:
                return RepologyErrors.NO_FILTERS
            try:
                log.info("Getting project info from repology...")
                response = await client.get(
                    f"https://repology.org/api/v1/project/{filters['project']}"
                )
            except KeyError:
                return RepologyErrors.NO_PROJECT_FILTER
            except RequestError:
                return RepologyErrors.REQUEST_ERROR
            else:
                repology_table = Table.grid()
                repology_table.add_column()
                project = filters["project"]
                if show_filters:
                    repology_table.add_row(
                        Panel(
                            Pretty(filters, indent_guides=True),
                            title="Filters",
                            border_style="bold blue",
                        )
                    )
                if "status" not in filters:
                    filters["status"] = "newest"

                del filters["project"]

            try:
                response.raise_for_status()
            except HTTPStatusError:
                return RepologyErrors.HTTP_STATUS_ERROR

            else:
                filtered: List[Dict[str, Any]] = response.json()

                log.info("Filtering...")
                for key, value in filters.items():
                    new_filtered: List[Dict[str, Any]] = []
                    for packages in filtered:
                        if packages[key] == value:
                            new_filtered.append(packages)
                    if new_filtered:
                        filtered = new_filtered

                # Map the versions to their list of packages
                log.info("Mapping the versions to their filtered packages...")
                versions: List[str] = []

                for package in filtered:
                    versions.append(package["version"])

                log.debug(f"{filtered = }")
                log.debug(f"{versions = }")

                log.info("Selecting most common version...")
                selected_version = Counter(versions).most_common(1)[0][0]
                log.debug(f"{selected_version = }")

                if show_filters:
                    repology_table.add_row(
                        Panel(
                            Pretty(filtered, indent_guides=True),
                            title="Filtrate",
                            border_style="bold blue",
                        )
                    )
                    repology_table.add_row(
                        Panel(
                            selected_version,
                            title="Selected version (most common)",
                            style="bold blue",
                        )
                    )

                    rprint(Panel.fit(repology_table, title=f"Repology for {project}"))

                # Return the most common version
                return selected_version

    @property
    def status(
        self,
    ) -> Literal[
        VersionStatuses.UNKNOWN,
        VersionStatuses.UPDATED,
        VersionStatuses.OUTDATED,
        VersionStatuses.NEWER,
    ]:
        if self.latest in [error.value for error in RepologyErrors]:
            return VersionStatuses.UNKNOWN

        current_version = pkg_version.parse(self.current)
        latest_version = pkg_version.parse(self.latest)

        if current_version < latest_version:
            return VersionStatuses.OUTDATED
        if current_version == latest_version:
            return VersionStatuses.UPDATED

        # NOTE: if current_version > latest_version: is implicit
        return VersionStatuses.NEWER

    def __repr__(self) -> str:
        return f"Version(line_number={self.line_number}, current={self.current}, latest={self.latest}, status={self.status})"
