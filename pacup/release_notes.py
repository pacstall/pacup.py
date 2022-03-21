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

"""The release notes processor module."""

# WARNING: Shit code ahead, feel free to improve.

from abc import ABC, abstractmethod
from logging import getLogger
from typing import Dict, List, Optional

from httpx import AsyncClient

log = getLogger("rich")


class Repository(ABC):
    """
    The Repository class is an abstract class that defines the interface for
    all repositories.

    Attributes
    ----------
    current_release
        The current release of the package.
    url
        The download URL of the pacscript.
    client
        The async HTTP client used to fetch the repository.

    Methods
    -------
    get_release_notes
        Returns the release notes of the current release.
    """

    tag_name = "tag_name"
    description = "description"

    def __init__(self, current_release: str, url: str, client: AsyncClient):
        log.info(f"Processing {self.__class__.__name__} release notes...")
        self.current_release = current_release
        self.url = url
        self.client = client

    @property
    @abstractmethod
    async def release_notes(self) -> Optional[Dict[str, str]]:
        """
        Returns the release notes of the releases from the latest to the
        current release.

        Returns
        -------
        Optional[Dict[str, str]]
            The release notes of the releases from the latest to the current
            release.
        """
        ...

    def _back_calculate_current_release_index(
        self,
        releases: List[Dict[str, str]],
    ) -> int:
        """
        Back calculates the index of the current release in the list of releases.

        Parameters
        ----------
        releases
            The list of releases.

        Returns
        -------
        int
            The back calculated index of the current release.
        """
        for index, release in enumerate(releases):
            log.debug(
                f"release = {release[self.tag_name].capitalize().replace('V', '')}"
            )
            if (
                release[self.tag_name].capitalize().replace("V", "")
                == self.current_release
            ):
                return index

        log.error("Could not find current release in release notes")
        return -1

    def _get_release_notes(
        self,
        current_release_index: int,
        response: List[Dict[str, str]],
    ) -> Dict[str, str]:
        """
        Returns the release notes of the releases from the latest to the
        current release.

        Parameters
        ----------
        current_release_index
            The back calculated index of the current release in the list of
            releases.
        response
            The list of releases.

        Returns
        -------
        Dict[str, str]
            The release notes of the releases from the latest to the current
            release.
        """

        release_notes: Dict[str, str] = {}
        for index, release in enumerate(response):
            if index == current_release_index:
                break

            release_notes[release[self.tag_name]] = release[self.description]

            log.debug(f"{release_notes = }")

        return release_notes


class Github(Repository):
    """
    The Github class is a concrete implementation of the Repository class that
    fetches the release notes from the Github repository.
    """

    description = "body"

    @property
    async def release_notes(self) -> Dict[str, str]:
        """Get the release notes of the releases from the latest to the current."""

        owner = self.url.split("/")[3]
        repo = self.url.split("/")[4]

        log.debug(f"{owner = }")
        log.debug(f"{repo = }")

        response = await self.client.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases"
        )
        response.raise_for_status()

        json = response.json()

        current_release_index = self._back_calculate_current_release_index(
            releases=json
        )
        log.debug(f"{current_release_index = }")
        if current_release_index == -1:
            return {}

        return self._get_release_notes(
            current_release_index=current_release_index,
            response=json,
        )


class Gitlab(Repository):
    """
    The Gitlab class is a concrete implementation of the Repository class that
    fetches the release notes from the Gitlab repository.
    """

    @property
    async def release_notes(self) -> Dict[str, str]:
        """Get the release notes of the releases from the latest to the current."""

        if "projects" in self.url:
            # NOTE: https://gitlab.com/api/v4/projects/24386000/...
            log.info("ID type URL detected.")
            identifier = self.url.split("/")[6]
            log.debug(f"{identifier = }")

            response = await self.client.get(
                f"https://gitlab.com/api/v4/projects/{identifier}/releases"
            )

        else:
            # NOTE: https://gitlab.com/volian/nala/uploads/...
            log.info("OWNER/REPO type URL detected.")
            owner = self.url.split("/")[3]
            repo = self.url.split("/")[4]

            log.debug(f"{owner = }")
            log.debug(f"{repo = }")

            response = await self.client.get(
                f"https://gitlab.com/api/v4/projects/{owner}%2F{repo}/releases"
            )

        response.raise_for_status()

        json = response.json()

        current_release_index = self._back_calculate_current_release_index(
            releases=json
        )
        if current_release_index == -1:
            return {}

        return self._get_release_notes(current_release_index, response=json)
