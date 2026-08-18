// Tailwind config, scanning index.html + all src files for class names.
// TODO: extend theme (colors, fonts) once visual design is decided.

import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
} satisfies Config;
