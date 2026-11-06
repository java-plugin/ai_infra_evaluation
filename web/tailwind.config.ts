import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#070b16",
        panel: "#0e1526",
        line: "#1e2a44",
        accent: "#22d3ee",
        violet: "#a78bfa",
      },
    },
  },
  plugins: [],
};

export default config;
