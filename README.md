<div align="center">

# 🎨 Draw.io to TikZ Converter

<p align="center">
  <strong>Transform your Draw.io diagrams into professional LaTeX TikZ code</strong>
</p>

<p align="center">
  <a href="https://github.com/okayama-daiki/drawio-to-tikz/actions"><img src="https://github.com/okayama-daiki/drawio-to-tikz/workflows/Continuous%20Integration/badge.svg" alt="CI Status"></a>
  <a href="https://github.com/okayama-daiki/drawio-to-tikz/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-16.0-black?logo=next.js" alt="Next.js"></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/React-19.2-blue?logo=react" alt="React"></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-5-blue?logo=typescript" alt="TypeScript"></a>
</p>

</div>

---

## ✨ Features

- **🎯 Easy Conversion** - Upload your Draw.io files and get instant TikZ code
- **📝 Interactive Editor** - Edit the generated TikZ code in real-time
- **👀 Live Preview** - See a preview of your diagram before using it
- **📁 Multiple Formats** - Supports `.drawio` and `.xml` file formats
- **🎨 Modern UI** - Clean and intuitive interface built with Next.js and Tailwind CSS
- **⚡ Fast Processing** - Quick conversion powered by server-side processing
- **📋 Copy & Export** - Easy copy-to-clipboard functionality for generated code

## 🚀 Quick Start

### Prerequisites

- [Bun](https://bun.sh/) (latest version recommended)
- Node.js 20+ (for alternative package managers)

### Installation

```bash
# Clone the repository
git clone https://github.com/okayama-daiki/drawio-to-tikz.git
cd drawio-to-tikz

# Install dependencies
bun install

# Run the development server
bun run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the application.

## 📖 Usage

1. **Upload Your Diagram**
   - Click the upload area or drag and drop your Draw.io file (`.drawio` or `.xml`)
   
2. **Get TikZ Code**
   - The application automatically converts your diagram to TikZ code
   
3. **Edit & Preview**
   - Use the built-in editor to modify the generated code
   - Switch to preview mode to see the result
   
4. **Copy to Your Document**
   - Copy the TikZ code and paste it into your LaTeX document

### Example

```latex
% In your LaTeX document
\documentclass{article}
\usepackage{tikz}

\begin{document}
  \begin{tikzpicture}
    % Paste your generated TikZ code here
  \end{tikzpicture}
\end{document}
```

## 🛠️ Tech Stack

- **Framework**: [Next.js 16](https://nextjs.org/) - React framework for production
- **Language**: [TypeScript](https://www.typescriptlang.org/) - Type-safe JavaScript
- **Styling**: [Tailwind CSS 4](https://tailwindcss.com/) - Utility-first CSS framework
- **UI Components**: [Headless UI](https://headlessui.com/) - Unstyled, accessible components
- **Icons**: [Lucide React](https://lucide.dev/) - Beautiful icon library
- **XML Parsing**: [@xmldom/xmldom](https://github.com/xmldom/xmldom) - DOM parser for Node.js
- **Code Quality**: [Biome](https://biomejs.dev/) - Fast linter and formatter
- **Runtime**: [Bun](https://bun.sh/) - Fast JavaScript runtime

## 🏗️ Development

### Available Scripts

```bash
# Start development server
bun run dev

# Build for production
bun run build

# Start production server
bun run start

# Run linter
bun run lint

# Format code
bun run format
```

### Project Structure

```
drawio-to-tikz/
├── app/
│   ├── _components/       # React components
│   ├── _lib/             # Utility functions
│   ├── api/              # API routes
│   │   └── convert/      # Conversion endpoint
│   ├── layout.tsx        # Root layout
│   └── page.tsx          # Home page
├── public/               # Static assets
├── biome.json           # Biome configuration
├── next.config.ts       # Next.js configuration
├── tailwind.config.ts   # Tailwind CSS configuration
└── tsconfig.json        # TypeScript configuration
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow the existing code style
- Run `bun run lint` before committing
- Write meaningful commit messages
- Update documentation as needed

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits & Acknowledgments

- [Lucide React](https://github.com/lucide-icons/lucide) - Beautiful & consistent icon toolkit made by the community
- [Draw.io](https://www.drawio.com/) - Free online diagram software
- [TikZ & PGF](https://github.com/pgf-tikz/pgf) - TeX Graphic System

## 📬 Contact

**Daiki Okayama** - [@okayama-daiki](https://github.com/okayama-daiki)

Project Link: [https://github.com/okayama-daiki/drawio-to-tikz](https://github.com/okayama-daiki/drawio-to-tikz)

---

<div align="center">
  Made with ❤️ by <a href="https://github.com/okayama-daiki">Daiki Okayama</a>
</div>
