import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{vue,ts}"],
  theme: {
    extend: {
      colors: {
        ink: "#161612",
        coal: "#22201d",
        paper: "#fffaf0",
        honey: "#f5b942",
        coral: "#ff6b5f",
        mint: "#6ee7b7",
        aqua: "#5bc0eb",
        grape: "#7c5cff",
      },
      boxShadow: {
        glow: "0 18px 50px rgba(124, 92, 255, 0.24)",
        lift: "0 16px 30px rgba(22, 22, 18, 0.12)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
