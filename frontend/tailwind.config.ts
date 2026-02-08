import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        dark: {
          bg: {
            primary: "#0a0a0a",
            secondary: "#1a1a1a",
            tertiary: "#2a2a2a",
          },
          text: {
            primary: "#f5f5f5",
            secondary: "#d0d0d0",
            tertiary: "#808080",
          },
          border: "#404040",
          accent: "#3b82f6",
        },
        light: {
          bg: {
            primary: "#ffffff",
            secondary: "#f9f9f9",
            tertiary: "#f0f0f0",
          },
          text: {
            primary: "#1a1a1a",
            secondary: "#505050",
            tertiary: "#808080",
          },
          border: "#e0e0e0",
          accent: "#0066cc",
        },
      },
    },
  },
  plugins: [],
};

export default config;
