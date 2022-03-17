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

from time import sleep
from typing import List

from rich.live import Live
from rich.panel import Panel

# list: List[str] = []
# with Live(Panel("\n".join(list)), vertical_overflow="visible") as live:
#     while True:
#         list.append("New line")
#         live.update(Panel("\n".join(list)))
#         sleep(0.2)

queue: List[str] = []

count = 0

with Live(Panel("\n".join(queue)), vertical_overflow="visible") as live:
    while True:
        live.update(Panel("\n".join(queue)))
        queue.append(str(count))
        sleep(0.2)
        count += 1
        if len(queue) > 10:
            queue.pop(0)
