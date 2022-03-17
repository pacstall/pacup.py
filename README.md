<p align="center"><img alt="logo" src=imgs/logo.png/></p>
<h1 align="center">Pacup</h1>

## What is this?

Pacup (**Pac**script **Up**dater) is a maintainer helper tool to help
maintainers update their pacscripts. It semi-automates the tedious task of
updating pacscripts, and aims to make it a fun process for the maintainer!

## Installation

We have plans to make standalone executable binaries, making a pacscript and
publishing to PyPI after the first release of Pacup.

For now you can install it directly from the repository.

```bash
$ pip install git+https://github.com/pacstall/pacup
```

## Usage

```
Usage: pacup [OPTIONS] PACSCRIPTS...

  Updates specified pacscripts.

Arguments:
  PACSCRIPTS...  The pacscripts to update.  [required]

Options:
  -s, --show-filters              Show the parsed repology filters and
                                  filterate.
  -d, --debug                     Turn on debugging mode.
  -v, --verbose                   Turn on verbose mode.
  -V, --version                   Show the version and exit.
  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified shell, to
                                  copy it or customize the installation.
  --help                          Show this message and exit.
```

You can get this help text by running `pacup --help`

## How does it work?

Suppose `foo.pacscript` is outdated.

On running `pacup foo.pacscript` Pacup will parse the pacscript's variables,
then it compiles a list of filters specified in the `repology` variable in the
pacscript. Then it queries the [Repology API](https://repology.org/api) to get
all the repositories which have packaged that package. After which it applies
the filter to the response, and from the filterate it considers the **first**
repository's package's version to be the latest.

Then it replaces all occurrences of the previous `version`'s value in the `url`
with the latest one placeholder's value with the latest version, and downloads
the new package, and generates it's hash.

Then writes the edited pacscript and installs it with
[Pacstall](https://github.com/pacstall/pacstall), after installation it asks
the user to confirm that the installed package works. On approval the pacscript
is considered successfully upgraded and the program ends.

## Caveats

* Does not work with `-git` pacscripts as those pacscripts are auto updating.
* Doesn't work if a pacscript doesn't have an equivalent
  [Repology](https://repology.org/) package.

## License

```
    ____             __  __
   / __ \____ ______/ / / /___
  / /_/ / __ `/ ___/ / / / __ \
 / ____/ /_/ / /__/ /_/ / /_/ /
/_/    \__,_/\___/\____/ .___/
                      /_/

Copyright (C) 2022-present

This file is part of PacUp

PacUp is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PacUp is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PacUp.  If not, see <https://www.gnu.org/licenses/>.```
