import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0f100e", // Deep warm dark background
        foreground: "#f5f6f4", // Off-white text
        card: {
          DEFAULT: "#171815", // Warm card dark background
          foreground: "#f5f6f4",
        },
        border: "#2c2d2a", // Olive-tinted dark border
        muted: {
          DEFAULT: "#898b84", // Muted olive-tinted secondary text
          foreground: "#898b84",
        },
        accent: {
          DEFAULT: "#e1e9d8", // Sage / Pale mint green
          foreground: "#151614", // Dark text on light sage
          hover: "#d1dbc7",
        },
      },
    },
  },
  plugins: [],
};
export default config;
