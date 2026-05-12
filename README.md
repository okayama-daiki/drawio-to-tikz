# drawio2tikz

`drawio2tikz` is a thin wrapper around [`svg2tikz`](https://github.com/xyz2tex/svg2tikz) that converts draw.io diagrams to TikZ code for embedding in LaTeX documents.

## Features

- Converts either a single draw.io page or all pages
- Converts multiple draw.io files from the web UI
- Preserves label colors, bold text, font sizes, and simple line breaks
- **Ignores draw.io font family names**, allowing output to use the host LaTeX document font
- Removes draw.io SVG CSS that `svg2tikz` cannot parse, including `light-dark(...)` from draw.io's dark mode color scheme
- Restores draw.io labels emitted as SVG `foreignObject` elements, which draw.io exports as HTML fragments

## Requirements

- **Python 3.14 or newer**
- **`drawio` CLI** available on `PATH` (install from [diagrams.net](https://diagrams.net) or via Homebrew: `brew install --cask drawio`)

## Installation

### pip / uv

Install from PyPI:

```bash
uv tool install drawio2tikz
```

Or with pip:

```bash
pip install drawio2tikz
```

### Development Setup

Clone the repository and install in development mode:

```bash
git clone https://github.com/daikiokayama/drawio2tikz.git
cd drawio2tikz
uv sync
uv run drawio2tikz --help
```

## Usage

### Basic Usage

Convert a single page from a draw.io file to TikZ:

```bash
drawio2tikz path/to/figure.drawio -o output_dir
```

This generates `figure.tex` in the output directory.

### Convert All Pages

To convert all pages in a multi-page `.drawio` file:

```bash
drawio2tikz path/to/multipage.drawio --all-pages -o output_dir
```

Each page is saved as `multipage-01.tex`, `multipage-02.tex`, and so on.

### Keep Intermediate SVG

To debug or inspect the intermediate SVG (after sanitization):

```bash
drawio2tikz path/to/figure.drawio -o output_dir --keep-svg --svg-dir output_dir/svg
```

### View Help

```bash
drawio2tikz --help
```

## Web App

Run the FastAPI web UI locally:

```bash
uv sync
uv run drawio2tikz-web
```

Then open <http://localhost:8000>.

The conversion API is available at `POST /api/convert` with multipart form data:

- `file`: one or more `.drawio`, `.drawio.png`, or `.xml` files
- `page_index`: 1-based page index, default `1`
- `all_pages`: convert every page, default `false`
- `keep_svg`: include the sanitized intermediate SVG, default `false`

### Docker

Build and run the web app:

```bash
docker build -t drawio2tikz .
docker run --rm -p 8000:8000 drawio2tikz
```

On Apple Silicon, build the amd64 image because the Dockerfile installs the draw.io Desktop `.deb` package:

```bash
docker build --platform linux/amd64 -t drawio2tikz .
docker run --rm --platform linux/amd64 -p 8000:8000 drawio2tikz
```

## LaTeX Setup

Add these packages to your LaTeX document preamble:

```tex
\usepackage{xcolor}
\usepackage{tikz}
\usepackage{amsmath}
```

Include the generated TikZ file:

```tex
\input{path/to/figure.tex}
```

For support of arbitrary large font sizes, use a scalable font:

```tex
\usepackage{mlmodern}
```

### Example LaTeX Document

```tex
\documentclass{article}
\usepackage{xcolor}
\usepackage{tikz}
\usepackage{amsmath}
\usepackage{mlmodern}

\begin{document}

\section{My Diagram}

\begin{figure}
  \centering
  \input{figures/diagram.tex}
  \caption{A diagram created in draw.io}
\end{figure}

\end{document}
```

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests on [GitHub](https://github.com/daikiokayama/drawio2tikz).

## License

MIT
