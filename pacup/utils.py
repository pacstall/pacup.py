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

"""Utility functions."""

from contextlib import contextmanager
from typing import Generator

current_level = 0


@contextmanager
def level() -> Generator[str, None, None]:
    """Context manager for printing with indentation."""
    global current_level
    current_level += 1
    yield "      " * current_level
    current_level -= 1
